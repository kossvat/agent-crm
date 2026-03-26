"""Agent CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Agent
from backend.schemas import AgentResponse, AgentCreate
from backend.auth import get_current_user

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=list[AgentResponse])
def list_agents(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all agents."""
    return db.query(Agent).order_by(Agent.name).all()


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single agent by ID."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("", response_model=AgentResponse, status_code=201)
def create_agent(
    data: AgentCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new agent."""
    existing = db.query(Agent).filter(Agent.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Agent with this name already exists")

    agent = Agent(**data.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent
