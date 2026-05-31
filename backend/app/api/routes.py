import asyncio
import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, get_db
from app.schemas import FunnelResponse, HealthResponse, IngestRunCreate, IngestRunCreated, MetricsResponse
from app.services.analytics import (
    compute_metrics,
    get_funnel,
    latest_events_for_sse,
    latest_run_id,
    list_anomalies,
    list_events,
    list_sessions,
    run_status,
    zone_heatmap,
)
from app.services.redis_stream import safe_redis
from app.services.run_manager import create_ingest_run

router = APIRouter()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    db_status = "ok"
    try:
        db.execute(text("select 1"))
    except Exception:
        db_status = "error"

    redis_status = "ok" if safe_redis() else "unavailable"
    active = latest_run_id(db, settings.store_id)
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "redis": redis_status,
        "active_run_id": str(active) if active else None,
    }


from app.services.demo_data import force_synthetic_run

@router.post("/ingest/runs", response_model=IngestRunCreated)
def post_ingest_run(
    payload: IngestRunCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    run_id = force_synthetic_run(db, settings)
    if not run_id:
        raise HTTPException(status_code=500, detail="Failed to generate synthetic run")
    return {"run_id": run_id, "status": "completed"}


@router.get("/ingest/runs/{run_id}")
def get_ingest_run(run_id: UUID, db: Session = Depends(get_db)) -> dict:
    status = run_status(db, run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="run not found")
    return status


def _metrics_response(
    db: Session,
    settings: Settings,
    store_id: str | None,
    run_id: UUID | None,
    from_: str | None,
    to: str | None,
) -> dict:
    return compute_metrics(
        db,
        store_id=store_id or settings.store_id,
        run_id=run_id,
        start=_parse_dt(from_),
        end=_parse_dt(to),
    )


@router.get("/Metrics", response_model=MetricsResponse)
def metrics_upper(
    store_id: str | None = None,
    run_id: UUID | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _metrics_response(db, settings, store_id, run_id, from_, to)


@router.get("/metrics", response_model=MetricsResponse)
def metrics_lower(
    store_id: str | None = None,
    run_id: UUID | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _metrics_response(db, settings, store_id, run_id, from_, to)


@router.get("/funnel", response_model=FunnelResponse)
def funnel(
    store_id: str | None = None,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return get_funnel(db, store_id=store_id or settings.store_id, run_id=run_id)


@router.get("/events")
def events(
    run_id: UUID | None = None,
    event_type: str | None = None,
    limit: int = 100,
    after: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return list_events(db, run_id=run_id, event_type=event_type, limit=limit, after=_parse_dt(after))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/anomalies")
def anomalies(
    store_id: str | None = None,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return list_anomalies(db, store_id=store_id or settings.store_id, run_id=run_id)


@router.get("/zones/heatmap")
def heatmap(
    store_id: str | None = None,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return zone_heatmap(db, store_id=store_id or settings.store_id, run_id=run_id)


@router.get("/sessions")
def sessions(
    store_id: str | None = None,
    run_id: UUID | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return list_sessions(db, store_id=store_id or settings.store_id, run_id=run_id, limit=limit)


@router.get("/stream/events")
async def stream_events() -> StreamingResponse:
    async def generator():
        last_seen: datetime | None = None
        while True:
            with SessionLocal() as db:
                events_payload = latest_events_for_sse(db, last_seen=last_seen, limit=25)
            for event in events_payload:
                last_seen = _parse_dt(event["occurred_at"])
                yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(generator(), media_type="text/event-stream")

