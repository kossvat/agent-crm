"""SQLAlchemy ORM models."""

import enum
from datetime import datetime, date, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Date,
    ForeignKey, Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from backend.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# --- Enums ---

class TierType(str, enum.Enum):
    hobby = "hobby"
    builder = "builder"
    pro = "pro"


TIER_AGENT_LIMITS = {
    TierType.hobby: 3,
    TierType.builder: 10,
    TierType.pro: -1,  # unlimited
}


class AgentStatus(str, enum.Enum):
    active = "active"
    idle = "idle"
    error = "error"


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class CronStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    error = "error"


class AlertType(str, enum.Enum):
    error = "error"
    warning = "warning"
    info = "info"


# --- Multi-tenant Models ---

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    name = Column(String(100), nullable=False)
    created = Column(DateTime(timezone=True), default=utcnow)
    onboarding_complete = Column(Boolean, default=False)
    is_superadmin = Column(Boolean, default=False)

    workspaces = relationship("Workspace", back_populates="owner")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    openclaw_url = Column(String(500), nullable=True)
    api_key = Column(String(500), nullable=True)
    tier = Column(SAEnum(TierType), default=TierType.hobby)
    agent_limit = Column(Integer, default=3)
    monthly_budget = Column(Float, default=100.0)
    created = Column(DateTime(timezone=True), default=utcnow)

    owner = relationship("User", back_populates="workspaces")


# --- Models ---

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    emoji = Column(String(10), default="🤖")
    model = Column(String(100), default="")
    status = Column(SAEnum(AgentStatus), default=AgentStatus.idle)
    session_key = Column(String(255), default="")
    last_active = Column(DateTime(timezone=True), nullable=True)
    role = Column(String(100), default="")
    bio = Column(Text, default="")
    daily_cost = Column(Float, default=0.0)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    created = Column(DateTime(timezone=True), default=utcnow)

    tasks = relationship("Task", back_populates="agent")
    crons = relationship("Cron", back_populates="agent")
    costs = relationship("Cost", back_populates="agent")
    alerts = relationship("Alert", back_populates="agent")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    status = Column(SAEnum(TaskStatus), default=TaskStatus.todo)
    priority = Column(SAEnum(TaskPriority), default=TaskPriority.medium)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    created_by = Column(String(100), default="")
    deadline = Column(DateTime(timezone=True), nullable=True)
    category = Column(String(50), default="")
    reminder_1h_sent = Column(Boolean, default=False)
    reminder_due_sent = Column(Boolean, default=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    created = Column(DateTime(timezone=True), default=utcnow)
    updated = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    agent = relationship("Agent", back_populates="tasks")


class Cron(Base):
    __tablename__ = "crons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    schedule = Column(String(100), nullable=False)
    command = Column(Text, default="")
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    status = Column(SAEnum(CronStatus), default=CronStatus.active)
    last_run = Column(DateTime(timezone=True), nullable=True)
    next_run = Column(DateTime(timezone=True), nullable=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    created = Column(DateTime(timezone=True), default=utcnow)

    agent = relationship("Agent", back_populates="crons")


class Cost(Base):
    __tablename__ = "costs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    date = Column(Date, nullable=False, default=lambda: date.today())
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    model = Column(String(100), default="")
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)

    agent = relationship("Agent", back_populates="costs")


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    content = Column(Text, default="")
    source = Column(String(50), default="manual")  # "manual", "memory", "auto"
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    created = Column(DateTime(timezone=True), default=utcnow)
    updated = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    agent = relationship("Agent")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    type = Column(SAEnum(AlertType), default=AlertType.info)
    message = Column(Text, nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    created = Column(DateTime(timezone=True), default=utcnow)
    is_read = Column(Boolean, default=False)

    agent = relationship("Agent", back_populates="alerts")


class InviteCode(Base):
    """Beta invite codes — required for new user registration."""
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(32), unique=True, nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # null = system-generated
    used_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    max_uses = Column(Integer, default=1)
    use_count = Column(Integer, default=0)
    note = Column(String(255), default="")  # e.g. "for Discord giveaway"
    created = Column(DateTime(timezone=True), default=utcnow)
    expires = Column(DateTime(timezone=True), nullable=True)


class AgentFile(Base):
    """Stored agent files (SOUL.md, IDENTITY.md, etc.) for prod environments without local filesystem."""
    __tablename__ = "agent_files"
    __table_args__ = (
        UniqueConstraint("agent_id", "filename", "workspace_id", name="uq_agent_file_workspace"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    filename = Column(String(255), nullable=False)  # e.g. "SOUL.md"
    content = Column(Text, default="")
    size = Column(Integer, default=0)  # bytes
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    updated = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    agent = relationship("Agent")


class PendingCommand(Base):
    """Command queue for bidirectional CRM ↔ OpenClaw sync."""
    __tablename__ = "pending_commands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    command_type = Column(String(50), nullable=False)  # "change_model", "restart_gateway", etc.
    payload = Column(Text, nullable=False)  # JSON: {"agent_name": "Caramel", "model": "claude-opus-4-6"}
    status = Column(String(20), default="pending")  # pending, applied, failed
    created = Column(DateTime(timezone=True), default=utcnow)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)


class ConnectToken(Base):
    """Magic link token for remote agent bootstrap."""
    __tablename__ = "connect_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created = Column(DateTime(timezone=True), default=utcnow)
    expires = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
