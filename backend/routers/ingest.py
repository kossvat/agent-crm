"""Ingest router — receives usage data from remote agents via workspace_token."""

from datetime import datetime, date, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import Agent, Cost
from backend.auth import decode_workspace_token

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


# --- Schemas ---

class UsageRecord(BaseModel):
    session_id: Optional[str] = None
    agent_name: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: Optional[str] = None  # ISO 8601


class IngestRequest(BaseModel):
    records: list[UsageRecord]


class IngestResponse(BaseModel):
    ingested: int
    created_agents: list[str]


# --- Auth helper ---

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


# --- Endpoint ---

@router.post("", response_model=IngestResponse)
def ingest_usage(
    data: IngestRequest,
    request: Request,
):
    """Ingest batch of usage records from a remote agent.
    
    Auth: workspace_token (Bearer header).
    Deduplication: upsert by agent_id + date + model (sums tokens/cost).
    Auto-creates agents that don't exist in the workspace.
    """
    ws_id = _get_workspace_id(request)

    db: Session = SessionLocal()
    try:
        created_agents: list[str] = []
        ingested = 0

        for rec in data.records:
            # Find or create agent
            agent = (
                db.query(Agent)
                .filter(Agent.name == rec.agent_name, Agent.workspace_id == ws_id)
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

            # Parse date from timestamp
            record_date = date.today()
            if rec.timestamp:
                try:
                    dt = datetime.fromisoformat(rec.timestamp.replace("Z", "+00:00"))
                    record_date = dt.date()
                except (ValueError, AttributeError):
                    pass

            # Upsert cost: find existing by agent_id + date + model
            existing_cost = (
                db.query(Cost)
                .filter(
                    Cost.agent_id == agent.id,
                    Cost.date == record_date,
                    Cost.model == (rec.model or ""),
                    Cost.workspace_id == ws_id,
                )
                .first()
            )
            if existing_cost:
                existing_cost.input_tokens += rec.input_tokens
                existing_cost.output_tokens += rec.output_tokens
                existing_cost.cost_usd += rec.cost_usd
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

        return IngestResponse(
            ingested=ingested,
            created_agents=created_agents,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
