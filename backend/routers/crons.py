"""Cron management — reads from OpenClaw jobs.json (local) or DB (prod)."""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.config import OPENCLAW_BIN, OPENCLAW_DIR
from backend.database import get_db
from backend.models import Cron, CronStatus

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


def _openclaw_available() -> bool:
    return JOBS_FILE.exists()


def _read_jobs() -> list[dict]:
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
        "status": "active" if item.get("enabled", True) else "paused",
        "model": payload.get("model", ""),
        "command": payload.get("message", ""),
        "description": payload.get("message", ""),
        "next_run": next_run,
        "last_run": None,
        "delivery_channel": delivery.get("channel", ""),
        "source": "openclaw",
    }


def _db_cron_to_dict(c: Cron) -> dict:
    return {
        "id": str(c.id),
        "name": c.name or "",
        "schedule": c.schedule or "",
        "command": c.command or "",
        "agent_id": c.agent_id,
        "enabled": c.status == CronStatus.active,
        "status": c.status.value if c.status else "active",
        "last_run": c.last_run.isoformat() if c.last_run else None,
        "next_run": c.next_run.isoformat() if c.next_run else None,
        "source": "db",
    }


# --- Endpoints ---

@router.get("")
def list_crons(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List cron jobs — OpenClaw first, DB fallback."""
    if _openclaw_available():
        jobs = _read_jobs()
        return [_parse_cron_item(item) for item in jobs]

    # DB fallback
    ws_id = user.get("workspace_id", 1)
    crons = db.query(Cron).filter(Cron.workspace_id == ws_id).all()
    return [_db_cron_to_dict(c) for c in crons]


class CronCreate(BaseModel):
    name: str
    schedule: str
    command: str = ""
    agent_id: Optional[int] = None


@router.post("")
def create_cron(
    data: CronCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new cron job (stored in DB)."""
    ws_id = user.get("workspace_id", 1)
    cron = Cron(
        name=data.name,
        schedule=data.schedule,
        command=data.command,
        agent_id=data.agent_id,
        status=CronStatus.active,
        workspace_id=ws_id,
    )
    db.add(cron)
    db.commit()
    db.refresh(cron)
    return _db_cron_to_dict(cron)


@router.post("/{cron_id}/enable")
def enable_cron(
    cron_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enable a cron job."""
    if _openclaw_available():
        code, stdout, stderr = _run_oc(["cron", "enable", cron_id])
        if code != 0:
            try:
                _toggle_job(cron_id, True)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Failed: {e}")
        return {"ok": True, "id": cron_id, "enabled": True}

    # DB
    ws_id = user.get("workspace_id", 1)
    cron = db.query(Cron).filter(Cron.id == int(cron_id), Cron.workspace_id == ws_id).first()
    if not cron:
        raise HTTPException(status_code=404, detail="Cron not found")
    cron.status = CronStatus.active
    db.commit()
    return {"ok": True, "id": cron_id, "enabled": True}


@router.post("/{cron_id}/disable")
def disable_cron(
    cron_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disable a cron job."""
    if _openclaw_available():
        code, stdout, stderr = _run_oc(["cron", "disable", cron_id])
        if code != 0:
            try:
                _toggle_job(cron_id, False)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Failed: {e}")
        return {"ok": True, "id": cron_id, "enabled": False}

    # DB
    ws_id = user.get("workspace_id", 1)
    cron = db.query(Cron).filter(Cron.id == int(cron_id), Cron.workspace_id == ws_id).first()
    if not cron:
        raise HTTPException(status_code=404, detail="Cron not found")
    cron.status = CronStatus.paused
    db.commit()
    return {"ok": True, "id": cron_id, "enabled": False}


@router.delete("/{cron_id}")
def delete_cron(
    cron_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a cron job."""
    if _openclaw_available():
        code, stdout, stderr = _run_oc(["cron", "rm", cron_id])
        if code != 0:
            raise HTTPException(status_code=502, detail=f"Failed to delete: {(stderr or stdout)[:200]}")
        return {"ok": True, "id": cron_id, "deleted": True}

    # DB
    ws_id = user.get("workspace_id", 1)
    cron = db.query(Cron).filter(Cron.id == int(cron_id), Cron.workspace_id == ws_id).first()
    if not cron:
        raise HTTPException(status_code=404, detail="Cron not found")
    db.delete(cron)
    db.commit()
    return {"ok": True, "id": cron_id, "deleted": True}


def _toggle_job(job_id: str, enabled: bool):
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
