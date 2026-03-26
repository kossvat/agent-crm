"""Cost tracking endpoints."""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import Cost, Agent
from backend.schemas import CostResponse, CostSummary
from backend.auth import get_current_user

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("", response_model=list[CostResponse])
def list_costs(
    agent_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List costs with optional filters."""
    q = db.query(Cost)

    if agent_id:
        q = q.filter(Cost.agent_id == agent_id)
    if date_from:
        q = q.filter(Cost.date >= date_from)
    if date_to:
        q = q.filter(Cost.date <= date_to)

    return q.order_by(Cost.date.desc()).all()


@router.get("/summary", response_model=list[CostSummary])
def cost_summary(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cost summary grouped by agent."""
    q = (
        db.query(
            Cost.agent_id,
            Agent.name,
            Agent.emoji,
            func.sum(Cost.cost_usd).label("total_cost"),
            func.sum(Cost.input_tokens).label("total_input_tokens"),
            func.sum(Cost.output_tokens).label("total_output_tokens"),
        )
        .join(Agent, Cost.agent_id == Agent.id)
        .group_by(Cost.agent_id, Agent.name, Agent.emoji)
    )

    if date_from:
        q = q.filter(Cost.date >= date_from)
    if date_to:
        q = q.filter(Cost.date <= date_to)

    rows = q.all()
    return [
        CostSummary(
            agent_id=r.agent_id,
            agent_name=r.name,
            agent_emoji=r.emoji,
            total_cost=float(r.total_cost or 0),
            total_input_tokens=int(r.total_input_tokens or 0),
            total_output_tokens=int(r.total_output_tokens or 0),
        )
        for r in rows
    ]
