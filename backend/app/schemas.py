from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class IngestRunCreate(BaseModel):
    store_id: str = "ST1008"
    video_glob: str = "/data/videos/*.mp4"
    sample_fps: float = Field(default=2.0, gt=0, le=15)
    max_seconds: int | None = Field(default=None, ge=1)
    auto_start: bool = True
    detector_mode: str | None = None


class IngestRunCreated(BaseModel):
    run_id: UUID
    status: str


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
    active_run_id: str | None


class MetricsResponse(BaseModel):
    store_id: str
    run_id: str | None
    footfall: int
    customer_sessions: int
    staff_tracks: int
    pos_invoices: int
    matched_purchases: int
    conversion_rate: float
    avg_dwell_seconds: int
    active_visitors: int
    anomaly_count: int


class FunnelStep(BaseModel):
    name: str
    count: int


class FunnelResponse(BaseModel):
    run_id: str | None
    steps: list[FunnelStep]


class GenericPayload(BaseModel):
    model_config = {"extra": "allow"}

    data: dict[str, Any] = {}

