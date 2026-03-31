"""System control endpoints — stop/resume/fix."""

import glob
import json
import logging
import os
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from backend.auth import get_current_user
from backend.config import OPENCLAW_BIN, OPENCLAW_DIR

router = APIRouter(prefix="/api/system", tags=["system"])
log = logging.getLogger("agent-crm.system")

SPENDING_DB = os.path.expanduser("~/projects/spending-tracker/spending.db")


def _run_oc(args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        r = subprocess.run([OPENCLAW_BIN] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", "not found"


def _check_gateway() -> dict:
    """Check if gateway is running by looking for the process."""
    import re
    try:
        r = subprocess.run(["pgrep", "-f", "openclaw.*gateway"], capture_output=True, text=True, timeout=5)
        running = r.returncode == 0 and bool(r.stdout.strip())
        pids = r.stdout.strip().split("\n") if running else []
        return {"running": running, "pids": pids}
    except Exception:
        return {"running": False, "pids": []}


def _openclaw_available() -> bool:
    """Check if OpenClaw binary exists and is executable."""
    return os.path.isfile(OPENCLAW_BIN) and os.access(OPENCLAW_BIN, os.X_OK)


@router.get("/status")
def system_status(user: dict = Depends(get_current_user)):
    """System status: gateway running, cron count, etc."""
    if not _openclaw_available():
        return {
            "status": "not_configured",
            "gateway": False,
            "message": "OpenClaw not connected",
        }

    gw = _check_gateway()

    return {
        "status": "running" if gw["running"] else "stopped",
        "gateway": gw["running"],
    }


@router.post("/stop")
def system_stop(user: dict = Depends(get_current_user)):
    """STOP: stop gateway + disable all crons. Owner only."""
    if not _openclaw_available():
        return {"error": "OpenClaw not configured"}
    if not user.get("full_access") and not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    results = {"gateway": None, "crons_disabled": []}

    # Stop gateway
    code, stdout, stderr = _run_oc(["gateway", "stop"], timeout=20)
    results["gateway"] = "stopped" if code == 0 else f"error: {stderr[:200]}"

    # Disable all crons
    code, stdout, stderr = _run_oc(["cron", "list", "--json", "--all"], timeout=15)
    if code == 0:
        try:
            data = json.loads(stdout)
            for cron in data.get("items", []):
                if cron.get("enabled"):
                    cid = cron["id"]
                    _run_oc(["cron", "disable", cid], timeout=10)
                    results["crons_disabled"].append(cron.get("name", cid))
        except json.JSONDecodeError:
            results["crons_error"] = "Failed to parse cron list"

    return results


@router.post("/resume")
def system_resume(user: dict = Depends(get_current_user)):
    """RESUME: start gateway + enable all crons. Owner only."""
    if not _openclaw_available():
        return {"error": "OpenClaw not configured"}
    if not user.get("full_access") and not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    results = {"gateway": None, "crons_enabled": []}

    # Start gateway
    code, stdout, stderr = _run_oc(["gateway", "start"], timeout=20)
    results["gateway"] = "started" if code == 0 else f"error: {stderr[:200]}"

    # Enable all crons
    code, stdout, stderr = _run_oc(["cron", "list", "--json", "--all"], timeout=15)
    if code == 0:
        try:
            data = json.loads(stdout)
            for cron in data.get("items", []):
                if not cron.get("enabled"):
                    cid = cron["id"]
                    _run_oc(["cron", "enable", cid], timeout=10)
                    results["crons_enabled"].append(cron.get("name", cid))
        except json.JSONDecodeError:
            results["crons_error"] = "Failed to parse cron list"

    return results


@router.post("/fix")
def system_fix(user: dict = Depends(get_current_user)):
    """FIX: clear large sessions, disable crons, report spending."""
    if not _openclaw_available():
        return {"error": "OpenClaw not configured"}
    if not user.get("full_access") and not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    results = {
        "cleared_sessions": [],
        "paused_crons": [],
        "spending_last_hour": {},
    }

    # 1. Find and delete large session JSONL files (>500KB)
    agents_dir = Path(OPENCLAW_DIR) / "agents"
    if agents_dir.exists():
        for jsonl in agents_dir.glob("*/sessions/*.jsonl"):
            if jsonl.stat().st_size > 500 * 1024:
                size_kb = jsonl.stat().st_size // 1024
                try:
                    jsonl.unlink()
                    results["cleared_sessions"].append(
                        f"{jsonl.parent.parent.name}/{jsonl.name} ({size_kb}KB)"
                    )
                except Exception as e:
                    log.error(f"Failed to delete {jsonl}: {e}")

    # 2. Disable all crons
    code, stdout, stderr = _run_oc(["cron", "list", "--json", "--all"], timeout=15)
    if code == 0:
        try:
            data = json.loads(stdout)
            for cron in data.get("items", []):
                if cron.get("enabled"):
                    cid = cron["id"]
                    _run_oc(["cron", "disable", cid], timeout=10)
                    results["paused_crons"].append(cron.get("name", cid))
        except json.JSONDecodeError:
            pass

    # 3. Spending last hour
    if os.path.exists(SPENDING_DB):
        conn = sqlite3.connect(SPENDING_DB)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        rows = conn.execute("""
            SELECT agent, SUM(cost_total) as cost, COUNT(*) as msgs
            FROM usage_log
            WHERE timestamp > ?
            GROUP BY agent
        """, (cutoff,)).fetchall()
        conn.close()
        for r in rows:
            results["spending_last_hour"][r[0]] = {
                "cost": round(float(r[1]), 2),
                "messages": r[2],
            }

    return results
