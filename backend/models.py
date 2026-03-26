"""SQLAlchemy ORM models."""

import enum
from datetime import datetime, date, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Date,
    ForeignKey, Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from backend.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# --- Enums ---

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
    daily_cost = Column(Float, default=0.0)
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
    reminder_1h_sent = Column(Boolean, default=False)
    reminder_due_sent = Column(Boolean, default=False)
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

    agent = relationship("Agent", back_populates="costs")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    type = Column(SAEnum(AlertType), default=AlertType.info)
    message = Column(Text, nullable=False)
    created = Column(DateTime(timezone=True), default=utcnow)
    is_read = Column(Boolean, default=False)

    agent = relationship("Agent", back_populates="alerts")
