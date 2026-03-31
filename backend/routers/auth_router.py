"""Authentication router — Telegram login + JWT tokens."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Workspace, TierType, InviteCode
from backend.auth import validate_init_data, create_access_token, get_current_user
from backend.config import REQUIRE_INVITE

import secrets
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _validate_invite(db: Session, code: str) -> InviteCode | None:
    """Validate an invite code. Returns InviteCode if valid, None otherwise."""
    invite = db.query(InviteCode).filter(InviteCode.code == code.strip().upper()).first()
    if not invite:
        return None
    if invite.use_count >= invite.max_uses:
        return None
    if invite.expires:
        exp = invite.expires if invite.expires.tzinfo else invite.expires.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return None
    return invite


class TelegramLoginRequest(BaseModel):
    init_data: str
    invite_code: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    user: dict


@router.post("/telegram", response_model=AuthResponse)
def telegram_login(
    data: TelegramLoginRequest,
    db: Session = Depends(get_db),
):
    """Authenticate via Telegram initData. Returns JWT token."""
    try:
        tg_user = validate_init_data(data.init_data)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    telegram_id = tg_user.get("user_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No user_id in initData")

    # Find or create user
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        # New user — check invite code if required
        if REQUIRE_INVITE:
            if not data.invite_code:
                raise HTTPException(
                    status_code=403,
                    detail="invite_required"
                )
            invite = _validate_invite(db, data.invite_code)
            if not invite:
                raise HTTPException(
                    status_code=403,
                    detail="invalid_invite"
                )

        name = tg_user.get("first_name", "")
        if tg_user.get("last_name"):
            name += f" {tg_user['last_name']}"
        user = User(
            telegram_id=telegram_id,
            name=name or f"User {telegram_id}",
        )
        db.add(user)
        db.flush()

        # Mark invite as used
        if REQUIRE_INVITE and data.invite_code:
            invite = db.query(InviteCode).filter(InviteCode.code == data.invite_code.strip().upper()).first()
            if invite:
                invite.use_count += 1
                if invite.use_count >= invite.max_uses:
                    invite.used_by = user.id

        # Create default workspace for new user
        workspace = Workspace(
            name="Default",
            owner_id=user.id,
            tier=TierType.hobby,
            agent_limit=3,
        )
        db.add(workspace)
        db.commit()
        db.refresh(user)
        db.refresh(workspace)
    else:
        # Find existing workspace
        workspace = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
        if not workspace:
            workspace = Workspace(
                name="Default",
                owner_id=user.id,
                tier=TierType.hobby,
                agent_limit=3,
            )
            db.add(workspace)
            db.commit()
            db.refresh(workspace)

    token = create_access_token(user.id, workspace.id)

    return AuthResponse(
        access_token=token,
        user={
            "id": user.id,
            "telegram_id": user.telegram_id,
            "name": user.name,
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "tier": workspace.tier.value if workspace.tier else "hobby",
            "onboarding_complete": user.onboarding_complete,
            "is_superadmin": user.is_superadmin or False,
        },
    )


@router.patch("/onboarding-complete")
def complete_onboarding(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark onboarding as complete for current user."""
    user_id = user.get("user_id")
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db_user.onboarding_complete = True
    db.commit()
    return {"ok": True}


class BudgetUpdateRequest(BaseModel):
    monthly_budget: float


@router.patch("/workspace/budget")
def update_budget(
    data: BudgetUpdateRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update workspace monthly budget. Owner only."""
    if not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")
    ws_id = user.get("workspace_id", 1)
    workspace = db.query(Workspace).filter(Workspace.id == ws_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if data.monthly_budget < 0 or data.monthly_budget > 10000:
        raise HTTPException(status_code=400, detail="Budget must be 0-10000")
    workspace.monthly_budget = data.monthly_budget
    db.commit()
    return {"ok": True, "monthly_budget": workspace.monthly_budget}


@router.get("/me")
def get_me(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user + workspace info."""
    user_id = user.get("user_id")
    workspace_id = user.get("workspace_id", 1)

    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=401, detail="User not found")
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=401, detail="Workspace not found")

    return {
        "user": {
            "id": db_user.id if db_user else user_id,
            "telegram_id": db_user.telegram_id if db_user else None,
            "name": db_user.name if db_user else user.get("username", ""),
            "onboarding_complete": db_user.onboarding_complete if db_user else False,
            "is_superadmin": db_user.is_superadmin if db_user else False,
        },
        "workspace": {
            "id": workspace.id if workspace else workspace_id,
            "name": workspace.name if workspace else "Default",
            "tier": workspace.tier.value if workspace and workspace.tier else "hobby",
            "agent_limit": workspace.agent_limit if workspace else 3,
        },
    }


# --- Invite Code Management (owner/admin only) ---

class CreateInviteRequest(BaseModel):
    max_uses: int = 1
    note: str = ""
    expires_hours: int | None = None  # None = never expires


@router.post("/invites")
def create_invite(
    data: CreateInviteRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate invite codes. Owner only."""
    if not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    code = secrets.token_hex(4).upper()  # 8-char hex code like "A3F7B2C1"
    expires = None
    if data.expires_hours:
        expires = datetime.now(timezone.utc) + timedelta(hours=data.expires_hours)

    invite = InviteCode(
        code=code,
        created_by=user["user_id"],
        max_uses=max(1, min(data.max_uses, 100)),
        note=data.note,
        expires=expires,
    )
    db.add(invite)
    db.commit()

    return {
        "code": code,
        "max_uses": invite.max_uses,
        "note": invite.note,
        "expires": expires.isoformat() if expires else None,
    }


@router.get("/invites")
def list_invites(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all invite codes. Owner only."""
    if not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    invites = db.query(InviteCode).order_by(InviteCode.created.desc()).all()
    return [
        {
            "code": inv.code,
            "max_uses": inv.max_uses,
            "use_count": inv.use_count,
            "note": inv.note,
            "expires": inv.expires.isoformat() if inv.expires else None,
            "created": inv.created.isoformat() if inv.created else None,
            "exhausted": inv.use_count >= inv.max_uses,
        }
        for inv in invites
    ]


@router.get("/invites/check/{code}")
def check_invite(code: str, db: Session = Depends(get_db)):
    """Public endpoint — check if an invite code is valid (no auth needed)."""
    invite = _validate_invite(db, code)
    if invite:
        return {"valid": True, "remaining": invite.max_uses - invite.use_count}
    return {"valid": False, "remaining": 0}
