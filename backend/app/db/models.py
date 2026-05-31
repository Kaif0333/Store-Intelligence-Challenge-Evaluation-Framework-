import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import GUID


class Base(DeclarativeBase):
    pass


class EventType(str, enum.Enum):
    PERSON_DETECTED = "person_detected"
    ZONE_ENTERED = "zone_entered"
    ZONE_EXITED = "zone_exited"
    STORE_ENTRY = "store_entry"
    STORE_EXIT = "store_exit"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    CHECKOUT_VISIT = "checkout_visit"
    TRANSACTION_MATCHED = "transaction_matched"
    ANOMALY_DETECTED = "anomaly_detected"


event_type_enum = Enum(EventType, name="event_type", values_callable=lambda values: [v.value for v in values])


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    video_path: Mapped[str | None] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, nullable=False)


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"), nullable=False)
    camera_id: Mapped[str | None] = mapped_column(String, ForeignKey("cameras.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    zone_type: Mapped[str] = mapped_column(String, nullable=False)
    polygon: Mapped[dict | list] = mapped_column(JSON, nullable=False)


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    processed_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PersonTrack(Base):
    __tablename__ = "person_tracks"
    __table_args__ = (UniqueConstraint("run_id", "camera_id", "tracker_id", name="uq_track_source"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("ingest_runs.id"), nullable=False)
    camera_id: Mapped[str] = mapped_column(String, ForeignKey("cameras.id"), nullable=False)
    tracker_id: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    is_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    staff_reason: Mapped[str | None] = mapped_column(Text)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("ingest_runs.id"), nullable=False)
    event_type: Mapped[EventType] = mapped_column(event_type_enum, nullable=False)
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"), nullable=False)
    camera_id: Mapped[str | None] = mapped_column(String, ForeignKey("cameras.id"))
    track_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("person_tracks.id"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    zone_id: Mapped[str | None] = mapped_column(String, ForeignKey("zones.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    video_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[dict | None] = mapped_column(JSON)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_event_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class CustomerSession(Base):
    __tablename__ = "customer_sessions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("ingest_runs.id"), nullable=False)
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_camera_id: Mapped[str | None] = mapped_column(String, ForeignKey("cameras.id"))
    exit_camera_id: Mapped[str | None] = mapped_column(String, ForeignKey("cameras.id"))
    dwell_seconds: Mapped[int | None] = mapped_column(Integer)
    is_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reentry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    group_id: Mapped[uuid.UUID | None] = mapped_column(GUID())


class SessionZoneVisit(Base):
    __tablename__ = "session_zone_visits"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("customer_sessions.id"), nullable=False)
    zone_id: Mapped[str] = mapped_column(String, ForeignKey("zones.id"), nullable=False)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dwell_seconds: Mapped[int | None] = mapped_column(Integer)


class PosOrderItem(Base):
    __tablename__ = "pos_order_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(String, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String, nullable=False)
    order_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    salesperson_id: Mapped[str | None] = mapped_column(String)
    employee_code: Mapped[str | None] = mapped_column(String)
    salesperson_name: Mapped[str | None] = mapped_column(String)
    sku: Mapped[str | None] = mapped_column(String)
    product_name: Mapped[str | None] = mapped_column(Text)
    qty: Mapped[int | None] = mapped_column(Integer)
    gmv: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    nmv: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))


class SessionPosMatch(Base):
    __tablename__ = "session_pos_matches"

    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("customer_sessions.id"), primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String, primary_key=True)
    match_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    match_reason: Mapped[str] = mapped_column(Text, nullable=False)


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("ingest_runs.id"), nullable=False)
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

