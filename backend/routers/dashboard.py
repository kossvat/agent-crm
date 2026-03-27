"""Dashboard endpoint — summary with period filter."""

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import Agent, Task, Cost, Alert, TaskStatus
from backend.schemas import DashboardResponse, AgentResponse, AlertResponse
from backend.auth import get_current_user

router = APIRouter(prefix="/api", tags=["dashboard"])


def _period_range(period: str) -> tuple[date, date]:
    """Return (start_date, end_date) for a period filter."""
    today = date.today()
    if period == "today":
        return today, today
    elif period == "week":
        start = today - timedelta(days=today.weekday())  # Monday
        return start, start + timedelta(days=6)
    elif period == "month":
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return start, end
    else:
        return date(2000, 1, 1), date(2099, 12, 31)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    period: str = Query("all", pattern="^(today|week|month|all)$"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dashboard with optional period filter (today/week/month/all)."""
    ws_id = user.get("workspace_id", 1)

    agents = db.query(Agent).filter(Agent.workspace_id == ws_id).all()
    start_date, end_date = _period_range(period)

    # Active tasks — filtered by workspace + deadline within period
    task_q = db.query(Task).filter(Task.workspace_id == ws_id, Task.status != TaskStatus.done)
    if period != "all":
        start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
        task_q = task_q.filter(
            (Task.deadline.between(start_dt, end_dt)) |
            ((Task.deadline.is_(None)) & (Task.status == TaskStatus.in_progress))
        )
    active_tasks = task_q.count()

    # Cost for period
    cost_q = db.query(func.coalesce(func.sum(Cost.cost_usd), 0.0)).filter(Cost.workspace_id == ws_id)
    if period != "all":
        cost_q = cost_q.filter(Cost.date.between(start_date, end_date))
    period_cost = float(cost_q.scalar())

    unread_alerts = db.query(Alert).filter(Alert.workspace_id == ws_id, Alert.is_read == False).count()
    recent_alerts = db.query(Alert).filter(Alert.workspace_id == ws_id).order_by(Alert.created.desc()).limit(10).all()

    return DashboardResponse(
        agent_count=len(agents),
        active_tasks=active_tasks,
        today_cost=period_cost,
        unread_alerts=unread_alerts,
        agents=[AgentResponse.model_validate(a) for a in agents],
        recent_alerts=[AlertResponse.model_validate(a) for a in recent_alerts],
    )
