"""Cron management — reads from OpenClaw jobs.json, controls via CLI."""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from backend.auth import get_current_user
from backend.config import OPENCLAW_BIN, OPENCLAW_DIR

router = APIRouter(prefix="/api/crons", tags=["crons"])
log = logging.getLogger("agent-crm.crons")

JOBS_FILE = Path(OPENCLAW_DIR) / "cron" / "jobs.json"


def _run_oc(args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        r = subprocess.run([OPENCLAW_BIN] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", "openclaw not found"


def _read_jobs() -> list[dict]:
    """Read cron jobs directly from jobs.json."""
    if not JOBS_FILE.exists():
        return []
    try:
        with open(JOBS_FILE) as f:
            data = json.load(f)
        return data.get("jobs", [])
    except Exception as e:
        log.error(f"Failed to read jobs.json: {e}")
        return []


def _parse_cron_item(item: dict) -> dict:
    """Parse OpenClaw cron item to CRM format."""
    schedule = item.get("schedule", {})
    payload = item.get("payload", {})
    state = item.get("state", {})
    delivery = item.get("delivery", {})

    name = item.get("name", "")
    if not name:
        msg = payload.get("message", "")
        name = msg[:80] + ("…" if len(msg) > 80 else "")

    next_run_ms = state.get("nextRunAtMs")
    next_run = None
    if next_run_ms:
        try:
            next_run = datetime.fromtimestamp(next_run_ms / 1000, tz=timezone.utc).isoformat()
        except Exception:
            pass

    return {
        "id": item.get("id", ""),
        "name": name,
        "schedule": schedule.get("expr", schedule.get("kind", "")),
        "timezone": schedule.get("tz", "UTC"),
        "agent_id": item.get("agentId", ""),
        "enabled": item.get("enabled", True),
        "model": payload.get("model", ""),
        "description": payload.get("message", "")[:200],
        "next_run": next_run,
        "delivery_channel": delivery.get("channel", ""),
    }


@router.get("")
def list_crons(user: dict = Depends(get_current_user)):
    """List all cron jobs from OpenClaw jobs.json."""
    jobs = _read_jobs()
    return [_parse_cron_item(item) for item in jobs]


@router.post("/{cron_id}/enable")
def enable_cron(cron_id: str, user: dict = Depends(get_current_user)):
    """Enable a cron job."""
    if not user.get("full_access") and not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    code, stdout, stderr = _run_oc(["cron", "enable", cron_id])
    if code != 0:
        # Fallback: edit jobs.json directly
        try:
            _toggle_job(cron_id, True)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed: {e}")
    return {"ok": True, "id": cron_id, "enabled": True}


@router.post("/{cron_id}/disable")
def disable_cron(cron_id: str, user: dict = Depends(get_current_user)):
    """Disable a cron job."""
    if not user.get("full_access") and not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    code, stdout, stderr = _run_oc(["cron", "disable", cron_id])
    if code != 0:
        try:
            _toggle_job(cron_id, False)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed: {e}")
    return {"ok": True, "id": cron_id, "enabled": False}


@router.delete("/{cron_id}")
def delete_cron(cron_id: str, user: dict = Depends(get_current_user)):
    """Delete a cron job."""
    if not user.get("full_access") and not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    code, stdout, stderr = _run_oc(["cron", "rm", cron_id])
    if code != 0:
        raise HTTPException(status_code=502, detail=f"Failed to delete: {(stderr or stdout)[:200]}")
    return {"ok": True, "id": cron_id, "deleted": True}


def _toggle_job(job_id: str, enabled: bool):
    """Directly toggle a job in jobs.json (fallback when CLI fails)."""
    if not JOBS_FILE.exists():
        raise FileNotFoundError("jobs.json not found")

    with open(JOBS_FILE) as f:
        data = json.load(f)

    found = False
    for job in data.get("jobs", []):
        if job.get("id") == job_id:
            job["enabled"] = enabled
            found = True
            break

    if not found:
        raise ValueError(f"Job {job_id} not found")

    with open(JOBS_FILE, "w") as f:
        json.dump(data, f, indent=2)
