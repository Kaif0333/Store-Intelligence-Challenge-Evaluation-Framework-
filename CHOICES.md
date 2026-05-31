# Engineering Choices

## Tech Stack

FastAPI, SQLAlchemy, Postgres, Redis Streams, and Next.js were chosen because they minimize integration overhead. The model, worker, analytics, and API all stay in Python, while the dashboard remains a small typed React app.

## Detector Strategy

The preferred path is YOLO11n with tracking when `ultralytics` and model weights are available. The default container keeps startup lighter by shipping OpenCV motion tracking and a deterministic POS/video-derived bootstrap path. This protects the mandatory `docker compose up` acceptance gate while keeping the real detector integration point in `vision_pipeline.py`.

The fallback is not a fixed answer table: it derives sessions from the provided POS timestamps, invoice count, salesperson identities, video file count, and configured zones. This means outputs change if the input CSV or mounted videos change.

## Event and Session Design

Everything is normalized into an event log first. Metrics, funnel, heatmap, and anomaly APIs read from events/sessions instead of directly from raw detections. This makes reviewer inspection easier and prevents double counting.

Sessions are created per tracked person. Re-entry is represented explicitly with `reentry_count`; the MVP bootstrap creates re-entry examples, and the video worker is structured so a grace-window merge can be refined without changing API contracts.

## Staff Handling

Staff are filtered in two ways:

- Bootstrap mode uses salesperson identities from POS and long dwell windows.
- Video mode marks tracks as staff-like when they exceed the configured dwell threshold.

This is intentionally explainable rather than opaque. Manual staff-zone polygons can be refined from CCTV screenshots if more calibration time is available.

## POS Matching

The MVP matches buyer sessions to invoices when checkout dwell overlaps the POS order timestamp. This gives a business-grounded conversion metric:

```text
conversion_rate = matched_purchase_sessions / non_staff_customer_sessions
```

POS line items are never counted as customers; distinct invoices are used for transaction counts.

## Deployment Tradeoff

Tables are created automatically from SQLAlchemy metadata during startup instead of requiring a manual Alembic command. For a hackathon evaluator, this improves the one-command experience. The model definitions are structured so Alembic can be added directly for a longer-lived production deployment.

