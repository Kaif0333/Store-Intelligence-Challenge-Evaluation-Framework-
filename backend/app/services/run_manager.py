from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import IngestRun
from app.schemas import IngestRunCreate
from app.services.redis_stream import safe_redis


def create_ingest_run(db: Session, settings: Settings, payload: IngestRunCreate) -> IngestRun:
    config = {
        "video_glob": payload.video_glob,
        "sample_fps": payload.sample_fps,
        "max_seconds": payload.max_seconds,
        "detector_mode": payload.detector_mode or settings.detector_mode,
    }
    run = IngestRun(
        store_id=payload.store_id,
        status="queued",
        started_at=datetime.now(tz=ZoneInfo(settings.local_timezone)),
        config=config,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if payload.auto_start:
        streams = safe_redis()
        if streams is None or not streams.queue_ingest_run(str(run.id), config):
            run.status = "queued_no_worker"
            run.error = "Redis unavailable. Start worker or POST again after Redis is available."
            db.commit()
            db.refresh(run)
    return run


def get_run(db: Session, run_id: UUID) -> IngestRun | None:
    return db.get(IngestRun, run_id)

