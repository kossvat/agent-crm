"""Pydantic v2 schemas for request/response validation."""

from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict


# --- User / Workspace ---

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: Optional[int] = None
    email: Optional[str] = None
    name: str
    created: datetime
    onboarding_complete: bool


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_id: int
    openclaw_url: Optional[str] = None
    tier: str
    agent_limit: int
    created: datetime


# --- Agent ---

class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    emoji: Optional[str] = "🤖"
    model: Optional[str] = ""
    role: Optional[str] = ""
    bio: Optional[str] = ""
    status: Optional[str] = "idle"
    session_key: Optional[str] = ""
    last_active: Optional[datetime] = None
    daily_cost: Optional[float] = 0.0
    created: Optional[datetime] = None


class AgentCreate(BaseModel):
    name: str
    emoji: str = "🤖"
    model: str = ""
    role: str = ""
    bio: str = ""
    session_key: str = ""


class AgentUpdate(BaseModel):
    model: Optional[str] = None
    role: Optional[str] = None
    bio: Optional[str] = None
    status: Optional[str] = None


# --- Task ---

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "todo"
    priority: str = "medium"
    category: str = ""
    agent_id: Optional[int] = None
    created_by: str = ""
    deadline: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: str
    priority: str
    category: str = ""
    agent_id: Optional[int]
    created_by: str
    deadline: Optional[datetime]
    deadline_status: Optional[str] = None  # "ok", "soon", "overdue"
    created: datetime
    updated: datetime
    agent: Optional[AgentResponse] = None


# --- Cron ---

class CronResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    schedule: str
    command: str
    agent_id: Optional[int]
    status: str
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    created: datetime


# --- Cron (OpenClaw format) ---

class CronOCResponse(BaseModel):
    """Cron job as returned from OpenClaw CLI."""
    id: str
    name: str
    schedule: str
    agent_id: Optional[str] = None
    enabled: bool = True
    description: str = ""
    model: str = ""
    next_run: Optional[str] = None


# --- Cost ---

class CostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    date: date
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


class CostSummary(BaseModel):
    agent_id: int
    agent_name: str
    agent_emoji: str
    total_cost: float
    total_input_tokens: int
    total_output_tokens: int


# --- Journal ---

class JournalEntryCreate(BaseModel):
    date: date
    agent_id: Optional[int] = None
    content: str
    source: str = "manual"


class JournalEntryUpdate(BaseModel):
    content: Optional[str] = None
    agent_id: Optional[int] = None


class JournalEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    agent_id: Optional[int]
    content: str
    source: str
    created: datetime
    updated: datetime
    agent: Optional[AgentResponse] = None


class JournalDayResponse(BaseModel):
    date: date
    entries: list[JournalEntryResponse]
    total_cost: float = 0.0


# --- Alert ---

class AlertCreate(BaseModel):
    agent_id: Optional[int] = None
    type: str = "info"
    message: str


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: Optional[int]
    type: str
    message: str
    created: datetime
    is_read: bool


# --- Dashboard ---

class DashboardResponse(BaseModel):
    agent_count: int
    active_tasks: int
    today_cost: float
    unread_alerts: int
    agents: list[AgentResponse]
    recent_alerts: list[AlertResponse]
