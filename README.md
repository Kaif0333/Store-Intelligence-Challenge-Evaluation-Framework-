# Purplle Store Intelligence MVP

AI-powered store intelligence system for the Purplle Tech Challenge 2026. The app turns CCTV/POS inputs into structured events, session metrics, funnel analytics, anomalies, and a live dashboard.

## 🌐 Live Demo

- **Dashboard**: [https://frontend-ten-liard-22.vercel.app](https://frontend-ten-liard-22.vercel.app)
- **API Docs**: _Deployed on Render_ `/docs`

## 🚀 Quick Start (Docker)

```bash
cp .env.example .env   # Configure environment
docker compose up --build
```

Open:

- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Dashboard: http://localhost:3000
- Mandatory endpoint: http://localhost:8000/Metrics

The Compose file mounts the provided local CSV and CCTV folder from this workspace. Videos, CSVs, spreadsheets, and PDFs are intentionally ignored by Git and Docker build context.

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Next.js    │────▶│  FastAPI      │────▶│  PostgreSQL  │
│  Dashboard  │     │  Backend      │     │  Database    │
│  (Vercel)   │     │  (Render)     │     │  (Render)    │
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────▼───────┐
                    │    Redis     │
                    │   (Streams)  │
                    └──────────────┘
```

## ☁️ Cloud Deployment

### Frontend (Vercel)
Already deployed. Auto-deploys from `main` branch.

### Backend (Render)

1. Go to [https://dashboard.render.com](https://dashboard.render.com) and sign up/login
2. Click **New** → **Blueprint**
3. Connect your GitHub repo: `Kaif0333/Store-Intelligence-Challenge-Evaluation-Framework-`
4. Render will auto-detect `render.yaml` and deploy the API + PostgreSQL
5. Once deployed, copy the Render service URL
6. Go to your Vercel project settings → **Environment Variables**
7. Add: `API_INTERNAL_URL` = `https://your-render-service.onrender.com`
8. Redeploy the Vercel frontend

## 🧪 Local Backend Checks

```bash
$env:PYTHONPATH="backend"
pytest backend/tests -q
```

## 📦 Ingest A Video Run

```bash
curl -X POST http://localhost:8000/ingest/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"store_id\":\"ST1008\",\"video_glob\":\"/data/videos/*.mp4\",\"sample_fps\":2,\"max_seconds\":180,\"auto_start\":true}"
```

## Tech Stack

| Layer      | Technology                        |
|------------|-----------------------------------|
| Frontend   | Next.js 16, React 19, Recharts   |
| Backend    | FastAPI, SQLAlchemy, Pydantic     |
| Database   | PostgreSQL 16                     |
| Streaming  | Redis Streams                     |
| Vision     | OpenCV, YOLO11n                   |
| Deployment | Docker, Vercel, Render            |
