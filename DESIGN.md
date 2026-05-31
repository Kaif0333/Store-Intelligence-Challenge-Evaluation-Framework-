# Store Intelligence System Design

## Architecture

The system is a five-service Docker Compose app:

- `api`: FastAPI service exposing health, ingest, metrics, funnel, events, anomaly, session, heatmap, and SSE endpoints.
- `worker`: Python worker that consumes ingest jobs from Redis Streams and processes CCTV videos.
- `postgres`: relational source of truth for stores, cameras, zones, runs, tracks, events, sessions, POS items, matches, and anomalies.
- `redis`: durable lightweight stream for ingest jobs and live event fanout.
- `frontend`: Next.js dashboard for operators and reviewers.

## Data Flow

1. Provided inputs are mounted into containers as read-only files: `/data/videos/*.mp4`, `/data/pos/transactions.csv`, and `/app/config/layout.zones.json`.
2. API startup creates tables, seeds store/camera/zone metadata, imports POS rows, and creates a deterministic bootstrap run from real POS/video metadata so `/Metrics` and `/events` are useful immediately.
3. `POST /ingest/runs` creates an `ingest_runs` row and pushes the run config to Redis.
4. The worker reads the run, samples frames, tracks people, resolves zone membership from bottom-center points, and writes structured events.
5. Session logic maps tracks into customer sessions, zone visits, checkout visits, staff-like tracks, transaction matches, and anomaly events.
6. Analytics endpoints compute values from persisted sessions/events instead of returning hardcoded constants.
7. The dashboard polls REST endpoints and can start a new video processing run.

## Core Models

The implementation follows the schema from the blueprint:

- `person_tracks`: per-camera tracked people with staff classification.
- `events`: normalized event log with unique source keys for idempotency.
- `customer_sessions`: visitor/staff sessions with dwell and re-entry fields.
- `session_zone_visits`: zone-level dwell for heatmaps and funnel logic.
- `pos_order_items`: imported POS line items.
- `session_pos_matches`: session to invoice joins based on checkout/order-time proximity.
- `anomalies`: queue/conversion/coverage findings with JSON evidence.

## API Surface

- `GET /health`
- `POST /ingest/runs`
- `GET /ingest/runs/{run_id}`
- `GET /Metrics`
- `GET /metrics`
- `GET /funnel`
- `GET /events`
- `GET /anomalies`
- `GET /zones/heatmap`
- `GET /sessions`
- `GET /stream/events`

## Scoring Alignment

- Detection pipeline produces structured events with event type, camera, track, session, zone, timestamp, bbox, confidence, and source key.
- Business metrics are session-based and avoid counting POS line items as customers.
- Funnel metrics use sessions and zone visits, so one customer with many events is counted once.
- The system is stable if YOLO weights are absent: it uses OpenCV motion tracking, and if video/CV is unavailable it still generates input-derived bootstrap events.
- Tests cover POS import, session conversion, funnel ordering, heatmap generation, and zone mapping.

