"""Superadmin panel endpoints."""

import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Workspace, Agent, Task, InviteCode
from backend.auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- Superadmin dependency ---

def get_superadmin(user: dict = Depends(get_current_user)):
    """Require is_superadmin=True on the JWT user."""
    if not user.get("is_superadmin"):
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return user


# --- Endpoints ---

@router.get("/users")
def list_users(
    admin: dict = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    """List all users with workspace/agent/task counts."""
    users = db.query(User).order_by(User.created.desc()).all()
    result = []
    for u in users:
        ws_count = db.query(func.count(Workspace.id)).filter(Workspace.owner_id == u.id).scalar()
        # Count agents/tasks across all user's workspaces
        ws_ids = [w.id for w in db.query(Workspace.id).filter(Workspace.owner_id == u.id).all()]
        agent_count = db.query(func.count(Agent.id)).filter(Agent.workspace_id.in_(ws_ids)).scalar() if ws_ids else 0
        task_count = db.query(func.count(Task.id)).filter(Task.workspace_id.in_(ws_ids)).scalar() if ws_ids else 0
        result.append({
            "id": u.id,
            "name": u.name,
            "telegram_id": u.telegram_id,
            "created": u.created.isoformat() if u.created else None,
            "onboarding_complete": u.onboarding_complete,
            "is_superadmin": u.is_superadmin,
            "workspaces_count": ws_count,
            "agents_count": agent_count,
            "tasks_count": task_count,
        })
    return result


@router.get("/workspaces")
def list_workspaces(
    admin: dict = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    """List all workspaces with owner info."""
    workspaces = db.query(Workspace).order_by(Workspace.created.desc()).all()
    result = []
    for ws in workspaces:
        owner = db.query(User).filter(User.id == ws.owner_id).first()
        agent_count = db.query(func.count(Agent.id)).filter(Agent.workspace_id == ws.id).scalar()
        result.append({
            "id": ws.id,
            "name": ws.name,
            "owner_name": owner.name if owner else "Unknown",
            "owner_id": ws.owner_id,
            "tier": ws.tier.value if ws.tier else "hobby",
            "agent_count": agent_count,
            "created": ws.created.isoformat() if ws.created else None,
        })
    return result


@router.get("/invites")
def list_invites(
    admin: dict = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    """List all invite codes with usage info."""
    invites = db.query(InviteCode).order_by(InviteCode.created.desc()).all()
    return [
        {
            "id": inv.id,
            "code": inv.code,
            "max_uses": inv.max_uses,
            "use_count": inv.use_count,
            "note": inv.note or "",
            "created": inv.created.isoformat() if inv.created else None,
            "expires": inv.expires.isoformat() if inv.expires else None,
            "status": "exhausted" if inv.use_count >= inv.max_uses else "active",
        }
        for inv in invites
    ]


@router.get("/stats")
def get_stats(
    admin: dict = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    """Summary stats for superadmin dashboard."""
    total_users = db.query(func.count(User.id)).scalar()
    total_workspaces = db.query(func.count(Workspace.id)).scalar()
    total_agents = db.query(func.count(Agent.id)).scalar()
    total_tasks = db.query(func.count(Task.id)).scalar()
    total_invites = db.query(func.count(InviteCode.id)).scalar()
    invites_used = db.query(func.coalesce(func.sum(InviteCode.use_count), 0)).scalar()
    invites_remaining = db.query(
        func.coalesce(func.sum(InviteCode.max_uses - InviteCode.use_count), 0)
    ).filter(InviteCode.use_count < InviteCode.max_uses).scalar()

    return {
        "total_users": total_users,
        "total_workspaces": total_workspaces,
        "total_agents": total_agents,
        "total_tasks": total_tasks,
        "total_invites": total_invites,
        "invites_used": invites_used,
        "invites_remaining": invites_remaining,
    }


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    admin: dict = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    """Delete a user. Cannot delete self."""
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete user's workspaces and related data
    ws_ids = [w.id for w in db.query(Workspace.id).filter(Workspace.owner_id == user_id).all()]
    if ws_ids:
        db.query(Agent).filter(Agent.workspace_id.in_(ws_ids)).delete(synchronize_session=False)
        db.query(Task).filter(Task.workspace_id.in_(ws_ids)).delete(synchronize_session=False)
        db.query(Workspace).filter(Workspace.owner_id == user_id).delete(synchronize_session=False)

    db.delete(user)
    db.commit()
    return {"ok": True}


class CreateInviteRequest(BaseModel):
    max_uses: int = 1
    note: str = ""


@router.post("/invites")
def create_invite(
    data: CreateInviteRequest,
    admin: dict = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    """Create a new invite code."""
    code = secrets.token_hex(4).upper()
    invite = InviteCode(
        code=code,
        created_by=admin["user_id"],
        max_uses=max(1, min(data.max_uses, 1000)),
        note=data.note,
    )
    db.add(invite)
    db.commit()
    return {
        "id": invite.id,
        "code": code,
        "max_uses": invite.max_uses,
        "note": invite.note,
    }


@router.delete("/invites/{invite_id}")
def delete_invite(
    invite_id: int,
    admin: dict = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    """Delete an invite code."""
    invite = db.query(InviteCode).filter(InviteCode.id == invite_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    db.delete(invite)
    db.commit()
    return {"ok": True}
