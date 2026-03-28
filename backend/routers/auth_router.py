"""Authentication router — Telegram login + JWT tokens."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Workspace, TierType
from backend.auth import validate_init_data, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TelegramLoginRequest(BaseModel):
    init_data: str


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
        name = tg_user.get("first_name", "")
        if tg_user.get("last_name"):
            name += f" {tg_user['last_name']}"
        user = User(
            telegram_id=telegram_id,
            name=name or f"User {telegram_id}",
        )
        db.add(user)
        db.flush()

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
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()

    return {
        "user": {
            "id": db_user.id if db_user else user_id,
            "telegram_id": db_user.telegram_id if db_user else None,
            "name": db_user.name if db_user else user.get("username", ""),
            "onboarding_complete": db_user.onboarding_complete if db_user else False,
        },
        "workspace": {
            "id": workspace.id if workspace else workspace_id,
            "name": workspace.name if workspace else "Default",
            "tier": workspace.tier.value if workspace and workspace.tier else "hobby",
            "agent_limit": workspace.agent_limit if workspace else 3,
        },
    }
