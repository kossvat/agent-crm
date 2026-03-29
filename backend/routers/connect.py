"""Connect router — magic link token generation and redemption for remote agent bootstrap."""

import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import ConnectToken, Workspace
from backend.auth import get_current_user, create_workspace_token

router = APIRouter(prefix="/api/connect", tags=["connect"])

DEFAULT_EXPIRY_HOURS = 24
CRM_BASE_URL = "https://crm.myaiagentscrm.com"


# --- Schemas ---

class GenerateResponse(BaseModel):
    token: str
    connect_url: str
    expires: datetime


class RedeemResponse(BaseModel):
    workspace_id: int
    workspace_name: str
    workspace_token: str


class TokenStatusResponse(BaseModel):
    id: int
    token: str
    connect_url: str
    created: datetime
    expires: datetime
    used: bool


# --- Endpoints ---

@router.post("/generate", response_model=GenerateResponse)
def generate_connect_token(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a magic link token. Owner only."""
    if not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    ws_id = user.get("workspace_id", 1)
    user_id = user.get("user_id")

    token_str = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=DEFAULT_EXPIRY_HOURS)

    ct = ConnectToken(
        token=token_str,
        workspace_id=ws_id,
        created_by=user_id,
        expires=expires,
    )
    db.add(ct)
    db.commit()
    db.refresh(ct)

    return GenerateResponse(
        token=token_str,
        connect_url=f"{CRM_BASE_URL}/connect/{token_str}",
        expires=expires,
    )


@router.get("/status", response_model=list[TokenStatusResponse])
def connect_status(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active (unused, non-expired) connect tokens for current workspace."""
    ws_id = user.get("workspace_id", 1)
    tokens = (
        db.query(ConnectToken)
        .filter(
            ConnectToken.workspace_id == ws_id,
            ConnectToken.used == False,
        )
        .order_by(ConnectToken.created.desc())
        .all()
    )
    # Filter expired in Python (SQLite naive datetime issue)
    now = datetime.now(timezone.utc)
    tokens = [
        t for t in tokens
        if (t.expires if t.expires.tzinfo else t.expires.replace(tzinfo=timezone.utc)) > now
    ]
    return [
        TokenStatusResponse(
            id=t.id,
            token=t.token,
            connect_url=f"{CRM_BASE_URL}/connect/{t.token}",
            created=t.created,
            expires=t.expires,
            used=t.used,
        )
        for t in tokens
    ]


@router.get("/{token}", response_model=RedeemResponse)
def redeem_connect_token(
    token: str,
    db: Session = Depends(get_db),
):
    """Redeem a connect token — called by remote agent. No auth required.
    Returns a long-lived workspace_token for ingest API.
    """
    ct = db.query(ConnectToken).filter(ConnectToken.token == token).first()
    if not ct:
        raise HTTPException(status_code=404, detail="Token not found")

    now = datetime.now(timezone.utc)
    if ct.used:
        raise HTTPException(status_code=410, detail="Token already used")
    # Ensure timezone-aware comparison (SQLite stores naive datetimes)
    expires = ct.expires if ct.expires.tzinfo else ct.expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=410, detail="Token expired")

    # Mark as used
    ct.used = True
    ct.used_at = now

    # Get workspace info
    workspace = db.query(Workspace).filter(Workspace.id == ct.workspace_id).first()
    ws_name = workspace.name if workspace else "Unknown"

    # Generate long-lived workspace token
    ws_token = create_workspace_token(ct.workspace_id, days=30)

    db.commit()

    return RedeemResponse(
        workspace_id=ct.workspace_id,
        workspace_name=ws_name,
        workspace_token=ws_token,
    )
