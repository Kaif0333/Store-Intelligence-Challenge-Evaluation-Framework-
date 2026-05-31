import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from glob import glob
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import (
    CustomerSession,
    Event,
    EventType,
    IngestRun,
    PersonTrack,
    SessionZoneVisit,
)
from app.db.session import SessionLocal
from app.services.demo_data import generate_synthetic_run_from_pos
from app.services.redis_stream import safe_redis
from app.services.zone_engine import resolve_zone

logger = logging.getLogger(__name__)


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


@dataclass
class Detection:
    tracker_id: str
    bbox: dict
    confidence: float


class CentroidTracker:
    def __init__(self, max_distance: float = 90.0, max_missing_frames: int = 12) -> None:
        self.max_distance = max_distance
        self.max_missing_frames = max_missing_frames
        self.next_id = 1
        self.objects: dict[str, tuple[float, float, int]] = {}

    def update(self, rects: list[tuple[int, int, int, int]], frame_index: int) -> list[Detection]:
        detections: list[Detection] = []
        used: set[str] = set()
        for x, y, w, h in rects:
            cx = x + w / 2
            cy = y + h / 2
            best_id = None
            best_dist = self.max_distance
            for object_id, (ox, oy, _) in self.objects.items():
                if object_id in used:
                    continue
                dist = ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5
                if dist < best_dist:
                    best_id = object_id
                    best_dist = dist
            if best_id is None:
                best_id = str(self.next_id)
                self.next_id += 1
            self.objects[best_id] = (cx, cy, frame_index)
            used.add(best_id)
            detections.append(
                Detection(
                    tracker_id=best_id,
                    bbox={"x": x, "y": y, "w": w, "h": h},
                    confidence=max(0.45, min(0.9, 1.0 - best_dist / (self.max_distance * 2))),
                )
            )

        expired = [
            object_id
            for object_id, (_, _, last_seen) in self.objects.items()
            if frame_index - last_seen > self.max_missing_frames
        ]
        for object_id in expired:
            self.objects.pop(object_id, None)
        return detections


class MotionDetector:
    def __init__(self):
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OpenCV is not installed") from exc
        self.cv2 = cv2
        self.subtractors: dict[str, object] = {}
        self.trackers: dict[str, CentroidTracker] = {}

    def detect(self, camera_id: str, frame, frame_index: int) -> list[Detection]:
        cv2 = self.cv2
        subtractor = self.subtractors.setdefault(
            camera_id,
            cv2.createBackgroundSubtractorMOG2(history=160, varThreshold=42, detectShadows=True),
        )
        tracker = self.trackers.setdefault(camera_id, CentroidTracker())
        mask = subtractor.apply(frame)
        mask = cv2.medianBlur(mask, 5)
        _, thresh = cv2.threshold(mask, 244, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rects = []
        frame_area = frame.shape[0] * frame.shape[1]
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < max(700, frame_area * 0.001):
                continue
            x, y, w, h = cv2.boundingRect(contour)
            if h < 35 or w < 15:
                continue
            rects.append((x, y, w, h))
        return tracker.update(rects[:8], frame_index)


class YoloDetector:
    def __init__(self, settings: Settings):
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Ultralytics is not installed") from exc
        self.model = YOLO(settings.yolo_model)
        self.confidence = settings.yolo_confidence

    def detect(self, camera_id: str, frame, frame_index: int) -> list[Detection]:
        result = self.model.track(frame, persist=True, classes=[0], conf=self.confidence, verbose=False)[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        xyxy = boxes.xyxy.cpu().numpy().tolist()
        confs = boxes.conf.cpu().numpy().tolist()
        ids = boxes.id.cpu().numpy().tolist() if boxes.id is not None else [None] * len(xyxy)
        detections: list[Detection] = []
        for idx, coords in enumerate(xyxy):
            x1, y1, x2, y2 = coords
            tracker_id = str(int(ids[idx])) if ids[idx] is not None else f"yolo-{frame_index}-{idx}"
            detections.append(
                Detection(
                    tracker_id=tracker_id,
                    bbox={"x": int(x1), "y": int(y1), "w": int(x2 - x1), "h": int(y2 - y1)},
                    confidence=float(confs[idx]),
                )
            )
        return detections


class RunEventWriter:
    def __init__(self, db: Session, run: IngestRun, settings: Settings) -> None:
        self.db = db
        self.run = run
        self.settings = settings
        self.streams = safe_redis()
        self.track_ids: dict[tuple[str, str], uuid.UUID] = {}
        self.session_ids: dict[tuple[str, str], uuid.UUID] = {}
        self.last_zone: dict[tuple[str, str], str | None] = {}
        self.active_visits: dict[tuple[str, str], uuid.UUID] = {}
        self.last_detection_event: dict[tuple[str, str], datetime] = {}

    def handle_detection(
        self,
        *,
        camera_id: str,
        detection: Detection,
        occurred_at: datetime,
        video_ms: int,
        frame_width: int,
        frame_height: int,
    ) -> None:
        key = (camera_id, detection.tracker_id)
        track = self._track_for(key, occurred_at, detection.confidence)
        session = self._session_for(key, occurred_at, camera_id)
        zone = resolve_zone(
            self.db,
            store_id=self.run.store_id,
            camera_id=camera_id,
            bbox=detection.bbox,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        zone_id = zone.id if zone else None

        if self._should_emit_detection(key, occurred_at):
            self._emit(
                EventType.PERSON_DETECTED,
                occurred_at,
                video_ms,
                f"{camera_id}:{detection.tracker_id}:{video_ms}:detected",
                camera_id=camera_id,
                track_id=track.id,
                session_id=session.id,
                zone_id=zone_id,
                bbox=detection.bbox,
                confidence=Decimal(str(round(detection.confidence, 5))),
                payload={"detector": self.run.config.get("detector_mode", "motion")},
            )

        previous_zone = self.last_zone.get(key)
        if previous_zone != zone_id:
            if previous_zone:
                self._close_zone_visit(key, occurred_at)
                self._emit(
                    EventType.ZONE_EXITED,
                    occurred_at,
                    video_ms,
                    f"{camera_id}:{detection.tracker_id}:{video_ms}:zone-exit",
                    camera_id=camera_id,
                    track_id=track.id,
                    session_id=session.id,
                    zone_id=previous_zone,
                )
            if zone_id:
                self._open_zone_visit(key, session.id, zone_id, occurred_at)
                self._emit(
                    EventType.ZONE_ENTERED,
                    occurred_at,
                    video_ms,
                    f"{camera_id}:{detection.tracker_id}:{video_ms}:zone-enter",
                    camera_id=camera_id,
                    track_id=track.id,
                    session_id=session.id,
                    zone_id=zone_id,
                )
                if zone and zone.zone_type == "entrance":
                    self._emit(EventType.STORE_ENTRY, occurred_at, video_ms, f"{camera_id}:{detection.tracker_id}:{video_ms}:store-entry", camera_id=camera_id, track_id=track.id, session_id=session.id, zone_id=zone_id)
                if zone and zone.zone_type == "checkout":
                    self._emit(EventType.CHECKOUT_VISIT, occurred_at, video_ms, f"{camera_id}:{detection.tracker_id}:{video_ms}:checkout", camera_id=camera_id, track_id=track.id, session_id=session.id, zone_id=zone_id)
            self.last_zone[key] = zone_id

    def close(self, finished_at: datetime) -> None:
        for key, session_id in list(self.session_ids.items()):
            session = self.db.get(CustomerSession, session_id)
            if not session:
                continue
            self._close_zone_visit(key, finished_at)
            track_id = self.track_ids.get(key)
            track = self.db.get(PersonTrack, track_id) if track_id else None
            if track:
                dwell_minutes = (track.last_seen_at - track.first_seen_at).total_seconds() / 60
                if dwell_minutes >= self.settings.staff_min_dwell_minutes:
                    track.is_staff = True
                    track.staff_reason = f"Dwell >= {self.settings.staff_min_dwell_minutes} minutes"
                    session.is_staff = True
            session.ended_at = track.last_seen_at if track else finished_at
            session.dwell_seconds = int(((session.ended_at or finished_at) - session.started_at).total_seconds())
            session.exit_camera_id = key[0]
            self._emit(
                EventType.SESSION_ENDED,
                session.ended_at or finished_at,
                0,
                f"{key[0]}:{key[1]}:session-ended",
                camera_id=key[0],
                track_id=track_id,
                session_id=session.id,
            )
        self.db.flush()

    def _track_for(self, key: tuple[str, str], occurred_at: datetime, confidence: float) -> PersonTrack:
        if key in self.track_ids:
            track = self.db.get(PersonTrack, self.track_ids[key])
            if track is None:
                raise RuntimeError("Track disappeared during run")
            track.last_seen_at = max(track.last_seen_at, occurred_at)
            track.max_confidence = max(track.max_confidence or Decimal("0"), Decimal(str(round(confidence, 5))))
            return track
        camera_id, tracker_id = key
        track = PersonTrack(
            run_id=self.run.id,
            camera_id=camera_id,
            tracker_id=tracker_id,
            first_seen_at=occurred_at,
            last_seen_at=occurred_at,
            max_confidence=Decimal(str(round(confidence, 5))),
        )
        self.db.add(track)
        self.db.flush()
        self.track_ids[key] = track.id
        return track

    def _session_for(self, key: tuple[str, str], occurred_at: datetime, camera_id: str) -> CustomerSession:
        if key in self.session_ids:
            session = self.db.get(CustomerSession, self.session_ids[key])
            if session is None:
                raise RuntimeError("Session disappeared during run")
            return session
        track_id = self.track_ids[key]
        session = CustomerSession(
            run_id=self.run.id,
            store_id=self.run.store_id,
            started_at=occurred_at,
            entry_camera_id=camera_id,
        )
        self.db.add(session)
        self.db.flush()
        self.session_ids[key] = session.id
        self._emit(EventType.SESSION_STARTED, occurred_at, 0, f"{camera_id}:{key[1]}:session-start", camera_id=camera_id, track_id=track_id, session_id=session.id)
        return session

    def _open_zone_visit(self, key: tuple[str, str], session_id: uuid.UUID, zone_id: str, entered_at: datetime) -> None:
        visit = SessionZoneVisit(session_id=session_id, zone_id=zone_id, entered_at=entered_at)
        self.db.add(visit)
        self.db.flush()
        self.active_visits[key] = visit.id

    def _close_zone_visit(self, key: tuple[str, str], exited_at: datetime) -> None:
        visit_id = self.active_visits.pop(key, None)
        if not visit_id:
            return
        visit = self.db.get(SessionZoneVisit, visit_id)
        if visit:
            visit.exited_at = exited_at
            visit.dwell_seconds = int((exited_at - visit.entered_at).total_seconds())

    def _should_emit_detection(self, key: tuple[str, str], occurred_at: datetime) -> bool:
        last = self.last_detection_event.get(key)
        if last is None or occurred_at - last >= timedelta(seconds=5):
            self.last_detection_event[key] = occurred_at
            return True
        return False

    def _emit(
        self,
        event_type: EventType,
        occurred_at: datetime,
        video_ms: int,
        source_key: str,
        *,
        camera_id: str | None = None,
        track_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        zone_id: str | None = None,
        bbox: dict | None = None,
        confidence: Decimal | None = None,
        payload: dict | None = None,
    ) -> None:
        full_key = f"{self.run.id}:{source_key}"
        if self.db.scalar(select(Event.id).where(Event.source_event_key == full_key).limit(1)):
            return
        event = Event(
            run_id=self.run.id,
            event_type=event_type,
            store_id=self.run.store_id,
            camera_id=camera_id,
            track_id=track_id,
            session_id=session_id,
            zone_id=zone_id,
            occurred_at=occurred_at,
            video_ms=video_ms,
            bbox=bbox,
            confidence=confidence,
            payload=_json_safe(payload or {}),
            source_event_key=full_key,
        )
        self.db.add(event)
        self.db.flush()
        if self.streams:
            self.streams.publish_event(
                {
                    "id": str(event.id),
                    "event_type": event.event_type.value,
                    "run_id": str(event.run_id),
                    "camera_id": event.camera_id,
                    "session_id": str(event.session_id) if event.session_id else None,
                    "occurred_at": event.occurred_at.isoformat(),
                    "zone_id": event.zone_id,
                    "payload": event.payload,
                }
            )


def _camera_id_from_path(path: str) -> str:
    name = Path(path).stem.upper().replace("_", " ")
    return name if name.startswith("CAM ") else "CAM 1"


def _make_detector(settings: Settings):
    if settings.detector_mode == "synthetic":
        return None
    if settings.detector_mode in {"auto", "yolo"}:
        try:
            return YoloDetector(settings)
        except Exception as exc:
            if settings.detector_mode == "yolo":
                raise
            logger.info("YOLO unavailable, falling back to motion detector: %s", exc)
    return MotionDetector()


def process_run(run_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        run = db.get(IngestRun, uuid.UUID(str(run_id)))
        if run is None:
            logger.error("Run %s not found", run_id)
            return
        run.status = "running"
        run.error = None
        db.commit()

        try:
            _process_run(db, settings, run)
            run.status = "completed"
            run.finished_at = datetime.now(tz=ZoneInfo(settings.local_timezone))
            run.event_count = int(db.scalar(select(func.count()).select_from(Event).where(Event.run_id == run.id)) or 0)
            db.commit()
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            run.status = "failed"
            run.error = str(exc)
            db.commit()


def _process_run(db: Session, settings: Settings, run: IngestRun) -> None:
    if run.config.get("detector_mode") == "synthetic":
        generate_synthetic_run_from_pos(db, settings, run)
        return

    try:
        import cv2
    except ImportError:
        logger.warning("OpenCV missing, using synthetic run")
        generate_synthetic_run_from_pos(db, settings, run)
        return

    video_glob = run.config.get("video_glob") or str(settings.videos_path / "*.mp4")
    video_paths = sorted(glob(video_glob))
    if not video_paths:
        logger.warning("No videos matched %s, using synthetic run", video_glob)
        generate_synthetic_run_from_pos(db, settings, run)
        return

    detector = _make_detector(settings)
    if detector is None:
        generate_synthetic_run_from_pos(db, settings, run)
        return

    writer = RunEventWriter(db, run, settings)
    local_tz = ZoneInfo(settings.local_timezone)
    base_time = run.started_at or datetime.now(tz=local_tz)
    sample_fps = float(run.config.get("sample_fps") or settings.default_sample_fps)
    max_seconds = run.config.get("max_seconds", settings.default_max_seconds)
    processed_frames = 0

    for video_path in video_paths:
        camera_id = _camera_id_from_path(video_path)
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        stride = max(1, int(round(fps / sample_fps)))
        frame_index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % stride != 0:
                frame_index += 1
                continue
            video_seconds = frame_index / fps
            if max_seconds and video_seconds > int(max_seconds):
                break
            occurred_at = base_time + timedelta(seconds=video_seconds)
            detections = detector.detect(camera_id, frame, frame_index)
            height, width = frame.shape[:2]
            for detection in detections:
                writer.handle_detection(
                    camera_id=camera_id,
                    detection=detection,
                    occurred_at=occurred_at,
                    video_ms=int(video_seconds * 1000),
                    frame_width=width,
                    frame_height=height,
                )
            processed_frames += 1
            if processed_frames % 50 == 0:
                run.processed_frames = processed_frames
                run.event_count = int(db.scalar(select(func.count()).select_from(Event).where(Event.run_id == run.id)) or 0)
                db.commit()
            frame_index += 1
        cap.release()

    writer.close(datetime.now(tz=local_tz))
    run.processed_frames = processed_frames
    current_events = int(db.scalar(select(func.count()).select_from(Event).where(Event.run_id == run.id)) or 0)
    if current_events == 0:
        logger.warning("Run %s produced no CV events; generating input-derived fallback events", run.id)
        generate_synthetic_run_from_pos(db, settings, run)
    db.commit()
