import os
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{Path(tempfile.gettempdir()).as_posix()}/storeintel_tests.db")
os.environ.setdefault("LAYOUT_CONFIG_PATH", "config/layout.zones.json")

from app.core.config import Settings
from app.db.models import Base
from app.db.session import SessionLocal, engine, init_db
from app.services.analytics import compute_metrics, get_funnel, zone_heatmap
from app.services.demo_data import ensure_bootstrap_run
from app.services.pos_importer import import_pos_csv
from app.services.seeding import seed_reference_data
from app.services.zone_engine import resolve_zone


def _sample_pos_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "order_id,coupon_code,offer_name,discount_code,invoice_number,invoice_type,order_date,order_time,return_id,store_id,store_name,city,customer_name,customer_number,sku,product_id,ean,product_name,brand_name,dep_name,sub_category,brand_type,tax,hsn_code,salesperson_id,employee_code,salesperson_name,qty,GMV,NMV,coupon_amount,item_promotion,amt_without_gwp,total_amount,pb_eb_sale,week_assigned,tax_m,taxable_amt,tax_amt",
                "1,,,,INV001,sales,10-04-2026,12:15:05,,ST1008,Brigade_Bangalore,Bangalore,Guest,999,SKU1,1,1,Lipstick,Brand,makeup,Lipstick,PB,18,1,101,CL101,Asha,1,500,450,0,0,450,450,450,,1.18,381,69",
                "2,,,,INV002,sales,10-04-2026,12:45:05,,ST1008,Brigade_Bangalore,Bangalore,Guest,999,SKU2,2,2,Serum,Brand,skin,Serum,PB,18,1,102,CL102,Meera,1,800,700,0,0,700,700,700,,1.18,593,107",
            ]
        ),
        encoding="utf-8",
    )


def _settings(tmp_path: Path) -> Settings:
    pos_path = tmp_path / "pos.csv"
    _sample_pos_csv(pos_path)
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        pos_csv_path=str(pos_path),
        video_dir=str(tmp_path / "videos"),
        layout_config_path="config/layout.zones.json",
        auto_bootstrap_demo=True,
    )


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()


def test_bootstrap_metrics_are_session_based(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SessionLocal() as db:
        seed_reference_data(db, settings)
        assert import_pos_csv(db, settings) == 2
        assert ensure_bootstrap_run(db, settings) is not None

        metrics = compute_metrics(db, store_id=settings.store_id)
        assert metrics["pos_invoices"] == 2
        assert metrics["matched_purchases"] == 2
        assert metrics["customer_sessions"] > metrics["matched_purchases"]
        assert 0 < metrics["conversion_rate"] < 1


def test_funnel_and_heatmap_are_consistent(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SessionLocal() as db:
        seed_reference_data(db, settings)
        import_pos_csv(db, settings)
        ensure_bootstrap_run(db, settings)

        funnel = get_funnel(db, store_id=settings.store_id)
        steps = {step["name"]: step["count"] for step in funnel["steps"]}
        assert steps["entered"] >= steps["browsed"] >= steps["checkout_visit"] >= steps["purchased"]

        heatmap = zone_heatmap(db, store_id=settings.store_id)
        assert any(zone["zone_type"] == "product_wall" for zone in heatmap["zones"])


def test_zone_resolution_uses_bottom_center(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SessionLocal() as db:
        seed_reference_data(db, settings)
        zone = resolve_zone(
            db,
            store_id=settings.store_id,
            camera_id="CAM 4",
            bbox={"x": 850, "y": 250, "w": 80, "h": 260},
            frame_width=1000,
            frame_height=800,
        )
        assert zone is not None
        assert zone.zone_type == "checkout"

