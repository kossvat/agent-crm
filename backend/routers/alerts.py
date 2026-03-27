"""Alert feed endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Alert
from backend.schemas import AlertCreate, AlertResponse
from backend.auth import get_current_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    unread: Optional[bool] = Query(None),
    agent_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws_id = user.get("workspace_id", 1)
    q = db.query(Alert).filter(Alert.workspace_id == ws_id)

    if unread is True:
        q = q.filter(Alert.is_read == False)
    if agent_id:
        q = q.filter(Alert.agent_id == agent_id)

    return q.order_by(Alert.created.desc()).limit(limit).all()


@router.post("", response_model=AlertResponse, status_code=201)
def create_alert(
    data: AlertCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws_id = user.get("workspace_id", 1)
    alert = Alert(**data.model_dump(), workspace_id=ws_id)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.patch("/{alert_id}/read", response_model=AlertResponse)
def mark_alert_read(
    alert_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws_id = user.get("workspace_id", 1)
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.workspace_id == ws_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.is_read = True
    db.commit()
    db.refresh(alert)
    return alert
