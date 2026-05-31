import json
import logging
import time

from redis.exceptions import BusyLoadingError, ResponseError

from app.core.config import get_settings
from app.db.session import SessionLocal, init_db
from app.services.demo_data import ensure_bootstrap_run
from app.services.pos_importer import import_pos_csv
from app.services.redis_stream import RedisStreams
from app.services.seeding import seed_reference_data
from app.services.vision_pipeline import process_run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def _bootstrap() -> None:
    settings = get_settings()
    init_db()
    with SessionLocal() as db:
        seed_reference_data(db, settings)
        import_pos_csv(db, settings)
        if settings.auto_bootstrap_demo:
            ensure_bootstrap_run(db, settings)


def main() -> None:
    _bootstrap()
    settings = get_settings()
    streams = RedisStreams()
    group = "ingest-workers"
    consumer = "worker-1"
    while True:
        try:
            try:
                streams.client.xgroup_create(settings.ingest_stream_name, group, id="0", mkstream=True)
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
            logger.info("Worker listening on %s", settings.ingest_stream_name)
            break
        except BusyLoadingError:
            time.sleep(2)
        except Exception as exc:
            logger.warning("Redis not ready yet: %s", exc)
            time.sleep(2)

    while True:
        try:
            response = streams.client.xreadgroup(
                group,
                consumer,
                {settings.ingest_stream_name: ">"},
                count=1,
                block=5000,
            )
            if not response:
                continue
            for _, messages in response:
                for message_id, fields in messages:
                    run_id = fields["run_id"]
                    logger.info("Processing run %s with config %s", run_id, fields.get("config"))
                    process_run(run_id)
                    streams.client.xack(settings.ingest_stream_name, group, message_id)
        except Exception as exc:
            logger.exception("Worker loop error: %s", exc)
            time.sleep(3)


if __name__ == "__main__":
    main()

