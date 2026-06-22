# TAQA Bid Analyzer Demo

AI-driven commercial bid analysis tool for TAQA/ADDC procurement.

## Getting Started

### Backend (FastAPI)

```bash
cd ~/Desktop/Projects/TAQA/bid_analyzer_demo
uv run uvicorn backend.main:app --reload --port 8000
```

- API: http://localhost:8000/api
- Health check: http://localhost:8000/health

### Frontend (Next.js)

```bash
cd ~/Desktop/Projects/TAQA/bid_analyzer_demo/frontend
npm run dev
```

- UI: http://localhost:3000
