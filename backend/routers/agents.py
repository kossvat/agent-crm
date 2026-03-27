"""Agent CRUD endpoints."""

import logging
import os
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Agent, Workspace, TIER_AGENT_LIMITS
from backend.schemas import AgentResponse, AgentCreate, AgentUpdate
from backend.auth import get_current_user
from backend.services.openclaw import (
    get_config_agent_models,
    update_agent_model,
    is_restart_pending,
    restart_gateway,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])
log = logging.getLogger("agent-crm.agents")

# Model list cache
_models_cache: dict = {"models": [], "fetched_at": 0}
CACHE_TTL = 3600  # 1 hour


@router.get("", response_model=list[AgentResponse])
def list_agents(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all agents in the current workspace."""
    ws_id = user.get("workspace_id", 1)
    agents = db.query(Agent).filter(Agent.workspace_id == ws_id).order_by(Agent.name).all()

    # Sync models from openclaw.json → DB
    try:
        config_models = get_config_agent_models()
        for agent in agents:
            if agent.session_key and agent.session_key in config_models:
                config_model = config_models[agent.session_key]
                if config_model and agent.model != config_model:
                    agent.model = config_model
                    log.info(f"Synced model for {agent.name}: {config_model}")
        db.commit()
    except Exception as e:
        log.warning(f"Failed to sync models from config: {e}")
        db.rollback()

    return agents


@router.get("/models", response_model=list[str])
def list_models(user: dict = Depends(get_current_user)):
    """List available Anthropic models. Cached for 1 hour."""
    now = time.time()
    if _models_cache["models"] and (now - _models_cache["fetched_at"]) < CACHE_TTL:
        return _models_cache["models"]

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            resp = httpx.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = sorted([m["id"] for m in data.get("data", [])])
                if models:
                    _models_cache["models"] = models
                    _models_cache["fetched_at"] = now
                    return models
        except Exception as e:
            log.warning(f"Anthropic models API failed: {e}")

    fallback = [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-35-20241022",
    ]
    return fallback


@router.get("/restart-status")
def get_restart_status(user: dict = Depends(get_current_user)):
    """Check if a gateway restart is pending after model changes."""
    return {"restart_pending": is_restart_pending()}


@router.post("/restart")
def do_restart(user: dict = Depends(get_current_user)):
    """Restart OpenClaw gateway to apply config changes. Owner only."""
    if not user.get("full_access") and not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    success, message = restart_gateway()
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {"ok": True, "message": message}


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single agent by ID."""
    ws_id = user.get("workspace_id", 1)
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.workspace_id == ws_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent(
    agent_id: int,
    data: AgentUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an agent (model, role, bio, status). Owner/full_access only."""
    if not user.get("full_access") and not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    ws_id = user.get("workspace_id", 1)
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.workspace_id == ws_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(agent, key, val)

    # Sync model change to openclaw.json
    if "model" in update_data and agent.session_key:
        try:
            updated = update_agent_model(agent.session_key, update_data["model"])
            if not updated:
                log.warning(f"Agent {agent.session_key} not found in openclaw.json")
        except Exception as e:
            log.error(f"Failed to update openclaw.json: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"DB updated but config write failed: {e}",
            )

    db.commit()
    db.refresh(agent)
    return agent


@router.post("", response_model=AgentResponse, status_code=201)
def create_agent(
    data: AgentCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new agent. Checks tier agent limit."""
    ws_id = user.get("workspace_id", 1)

    # Tier limit check
    workspace = db.query(Workspace).filter(Workspace.id == ws_id).first()
    if workspace:
        limit = workspace.agent_limit
        if limit >= 0:  # -1 = unlimited
            current_count = db.query(Agent).filter(Agent.workspace_id == ws_id).count()
            if current_count >= limit:
                raise HTTPException(
                    status_code=403,
                    detail=f"Agent limit reached ({limit}). Upgrade your plan to add more agents.",
                )

    existing = db.query(Agent).filter(Agent.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Agent with this name already exists")

    agent = Agent(**data.model_dump(), workspace_id=ws_id)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent
