import json
import logging
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RedisStreams:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = Redis.from_url(self.settings.redis_url, decode_responses=True)

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except RedisError as exc:
            logger.warning("Redis ping failed: %s", exc)
            return False

    def queue_ingest_run(self, run_id: str, config: dict[str, Any]) -> bool:
        try:
            self.client.xadd(
                self.settings.ingest_stream_name,
                {"run_id": run_id, "config": json.dumps(config)},
                maxlen=500,
                approximate=True,
            )
            return True
        except RedisError as exc:
            logger.warning("Could not queue ingest run %s: %s", run_id, exc)
            return False

    def publish_event(self, event: dict[str, Any]) -> bool:
        try:
            self.client.xadd(
                self.settings.event_stream_name,
                {"event": json.dumps(event, default=str)},
                maxlen=5000,
                approximate=True,
            )
            return True
        except RedisError as exc:
            logger.debug("Could not publish event: %s", exc)
            return False


def safe_redis() -> RedisStreams | None:
    try:
        streams = RedisStreams()
        if streams.ping():
            return streams
    except RedisError as exc:
        logger.warning("Redis unavailable: %s", exc)
    return None

