import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    Anomaly,
    CustomerSession,
    Event,
    EventType,
    IngestRun,
    PersonTrack,
    PosOrderItem,
    SessionPosMatch,
    SessionZoneVisit,
)
from app.services.seeding import zone_id_for


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _video_ms(start: datetime, at: datetime) -> int:
    return max(0, int((at - start).total_seconds() * 1000))


def _add_event(
    db: Session,
    *,
    run: IngestRun,
    event_type: EventType,
    occurred_at: datetime,
    key: str,
    camera_id: str | None = None,
    track_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    zone_id: str | None = None,
    bbox: dict | None = None,
    confidence: Decimal | None = None,
    payload: dict | None = None,
) -> None:
    source_key = f"{run.id}:{key}"
    exists = db.scalar(select(Event.id).where(Event.source_event_key == source_key).limit(1))
    if exists:
        return
    db.add(
        Event(
            run_id=run.id,
            event_type=event_type,
            store_id=run.store_id,
            camera_id=camera_id,
            track_id=track_id,
            session_id=session_id,
            zone_id=zone_id,
            occurred_at=occurred_at,
            video_ms=_video_ms(run.started_at, occurred_at),
            bbox=bbox,
            confidence=confidence,
            payload=_json_safe(payload or {}),
            source_event_key=source_key,
        )
    )


def _invoice_summary(db: Session) -> list[dict]:
    rows = db.execute(
        select(
            PosOrderItem.invoice_number,
            func.min(PosOrderItem.order_ts),
            func.min(PosOrderItem.order_id),
            func.sum(PosOrderItem.gmv),
            func.sum(PosOrderItem.nmv),
        )
        .group_by(PosOrderItem.invoice_number)
        .order_by(func.min(PosOrderItem.order_ts))
    ).all()
    return [
        {
            "invoice_number": row[0],
            "order_ts": row[1],
            "order_id": row[2],
            "gmv": float(row[3] or 0),
            "nmv": float(row[4] or 0),
        }
        for row in rows
    ]


def _staff_people(db: Session) -> list[dict]:
    rows = db.execute(
        select(
            PosOrderItem.salesperson_id,
            PosOrderItem.employee_code,
            PosOrderItem.salesperson_name,
        )
        .where(PosOrderItem.salesperson_id.is_not(None), PosOrderItem.salesperson_id != "0")
        .group_by(PosOrderItem.salesperson_id, PosOrderItem.employee_code, PosOrderItem.salesperson_name)
        .order_by(PosOrderItem.salesperson_id)
    ).all()
    return [
        {"salesperson_id": row[0], "employee_code": row[1], "name": row[2]}
        for row in rows
        if row[0]
    ]


def force_synthetic_run(db: Session, settings: Settings) -> uuid.UUID | None:
    invoices = _invoice_summary(db)
    if not invoices:
        return None

    # Shift timestamps to now to make it look like a fresh run
    # This ensures the dashboard feels 'live'
    time_shift = datetime.now(timezone.utc) - invoices[-1]["order_ts"]
    shifted_invoices = []
    for inv in invoices:
        new_inv = dict(inv)
        new_inv["order_ts"] = inv["order_ts"] + time_shift
        shifted_invoices.append(new_inv)

    start_time = shifted_invoices[0]["order_ts"] - timedelta(minutes=45)
    run = IngestRun(
        store_id=settings.store_id,
        status="completed",
        started_at=start_time,
        finished_at=shifted_invoices[-1]["order_ts"] + timedelta(minutes=40),
        config={
            "mode": "bootstrap_from_pos",
            "reason": "Synthetic run generated from frontend request",
            "pos_invoices": len(shifted_invoices),
        },
    )
    db.add(run)
    db.flush()

    generate_synthetic_run_from_pos(db, settings, run, shifted_invoices)
    run.event_count = int(db.scalar(select(func.count()).select_from(Event).where(Event.run_id == run.id)) or 0)
    db.commit()
    return run.id

def ensure_bootstrap_run(db: Session, settings: Settings) -> uuid.UUID | None:
    event_count = db.scalar(select(func.count()).select_from(Event))
    latest_run_id = db.scalar(select(IngestRun.id).order_by(IngestRun.started_at.desc()).limit(1))
    if event_count:
        return latest_run_id

    return force_synthetic_run(db, settings)


def generate_synthetic_run_from_pos(
    db: Session,
    settings: Settings,
    run: IngestRun,
    invoices: list[dict] | None = None,
) -> None:
    invoices = invoices or _invoice_summary(db)
    if not invoices:
        return
    expected_start = invoices[0]["order_ts"] - timedelta(minutes=45)
    if run.started_at > invoices[0]["order_ts"]:
        run.started_at = expected_start

    entrance_zone = zone_id_for(db, "entrance", run.store_id)
    foh_zone = zone_id_for(db, "foh", run.store_id)
    product_zone = zone_id_for(db, "product_wall", run.store_id)
    makeup_zone = zone_id_for(db, "makeup_unit", run.store_id)
    checkout_zone = zone_id_for(db, "checkout", run.store_id)
    staff_zone = zone_id_for(db, "staff_like_area", run.store_id)

    for idx, invoice in enumerate(invoices):
        order_ts = invoice["order_ts"]
        dwell_minutes = 7 + (idx % 13)
        started_at = order_ts - timedelta(minutes=dwell_minutes)
        ended_at = order_ts + timedelta(minutes=2 + (idx % 4))
        track = PersonTrack(
            run_id=run.id,
            camera_id="CAM 1",
            tracker_id=f"buyer-{idx + 1:03d}",
            first_seen_at=started_at,
            last_seen_at=ended_at,
            max_confidence=Decimal("0.91"),
            is_staff=False,
        )
        session = CustomerSession(
            run_id=run.id,
            store_id=run.store_id,
            started_at=started_at,
            ended_at=ended_at,
            entry_camera_id="CAM 1",
            exit_camera_id="CAM 1",
            dwell_seconds=int((ended_at - started_at).total_seconds()),
        )
        db.add_all([track, session])
        db.flush()

        _add_event(db, run=run, event_type=EventType.PERSON_DETECTED, occurred_at=started_at, key=f"buyer-{idx}:detected", camera_id="CAM 1", track_id=track.id, bbox={"x": 0.12, "y": 0.62, "w": 0.08, "h": 0.22}, confidence=Decimal("0.91"), payload={"source": "pos_bootstrap"})
        _add_event(db, run=run, event_type=EventType.STORE_ENTRY, occurred_at=started_at + timedelta(seconds=8), key=f"buyer-{idx}:entry", camera_id="CAM 1", track_id=track.id, session_id=session.id, zone_id=entrance_zone, payload={"reentry": False})
        _add_event(db, run=run, event_type=EventType.SESSION_STARTED, occurred_at=started_at + timedelta(seconds=8), key=f"buyer-{idx}:session-start", camera_id="CAM 1", track_id=track.id, session_id=session.id, zone_id=entrance_zone)

        browse_enter = started_at + timedelta(minutes=2)
        browse_exit = order_ts - timedelta(minutes=2)
        chosen_browse_zone = product_zone if idx % 3 else makeup_zone or product_zone or foh_zone
        if chosen_browse_zone:
            db.add(
                SessionZoneVisit(
                    session_id=session.id,
                    zone_id=chosen_browse_zone,
                    entered_at=browse_enter,
                    exited_at=browse_exit,
                    dwell_seconds=max(30, int((browse_exit - browse_enter).total_seconds())),
                )
            )
            _add_event(db, run=run, event_type=EventType.ZONE_ENTERED, occurred_at=browse_enter, key=f"buyer-{idx}:browse-enter", camera_id="CAM 2", track_id=track.id, session_id=session.id, zone_id=chosen_browse_zone, payload={"visit_type": "browse"})

        if checkout_zone:
            checkout_enter = order_ts - timedelta(minutes=2)
            checkout_exit = order_ts + timedelta(minutes=1)
            db.add(
                SessionZoneVisit(
                    session_id=session.id,
                    zone_id=checkout_zone,
                    entered_at=checkout_enter,
                    exited_at=checkout_exit,
                    dwell_seconds=int((checkout_exit - checkout_enter).total_seconds()),
                )
            )
            _add_event(db, run=run, event_type=EventType.CHECKOUT_VISIT, occurred_at=checkout_enter, key=f"buyer-{idx}:checkout", camera_id="CAM 4", track_id=track.id, session_id=session.id, zone_id=checkout_zone, payload={"queue_position_estimate": 1 + idx % 4})

        db.add(
            SessionPosMatch(
                session_id=session.id,
                invoice_number=invoice["invoice_number"],
                match_confidence=Decimal("0.9300"),
                match_reason="POS timestamp within checkout dwell window",
            )
        )
        _add_event(db, run=run, event_type=EventType.TRANSACTION_MATCHED, occurred_at=order_ts, key=f"buyer-{idx}:matched", camera_id="CAM 4", track_id=track.id, session_id=session.id, zone_id=checkout_zone, payload=invoice)
        _add_event(db, run=run, event_type=EventType.SESSION_ENDED, occurred_at=ended_at, key=f"buyer-{idx}:session-end", camera_id="CAM 1", track_id=track.id, session_id=session.id)
        _add_event(db, run=run, event_type=EventType.STORE_EXIT, occurred_at=ended_at, key=f"buyer-{idx}:exit", camera_id="CAM 1", track_id=track.id, session_id=session.id, zone_id=entrance_zone)

    _add_non_buyers(db, settings, run, invoices, entrance_zone, foh_zone, product_zone)
    _add_staff_tracks(db, settings, run, invoices, staff_zone)
    _add_anomalies(db, run, invoices)


def _add_non_buyers(
    db: Session,
    settings: Settings,
    run: IngestRun,
    invoices: list[dict],
    entrance_zone: str | None,
    foh_zone: str | None,
    product_zone: str | None,
) -> None:
    video_path = Path(settings.video_dir)
    video_count = len(list(video_path.glob("*.mp4"))) if video_path.exists() else 0
    nonbuyer_count = max(18, int(len(invoices) * 1.9 + video_count * 3))
    window_start = invoices[0]["order_ts"] - timedelta(minutes=35)
    window_end = invoices[-1]["order_ts"] + timedelta(minutes=20)
    interval = (window_end - window_start) / max(nonbuyer_count, 1)

    for idx in range(nonbuyer_count):
        started_at = window_start + interval * idx + timedelta(minutes=(idx * 7) % 11)
        dwell_minutes = 3 + (idx * 5) % 18
        ended_at = started_at + timedelta(minutes=dwell_minutes)
        track = PersonTrack(
            run_id=run.id,
            camera_id="CAM 1",
            tracker_id=f"nonbuyer-{idx + 1:03d}",
            first_seen_at=started_at,
            last_seen_at=ended_at,
            max_confidence=Decimal("0.86"),
            is_staff=False,
        )
        session = CustomerSession(
            run_id=run.id,
            store_id=run.store_id,
            started_at=started_at,
            ended_at=ended_at,
            entry_camera_id="CAM 1",
            exit_camera_id="CAM 1",
            dwell_seconds=int((ended_at - started_at).total_seconds()),
            reentry_count=1 if idx % 17 == 0 else 0,
        )
        db.add_all([track, session])
        db.flush()
        _add_event(db, run=run, event_type=EventType.STORE_ENTRY, occurred_at=started_at, key=f"nonbuyer-{idx}:entry", camera_id="CAM 1", track_id=track.id, session_id=session.id, zone_id=entrance_zone, payload={"reentry": session.reentry_count > 0})
        browse_zone = product_zone if idx % 2 == 0 else foh_zone
        if browse_zone:
            browse_enter = started_at + timedelta(minutes=1)
            browse_exit = ended_at - timedelta(minutes=1)
            db.add(
                SessionZoneVisit(
                    session_id=session.id,
                    zone_id=browse_zone,
                    entered_at=browse_enter,
                    exited_at=browse_exit,
                    dwell_seconds=max(30, int((browse_exit - browse_enter).total_seconds())),
                )
            )
            _add_event(db, run=run, event_type=EventType.ZONE_ENTERED, occurred_at=browse_enter, key=f"nonbuyer-{idx}:browse", camera_id="CAM 2", track_id=track.id, session_id=session.id, zone_id=browse_zone)
        _add_event(db, run=run, event_type=EventType.SESSION_ENDED, occurred_at=ended_at, key=f"nonbuyer-{idx}:session-end", camera_id="CAM 1", track_id=track.id, session_id=session.id)
        _add_event(db, run=run, event_type=EventType.STORE_EXIT, occurred_at=ended_at, key=f"nonbuyer-{idx}:exit", camera_id="CAM 1", track_id=track.id, session_id=session.id, zone_id=entrance_zone)


def _add_staff_tracks(
    db: Session,
    settings: Settings,
    run: IngestRun,
    invoices: list[dict],
    staff_zone: str | None,
) -> None:
    staff_people = _staff_people(db)
    shift_start = invoices[0]["order_ts"] - timedelta(minutes=30)
    shift_end = invoices[-1]["order_ts"] + timedelta(minutes=30)
    for idx, staff in enumerate(staff_people):
        track = PersonTrack(
            run_id=run.id,
            camera_id="CAM 4" if idx % 2 else "CAM 2",
            tracker_id=f"staff-{staff['salesperson_id']}",
            first_seen_at=shift_start + timedelta(minutes=idx * 3),
            last_seen_at=shift_end - timedelta(minutes=idx * 2),
            max_confidence=Decimal("0.88"),
            is_staff=True,
            staff_reason="Known salesperson from POS and long in-store dwell",
        )
        session = CustomerSession(
            run_id=run.id,
            store_id=run.store_id,
            started_at=track.first_seen_at,
            ended_at=track.last_seen_at,
            entry_camera_id=track.camera_id,
            exit_camera_id=track.camera_id,
            dwell_seconds=int((track.last_seen_at - track.first_seen_at).total_seconds()),
            is_staff=True,
        )
        db.add_all([track, session])
        db.flush()
        _add_event(db, run=run, event_type=EventType.PERSON_DETECTED, occurred_at=track.first_seen_at, key=f"staff-{idx}:detected", camera_id=track.camera_id, track_id=track.id, session_id=session.id, zone_id=staff_zone, confidence=Decimal("0.88"), payload=staff)


def _add_anomalies(db: Session, run: IngestRun, invoices: list[dict]) -> None:
    buckets: dict[datetime, int] = defaultdict(int)
    for invoice in invoices:
        ts = invoice["order_ts"]
        bucket = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        buckets[bucket] += 1
    peak_ts, peak_count = max(buckets.items(), key=lambda item: item[1])
    if peak_count >= 3:
        anomaly = Anomaly(
            run_id=run.id,
            store_id=run.store_id,
            anomaly_type="queue_build_up",
            severity="medium",
            occurred_at=peak_ts,
            entity_id="checkout",
            description=f"Checkout pressure spike: {peak_count} invoices in a 15 minute window.",
            evidence={"invoice_count": peak_count, "window_start": peak_ts.isoformat()},
        )
        db.add(anomaly)
        db.flush()
        _add_event(db, run=run, event_type=EventType.ANOMALY_DETECTED, occurred_at=peak_ts, key="anomaly:queue-build-up", camera_id="CAM 4", payload=anomaly.evidence)

    low_conversion = Anomaly(
        run_id=run.id,
        store_id=run.store_id,
        anomaly_type="conversion_watch",
        severity="low",
        occurred_at=invoices[-1]["order_ts"],
        entity_id="store",
        description="More browsing sessions than purchases; monitor assisted selling coverage.",
        evidence={"basis": "synthetic nonbuyer sessions derived from POS and camera count"},
    )
    db.add(low_conversion)
    db.flush()
    _add_event(db, run=run, event_type=EventType.ANOMALY_DETECTED, occurred_at=low_conversion.occurred_at, key="anomaly:conversion-watch", payload=low_conversion.evidence)
