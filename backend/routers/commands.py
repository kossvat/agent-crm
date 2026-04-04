"""Command queue endpoints for bidirectional CRM ↔ OpenClaw sync."""

import json
import logging
import os
from datetime import datetime, timezone

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from backend.database import get_db, SessionLocal
from backend.models import PendingCommand, User, Workspace
from backend.auth import get_current_user, decode_workspace_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/commands", tags=["commands"])


# --- Schemas ---

class CommandResponse(BaseModel):
    id: int
    workspace_id: int
    command_type: str
    payload: str
    status: str
    created: Optional[str] = None
    applied_at: Optional[str] = None
    error: Optional[str] = None


class AckRequest(BaseModel):
    status: str  # "applied" or "failed"
    error: Optional[str] = None


# --- Auth helper (workspace token) ---

def _get_workspace_id(request: Request) -> int:
    """Extract workspace_id from Authorization: Bearer <workspace_token>."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing workspace token")
    token = auth_header[7:]
    try:
        payload = decode_workspace_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return payload["workspace_id"]


# --- Endpoints (workspace token auth — for sync scripts) ---

@router.get("/pending", response_model=list[CommandResponse])
def get_pending_commands(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get pending commands for the current workspace.

    Auth: JWT (frontend) or workspace token (sync script).
    If JWT auth succeeds, uses workspace_id from JWT.
    """
    ws_id = user.get("workspace_id", 1)
    db: Session = SessionLocal()
    try:
        commands = (
            db.query(PendingCommand)
            .filter(
                PendingCommand.workspace_id == ws_id,
                PendingCommand.status == "pending",
            )
            .order_by(PendingCommand.created.asc())
            .all()
        )
        return [
            CommandResponse(
                id=cmd.id,
                workspace_id=cmd.workspace_id,
                command_type=cmd.command_type,
                payload=cmd.payload,
                status=cmd.status,
                created=cmd.created.isoformat() if cmd.created else None,
                applied_at=cmd.applied_at.isoformat() if cmd.applied_at else None,
                error=cmd.error,
            )
            for cmd in commands
        ]
    finally:
        db.close()


@router.get("/pending/ws", response_model=list[CommandResponse])
def get_pending_commands_ws(request: Request):
    """Get pending commands via workspace token (for sync scripts).

    Auth: workspace token only (Bearer header).
    """
    ws_id = _get_workspace_id(request)
    db: Session = SessionLocal()
    try:
        commands = (
            db.query(PendingCommand)
            .filter(
                PendingCommand.workspace_id == ws_id,
                PendingCommand.status == "pending",
            )
            .order_by(PendingCommand.created.asc())
            .all()
        )
        return [
            CommandResponse(
                id=cmd.id,
                workspace_id=cmd.workspace_id,
                command_type=cmd.command_type,
                payload=cmd.payload,
                status=cmd.status,
                created=cmd.created.isoformat() if cmd.created else None,
                applied_at=cmd.applied_at.isoformat() if cmd.applied_at else None,
                error=cmd.error,
            )
            for cmd in commands
        ]
    finally:
        db.close()


def _send_telegram_notification(chat_id: int, text: str):
    """Best-effort Telegram notification via Bot API."""
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token or not chat_id:
        return
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        )
    except Exception as e:
        logger.warning(f"Telegram notification failed: {e}")


def _notify_command_result(db: Session, cmd: PendingCommand, status: str, error: str | None):
    """Send Telegram notification to workspace owner about command result."""
    try:
        workspace = db.query(Workspace).filter(Workspace.id == cmd.workspace_id).first()
        if not workspace:
            return
        owner = db.query(User).filter(User.id == workspace.owner_id).first()
        if not owner or not owner.telegram_id:
            return

        # Parse payload for agent/model info
        try:
            payload = json.loads(cmd.payload) if isinstance(cmd.payload, str) else cmd.payload
        except (json.JSONDecodeError, TypeError):
            payload = {}

        agent_name = payload.get("agent_name", "unknown")
        model_name = payload.get("model", "unknown")

        if status == "applied":
            text = f"✅ Model for {agent_name} changed to {model_name}"
        else:
            err_msg = error or "unknown error"
            text = f"❌ Failed to change model for {agent_name}: {err_msg}"

        _send_telegram_notification(owner.telegram_id, text)
    except Exception as e:
        logger.warning(f"Failed to send command notification: {e}")


_SYSTEM_CMD_MESSAGES = {
    "stop_gateway": "⏹ Gateway stopped and all crons disabled",
    "resume_gateway": "▶ Gateway started and all crons enabled",
    "fix_system": "🔧 System fix applied: sessions cleared, crons disabled",
}


def _notify_system_command_result(db: Session, cmd: PendingCommand, status: str, error: str | None):
    """Send Telegram notification about system command result."""
    try:
        workspace = db.query(Workspace).filter(Workspace.id == cmd.workspace_id).first()
        if not workspace:
            return
        owner = db.query(User).filter(User.id == workspace.owner_id).first()
        if not owner or not owner.telegram_id:
            return

        if status == "applied":
            text = _SYSTEM_CMD_MESSAGES.get(cmd.command_type, f"✅ {cmd.command_type} applied")
        else:
            action = cmd.command_type.replace("_", " ")
            text = f"❌ Failed to {action}: {error or 'unknown error'}"

        _send_telegram_notification(owner.telegram_id, text)
    except Exception as e:
        logger.warning(f"Failed to send system command notification: {e}")


@router.post("/{command_id}/ack")
def ack_command(
    command_id: int,
    data: AckRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Acknowledge a command (mark as applied or failed).

    Auth: API key, JWT, or workspace token.
    """
    ws_id = user.get("workspace_id", 1)

    if data.status not in ("applied", "failed"):
        raise HTTPException(status_code=400, detail="status must be 'applied' or 'failed'")

    db: Session = SessionLocal()
    try:
        cmd = (
            db.query(PendingCommand)
            .filter(
                PendingCommand.id == command_id,
                PendingCommand.workspace_id == ws_id,
            )
            .first()
        )
        if not cmd:
            raise HTTPException(status_code=404, detail="Command not found")

        cmd.status = data.status
        if data.status == "applied":
            cmd.applied_at = datetime.now(timezone.utc)
        if data.error:
            cmd.error = data.error

        db.commit()

        # Best-effort notification (after commit, don't fail the ACK)
        if cmd.command_type == "change_model":
            _notify_command_result(db, cmd, data.status, data.error)
        elif cmd.command_type in ("stop_gateway", "resume_gateway", "fix_system"):
            _notify_system_command_result(db, cmd, data.status, data.error)

        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
