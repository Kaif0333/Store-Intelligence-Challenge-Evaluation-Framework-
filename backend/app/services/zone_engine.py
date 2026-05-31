from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Zone


def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, point in enumerate(polygon):
        xi, yi = point
        xj, yj = polygon[j]
        intersects = (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        if intersects:
            inside = not inside
        j = i
    return inside


def _normalize(value: float, size: int) -> float:
    if value <= 1.0:
        return value
    return value / max(size, 1)


def bottom_center(bbox: dict, frame_width: int, frame_height: int) -> tuple[float, float]:
    x = float(bbox["x"])
    y = float(bbox["y"])
    w = float(bbox["w"])
    h = float(bbox["h"])
    cx = _normalize(x + w / 2, frame_width)
    by = _normalize(y + h, frame_height)
    return cx, by


def resolve_zone(
    db: Session,
    *,
    store_id: str,
    camera_id: str,
    bbox: dict,
    frame_width: int,
    frame_height: int,
) -> Zone | None:
    cx, by = bottom_center(bbox, frame_width, frame_height)
    zones = db.execute(
        select(Zone)
        .where(Zone.store_id == store_id, or_(Zone.camera_id == camera_id, Zone.camera_id.is_(None)))
        .order_by(Zone.camera_id.is_(None), Zone.id)
    ).scalars()
    fallback: Zone | None = None
    for zone in zones:
        if zone.zone_type == "foh":
            fallback = zone
        polygon = zone.polygon
        if isinstance(polygon, dict):
            polygon = polygon.get("points", [])
        if polygon and _point_in_polygon(cx, by, polygon):
            return zone
    return fallback

