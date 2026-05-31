from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Purplle Store Intelligence"
    environment: str = "local"
    database_url: str = Field(
        default="postgresql+psycopg2://storeintel:storeintel@postgres:5432/storeintel"
    )
    redis_url: str = "redis://redis:6379/0"
    cors_origins: str = "*"

    store_id: str = "ST1008"
    store_name: str = "Brigade_Bangalore"
    store_city: str = "Bangalore"
    local_timezone: str = "Asia/Kolkata"

    pos_csv_path: str = "/data/pos/transactions.csv"
    video_dir: str = "/data/videos"
    layout_config_path: str = "/app/config/layout.zones.json"

    auto_bootstrap_demo: bool = True
    default_sample_fps: float = 2.0
    default_max_seconds: int | None = 180
    reentry_grace_minutes: int = 10
    staff_min_dwell_minutes: int = 35

    detector_mode: str = "auto"  # auto, yolo, motion, synthetic
    yolo_model: str = "yolo11n.pt"
    yolo_confidence: float = 0.35
    event_stream_name: str = "storeintel:events"
    ingest_stream_name: str = "storeintel:ingest_runs"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def pos_path(self) -> Path:
        return Path(self.pos_csv_path)

    @property
    def videos_path(self) -> Path:
        return Path(self.video_dir)

    @property
    def layout_path(self) -> Path:
        return Path(self.layout_config_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()

