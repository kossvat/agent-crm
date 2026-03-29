"""Agent CRM — FastAPI application."""

import asyncio
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

from backend.routers import dashboard, agents, tasks, crons, costs, alerts, spending, system, files, auth_router, connect, ingest

log = logging.getLogger("agent-crm")

WATCHDOG_INTERVAL = 300  # 5 minutes


async def watchdog_loop():
    """Background watchdog — runs every 5 min, pure Python, no LLM."""
    from backend.services.watchdog import run as watchdog_run
    from backend.services.sync import sync_costs_history, sync_daily_costs
    from backend.database import SessionLocal
    await asyncio.sleep(60)  # wait 1 min after startup
    while True:
        try:
            watchdog_run()
        except Exception as e:
            log.error(f"Watchdog error: {e}")
        # Sync costs every cycle (idempotent — upserts existing rows)
        try:
            db = SessionLocal()
            sync_daily_costs(db)
            sync_costs_history(db)
            db.close()
        except Exception as e:
            log.error(f"Costs sync error: {e}")
        await asyncio.sleep(WATCHDOG_INTERVAL)


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

    # Start watchdog background task
    watchdog_task = asyncio.create_task(watchdog_loop())
    log.info("Watchdog started (every 5 min)")

    yield

    # Cleanup
    watchdog_task.cancel()
    try:
        await watchdog_task
    except asyncio.CancelledError:
        pass


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
app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(crons.router)
app.include_router(costs.router)
app.include_router(alerts.router)
app.include_router(spending.router)
app.include_router(system.router)
app.include_router(files.router)
app.include_router(connect.router)
app.include_router(ingest.router)

from backend.routers import journal
app.include_router(journal.router)


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
    from fastapi.responses import FileResponse

    @app.get("/app.js")
    async def serve_app_js():
        return FileResponse(
            str(FRONTEND_DIR / "app.js"),
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/style.css")
    async def serve_style_css():
        return FileResponse(
            str(FRONTEND_DIR / "style.css"),
            media_type="text/css",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
