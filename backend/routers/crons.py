"""Cron monitoring endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Cron
from backend.schemas import CronResponse
from backend.auth import get_current_user

router = APIRouter(prefix="/api/crons", tags=["crons"])


@router.get("", response_model=list[CronResponse])
def list_crons(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all cron jobs."""
    return db.query(Cron).order_by(Cron.name).all()


@router.get("/{cron_id}", response_model=CronResponse)
def get_cron(
    cron_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single cron job."""
    cron = db.query(Cron).filter(Cron.id == cron_id).first()
    if not cron:
        raise HTTPException(status_code=404, detail="Cron not found")
    return cron
