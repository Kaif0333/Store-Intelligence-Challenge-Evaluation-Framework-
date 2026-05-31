import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import PosOrderItem


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _decimal(value: str | None) -> Decimal | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _int(value: str | None) -> int | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def parse_order_ts(order_date: str, order_time: str, timezone: str) -> datetime:
    parsed = datetime.strptime(f"{order_date} {order_time}", "%d-%m-%Y %H:%M:%S")
    return parsed.replace(tzinfo=ZoneInfo(timezone))


def import_pos_csv(db: Session, settings: Settings) -> int:
    existing = db.scalar(select(func.count()).select_from(PosOrderItem))
    if existing:
        return int(existing)

    csv_path = Path(settings.pos_csv_path)
    if not csv_path.exists():
        return 0

    inserted = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            invoice = _clean(row.get("invoice_number"))
            order_id = _clean(row.get("order_id"))
            if not invoice or not order_id:
                continue

            item = PosOrderItem(
                store_id=_clean(row.get("store_id")) or settings.store_id,
                order_id=order_id,
                invoice_number=invoice,
                order_ts=parse_order_ts(row["order_date"], row["order_time"], settings.local_timezone),
                salesperson_id=_clean(row.get("salesperson_id")),
                employee_code=_clean(row.get("employee_code")),
                salesperson_name=_clean(row.get("salesperson_name")),
                sku=_clean(row.get("sku")),
                product_name=_clean(row.get("product_name")),
                qty=_int(row.get("qty")),
                gmv=_decimal(row.get("GMV")),
                nmv=_decimal(row.get("NMV")),
            )
            db.add(item)
            inserted += 1

    db.commit()
    return inserted

