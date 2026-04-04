"""Cost tracking endpoints."""

from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import Cost, Agent
from backend.schemas import CostResponse, CostSummary
from backend.auth import get_current_user

router = APIRouter(prefix="/api/costs", tags=["costs"])


# --- Bulk ingest schema ---

class CostRecord(BaseModel):
    agent_name: str
    date: str  # YYYY-MM-DD
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""


class BulkIngestRequest(BaseModel):
    records: List[CostRecord]


class BulkIngestResponse(BaseModel):
    ingested: int
    created_agents: List[str]
    updated: int


@router.post("", response_model=BulkIngestResponse)
def ingest_costs(
    data: BulkIngestRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk ingest cost records. Upserts by agent+date+model."""
    ws_id = user.get("workspace_id", 1)
    created_agents = []
    updated = 0
    ingested = 0

    for rec in data.records:
        # Find or create agent (case-insensitive name match)
        from sqlalchemy import func as sa_func
        agent = (
            db.query(Agent)
            .filter(sa_func.lower(Agent.name) == rec.agent_name.lower(), Agent.workspace_id == ws_id)
            .first()
        )
        if not agent:
            agent = Agent(
                name=rec.agent_name,
                emoji="🤖",
                model=rec.model or "",
                workspace_id=ws_id,
            )
            db.add(agent)
            db.flush()
            created_agents.append(rec.agent_name)

        record_date = date.fromisoformat(rec.date)

        # Upsert: find existing by agent_id + date + model
        existing = (
            db.query(Cost)
            .filter(
                Cost.agent_id == agent.id,
                Cost.date == record_date,
                Cost.model == (rec.model or ""),
                Cost.workspace_id == ws_id,
            )
            .first()
        )
        if existing:
            existing.input_tokens = rec.input_tokens
            existing.output_tokens = rec.output_tokens
            existing.cost_usd = rec.cost_usd
            updated += 1
        else:
            cost = Cost(
                agent_id=agent.id,
                date=record_date,
                input_tokens=rec.input_tokens,
                output_tokens=rec.output_tokens,
                cost_usd=rec.cost_usd,
                model=rec.model or "",
                workspace_id=ws_id,
            )
            db.add(cost)

        ingested += 1

    db.commit()
    return BulkIngestResponse(
        ingested=ingested,
        created_agents=created_agents,
        updated=updated,
    )


@router.get("", response_model=list[CostResponse])
def list_costs(
    agent_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws_id = user.get("workspace_id", 1)
    q = db.query(Cost).filter(Cost.workspace_id == ws_id)

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
    ws_id = user.get("workspace_id", 1)
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
        .filter(Cost.workspace_id == ws_id)
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
