import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Camera, Store, Zone


DEFAULT_CAMERA_ROLES = {
    "CAM 1": "entrance",
    "CAM 2": "front_of_house",
    "CAM 3": "product_wall",
    "CAM 4": "checkout",
    "CAM 5": "checkout_pmu",
}


def _load_zone_config(path: Path) -> list[dict]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")).get("zones", [])
    return []


def seed_reference_data(db: Session, settings: Settings) -> None:
    store = db.get(Store, settings.store_id)
    if store is None:
        db.add(Store(id=settings.store_id, name=settings.store_name, city=settings.store_city))
        db.flush()

    video_files = {path.stem.upper(): str(path) for path in settings.videos_path.glob("CAM *.mp4")}
    for camera_id, role in DEFAULT_CAMERA_ROLES.items():
        camera = db.get(Camera, camera_id)
        if camera is None:
            db.add(
                Camera(
                    id=camera_id,
                    store_id=settings.store_id,
                    name=camera_id,
                    video_path=video_files.get(camera_id),
                    role=role,
                )
            )
        else:
            camera.video_path = video_files.get(camera_id, camera.video_path)
            camera.role = role

    db.flush()
    zones = _load_zone_config(settings.layout_path)
    for zone_data in zones:
        zone_id = zone_data["id"]
        zone = db.get(Zone, zone_id)
        payload = {
            "store_id": zone_data.get("store_id", settings.store_id),
            "camera_id": zone_data.get("camera_id"),
            "name": zone_data["name"],
            "zone_type": zone_data["zone_type"],
            "polygon": zone_data["polygon"],
        }
        if zone is None:
            db.add(Zone(id=zone_id, **payload))
        else:
            for key, value in payload.items():
                setattr(zone, key, value)

    db.commit()


def zone_id_for(db: Session, zone_type: str, store_id: str) -> str | None:
    return db.scalar(
        select(Zone.id)
        .where(Zone.store_id == store_id, Zone.zone_type == zone_type)
        .order_by(Zone.camera_id.is_not(None), Zone.id)
        .limit(1)
    )
