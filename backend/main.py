"""Agent CRM — FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import HOST, PORT
from backend.database import create_tables, SessionLocal
from backend.auth import get_current_user
from backend.services.sync import full_sync

from backend.routers import dashboard, agents, tasks, crons, costs, alerts

log = logging.getLogger("agent-crm")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    # Create tables
    create_tables()
    log.info("Database tables created")

    # Initial sync from OpenClaw
    try:
        db = SessionLocal()
        result = full_sync(db)
        db.close()
        log.info(f"Initial sync: {result}")
    except Exception as e:
        log.error(f"Initial sync failed: {e}")

    yield


app = FastAPI(
    title="Agent CRM",
    description="CRM for AI agent teams — Telegram Mini App",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow Telegram WebApp domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://web.telegram.org",
        "https://telegram.org",
        "https://crm.myaiagentscrm.com",
        "http://localhost:*",
        "http://127.0.0.1:*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(dashboard.router)
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(crons.router)
app.include_router(costs.router)
app.include_router(alerts.router)


# Sync endpoint
@app.post("/api/sync")
def trigger_sync(user: dict = Depends(get_current_user)):
    """Manually trigger OpenClaw sync."""
    db = SessionLocal()
    try:
        result = full_sync(db)
        return result
    finally:
        db.close()


# Serve frontend static files
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
