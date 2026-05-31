from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

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
    Zone,
)


def latest_run_id(db: Session, store_id: str) -> UUID | None:
    """Return the best default analytics run.

    Prefer completed runs that produced events. A just-clicked queued/running run
    should be visible through its status endpoint, but it should not zero out the
    dashboard until analytics rows exist.
    """

    completed_with_events = db.scalar(
        select(IngestRun.id)
        .where(IngestRun.store_id == store_id, IngestRun.status == "completed", IngestRun.event_count > 0)
        .order_by(desc(IngestRun.finished_at), desc(IngestRun.started_at))
        .limit(1)
    )
    if completed_with_events:
        return completed_with_events

    completed = db.scalar(
        select(IngestRun.id)
        .where(IngestRun.store_id == store_id, IngestRun.status == "completed")
        .order_by(desc(IngestRun.finished_at), desc(IngestRun.started_at))
        .limit(1)
    )
    if completed:
        return completed

    return db.scalar(
        select(IngestRun.id)
        .where(IngestRun.store_id == store_id)
        .order_by(desc(IngestRun.started_at))
        .limit(1)
    )


def _run_filter(run_id: UUID | None):
    return CustomerSession.run_id == run_id if run_id else True


def compute_metrics(
    db: Session,
    *,
    store_id: str,
    run_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    run_id = run_id or latest_run_id(db, store_id)
    session_filters = [CustomerSession.store_id == store_id]
    if run_id:
        session_filters.append(CustomerSession.run_id == run_id)
    if start:
        session_filters.append(CustomerSession.started_at >= start)
    if end:
        session_filters.append(CustomerSession.started_at <= end)

    customer_sessions = int(
        db.scalar(
            select(func.count())
            .select_from(CustomerSession)
            .where(*session_filters, CustomerSession.is_staff.is_(False))
        )
        or 0
    )
    staff_tracks = int(
        db.scalar(
            select(func.count())
            .select_from(PersonTrack)
            .where(PersonTrack.run_id == run_id, PersonTrack.is_staff.is_(True))
        )
        or 0
    )
    pos_invoices = int(
        db.scalar(
            select(func.count(func.distinct(PosOrderItem.invoice_number))).where(PosOrderItem.store_id == store_id)
        )
        or 0
    )
    matched_purchases = int(
        db.scalar(
            select(func.count(func.distinct(SessionPosMatch.session_id)))
            .select_from(SessionPosMatch)
            .join(CustomerSession, CustomerSession.id == SessionPosMatch.session_id)
            .where(*session_filters, CustomerSession.is_staff.is_(False))
        )
        or 0
    )
    avg_dwell = db.scalar(
        select(func.avg(CustomerSession.dwell_seconds)).where(
            *session_filters,
            CustomerSession.is_staff.is_(False),
            CustomerSession.dwell_seconds.is_not(None),
        )
    )
    active_visitors = int(
        db.scalar(
            select(func.count())
            .select_from(CustomerSession)
            .where(*session_filters, CustomerSession.is_staff.is_(False), CustomerSession.ended_at.is_(None))
        )
        or 0
    )
    anomaly_count = int(
        db.scalar(
            select(func.count())
            .select_from(Anomaly)
            .where(Anomaly.store_id == store_id, Anomaly.run_id == run_id if run_id else True)
        )
        or 0
    )

    conversion = matched_purchases / customer_sessions if customer_sessions else 0.0
    return {
        "store_id": store_id,
        "run_id": str(run_id) if run_id else None,
        "footfall": customer_sessions,
        "customer_sessions": customer_sessions,
        "staff_tracks": staff_tracks,
        "pos_invoices": pos_invoices,
        "matched_purchases": matched_purchases,
        "conversion_rate": round(conversion, 4),
        "avg_dwell_seconds": int(avg_dwell or 0),
        "active_visitors": active_visitors,
        "anomaly_count": anomaly_count,
    }


def get_funnel(db: Session, *, store_id: str, run_id: UUID | None = None) -> dict[str, Any]:
    run_id = run_id or latest_run_id(db, store_id)
    base = [CustomerSession.store_id == store_id, CustomerSession.is_staff.is_(False)]
    if run_id:
        base.append(CustomerSession.run_id == run_id)

    entered_sessions = db.scalars(select(CustomerSession.id).where(*base)).all()
    entered_set = set(entered_sessions)

    browsed_sessions = db.scalars(
        select(SessionZoneVisit.session_id)
        .join(CustomerSession, CustomerSession.id == SessionZoneVisit.session_id)
        .join(Zone, Zone.id == SessionZoneVisit.zone_id)
        .where(*base, Zone.zone_type.not_in(["entrance", "checkout", "staff_like_area"]))
    ).all()
    
    checkout_sessions = db.scalars(
        select(SessionZoneVisit.session_id)
        .join(CustomerSession, CustomerSession.id == SessionZoneVisit.session_id)
        .join(Zone, Zone.id == SessionZoneVisit.zone_id)
        .where(*base, Zone.zone_type == "checkout")
    ).all()

    purchased_sessions = db.scalars(
        select(SessionPosMatch.session_id)
        .join(CustomerSession, CustomerSession.id == SessionPosMatch.session_id)
        .where(*base)
    ).all()

    purchased_set = set(purchased_sessions)
    checkout_set = set(checkout_sessions) | purchased_set
    browsed_set = set(browsed_sessions) | checkout_set
    # Ensure nobody can bypass entered_set (though naturally they shouldn't)
    browsed_set &= entered_set
    checkout_set &= entered_set
    purchased_set &= entered_set

    return {
        "run_id": str(run_id) if run_id else None,
        "steps": [
            {"name": "entered", "count": len(entered_set)},
            {"name": "browsed", "count": len(browsed_set)},
            {"name": "checkout_visit", "count": len(checkout_set)},
            {"name": "purchased", "count": len(purchased_set)},
        ],
    }


def list_events(
    db: Session,
    *,
    run_id: UUID | None = None,
    event_type: str | None = None,
    limit: int = 100,
    after: datetime | None = None,
) -> dict[str, Any]:
    filters = []
    if run_id:
        filters.append(Event.run_id == run_id)
    if event_type:
        filters.append(Event.event_type == EventType(event_type))
    if after:
        filters.append(Event.occurred_at > after)

    rows = db.execute(
        select(Event)
        .where(*filters)
        .order_by(desc(Event.occurred_at))
        .limit(min(limit, 500))
    ).scalars()
    events = [
        {
            "id": str(event.id),
            "run_id": str(event.run_id),
            "event_type": event.event_type.value,
            "store_id": event.store_id,
            "camera_id": event.camera_id,
            "track_id": str(event.track_id) if event.track_id else None,
            "session_id": str(event.session_id) if event.session_id else None,
            "zone_id": event.zone_id,
            "occurred_at": event.occurred_at.isoformat(),
            "video_ms": event.video_ms,
            "bbox": event.bbox,
            "confidence": float(event.confidence) if event.confidence is not None else None,
            "payload": event.payload,
        }
        for event in rows
    ]
    return {"events": events}


def list_anomalies(db: Session, *, store_id: str, run_id: UUID | None = None) -> dict[str, Any]:
    filters = [Anomaly.store_id == store_id]
    if run_id:
        filters.append(Anomaly.run_id == run_id)
    rows = db.execute(select(Anomaly).where(*filters).order_by(desc(Anomaly.occurred_at))).scalars()
    return {
        "anomalies": [
            {
                "id": str(row.id),
                "run_id": str(row.run_id),
                "type": row.anomaly_type,
                "severity": row.severity,
                "occurred_at": row.occurred_at.isoformat(),
                "entity_id": row.entity_id,
                "description": row.description,
                "evidence": row.evidence,
            }
            for row in rows
        ]
    }


def zone_heatmap(db: Session, *, store_id: str, run_id: UUID | None = None) -> dict[str, Any]:
    filters = [CustomerSession.store_id == store_id, CustomerSession.is_staff.is_(False)]
    if run_id:
        filters.append(CustomerSession.run_id == run_id)
    rows = db.execute(
        select(
            Zone.id,
            Zone.name,
            Zone.zone_type,
            func.count(SessionZoneVisit.id),
            func.avg(SessionZoneVisit.dwell_seconds),
        )
        .select_from(SessionZoneVisit)
        .join(CustomerSession, CustomerSession.id == SessionZoneVisit.session_id)
        .join(Zone, Zone.id == SessionZoneVisit.zone_id)
        .where(*filters)
        .group_by(Zone.id, Zone.name, Zone.zone_type)
        .order_by(desc(func.count(SessionZoneVisit.id)))
    ).all()
    return {
        "zones": [
            {
                "zone_id": row[0],
                "name": row[1],
                "zone_type": row[2],
                "visits": int(row[3] or 0),
                "avg_dwell_seconds": int(row[4] or 0),
            }
            for row in rows
        ]
    }


def list_sessions(db: Session, *, store_id: str, run_id: UUID | None = None, limit: int = 100) -> dict[str, Any]:
    filters = [CustomerSession.store_id == store_id]
    if run_id:
        filters.append(CustomerSession.run_id == run_id)
    rows = db.execute(
        select(CustomerSession, SessionPosMatch.invoice_number)
        .outerjoin(SessionPosMatch, SessionPosMatch.session_id == CustomerSession.id)
        .where(*filters)
        .order_by(desc(CustomerSession.started_at))
        .limit(min(limit, 500))
    ).all()
    return {
        "sessions": [
            {
                "id": str(session.id),
                "run_id": str(session.run_id),
                "started_at": session.started_at.isoformat(),
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "dwell_seconds": session.dwell_seconds,
                "matched_invoice": invoice,
                "is_staff": session.is_staff,
                "reentry_count": session.reentry_count,
            }
            for session, invoice in rows
        ]
    }


def run_status(db: Session, run_id: UUID) -> dict[str, Any] | None:
    run = db.get(IngestRun, run_id)
    if run is None:
        return None
    return {
        "run_id": str(run.id),
        "status": run.status,
        "processed_frames": run.processed_frames,
        "events": run.event_count,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error": run.error,
        "config": run.config,
    }


def latest_events_for_sse(db: Session, *, last_seen: datetime | None, limit: int = 25) -> list[dict[str, Any]]:
    payload = list_events(db, after=last_seen, limit=limit)["events"]
    return list(reversed(payload))
