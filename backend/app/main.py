import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.db.session import SessionLocal, init_db
from app.services.demo_data import ensure_bootstrap_run
from app.services.pos_importer import import_pos_csv
from app.services.seeding import seed_reference_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Initializing database and reference data")
    init_db()
    with SessionLocal() as db:
        seed_reference_data(db, settings)
        imported = import_pos_csv(db, settings)
        logger.info("POS rows available: %s", imported)
        if settings.auto_bootstrap_demo:
            run_id = ensure_bootstrap_run(db, settings)
            if run_id:
                logger.info("Bootstrap run ready: %s", run_id)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()

