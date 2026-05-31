# Purplle Store Intelligence MVP

AI-powered store intelligence system for the Purplle Tech Challenge 2026. The app turns CCTV/POS inputs into structured events, session metrics, funnel analytics, anomalies, and a live dashboard.

## Run

```bash
docker compose up --build
```

Open:

- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Dashboard: http://localhost:3000
- Mandatory endpoint: http://localhost:8000/Metrics

The Compose file mounts the provided local CSV and CCTV folder from this workspace. Videos, CSVs, spreadsheets, and PDFs are intentionally ignored by Git and Docker build context.

## Local Backend Checks

```bash
$env:PYTHONPATH="backend"
pytest backend/tests -q
```

## Ingest A Video Run

```bash
curl -X POST http://localhost:8000/ingest/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"store_id\":\"ST1008\",\"video_glob\":\"/data/videos/*.mp4\",\"sample_fps\":2,\"max_seconds\":180,\"auto_start\":true}"
```

The API creates the run and queues it in Redis. The worker consumes the run, processes videos, and writes normalized events/sessions to Postgres.

