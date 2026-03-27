"""Task CRUD endpoints with deadline support."""

from datetime import date, datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import Task, TaskStatus
from backend.schemas import TaskCreate, TaskUpdate, TaskResponse
from backend.auth import get_current_user, has_task_access


def _period_range(period: str) -> tuple[date, date]:
    today = date.today()
    if period == "today":
        return today, today
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    elif period == "month":
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return start, end
    return date(2000, 1, 1), date(2099, 12, 31)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def compute_deadline_status(task) -> Optional[str]:
    """Compute deadline status: ok / soon (< 1h) / overdue."""
    if not task.deadline or task.status == TaskStatus.done:
        return None
    now = datetime.now(timezone.utc)
    dl = task.deadline if task.deadline.tzinfo else task.deadline.replace(tzinfo=timezone.utc)
    diff = (dl - now).total_seconds()
    if diff < 0:
        return "overdue"
    if diff < 3600:
        return "soon"
    return "ok"


def task_to_response(task) -> dict:
    """Convert task ORM object to response dict with deadline_status."""
    resp = TaskResponse.model_validate(task)
    resp.deadline_status = compute_deadline_status(task)
    return resp


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    status: Optional[str] = Query(None),
    agent_id: Optional[int] = Query(None),
    priority: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    period: Optional[str] = Query(None, pattern="^(today|week|month|all)$"),
    has_deadline: Optional[bool] = Query(None),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List tasks with optional filters including time period and category."""
    q = db.query(Task).options(joinedload(Task.agent))

    # Access control: non-admin agents see only their tasks
    if not user.get("full_access") and user.get("agent_id"):
        q = q.filter((Task.agent_id == user["agent_id"]) | (Task.agent_id.is_(None)))

    if status:
        q = q.filter(Task.status == status)
    if agent_id:
        q = q.filter(Task.agent_id == agent_id)
    if priority:
        q = q.filter(Task.priority == priority)
    if category:
        q = q.filter(Task.category == category)
    if has_deadline is True:
        q = q.filter(Task.deadline.isnot(None))
    if has_deadline is False:
        q = q.filter(Task.deadline.is_(None))

    # Period filter — tasks with deadline in range OR in_progress without deadline
    if period and period != "all":
        start_date, end_date = _period_range(period)
        start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
        q = q.filter(
            (Task.deadline.between(start_dt, end_dt)) |
            ((Task.deadline.is_(None)) & (Task.status == TaskStatus.in_progress))
        )

    tasks = q.order_by(Task.created.desc()).all()
    return [task_to_response(t) for t in tasks]


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(
    data: TaskCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new task. Non-admin agents can only create tasks for themselves."""
    # Access control: agents can only create tasks for themselves
    if not user.get("full_access") and user.get("agent_id"):
        if data.agent_id and data.agent_id != user["agent_id"]:
            raise HTTPException(status_code=403, detail="Can only create tasks for yourself")
        data.agent_id = user["agent_id"]

    task = Task(**data.model_dump())
    if not task.created_by:
        task.created_by = user.get("username", str(user.get("user_id", "")))
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_to_response(task)


@router.get("/reminders", response_model=list[TaskResponse])
def get_pending_reminders(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get tasks that need reminder notifications.
    Returns tasks where:
    - deadline is set and not done
    - 1h reminder not sent yet AND deadline < 1h away
    - OR due reminder not sent yet AND deadline has passed
    """
    now = datetime.now(timezone.utc)
    one_hour_ahead = now + timedelta(hours=1)

    tasks = (
        db.query(Task)
        .options(joinedload(Task.agent))
        .filter(
            Task.deadline.isnot(None),
            Task.status != TaskStatus.done,
        )
        .all()
    )

    pending = []
    for t in tasks:
        dl = t.deadline if t.deadline.tzinfo else t.deadline.replace(tzinfo=timezone.utc)
        # 1h reminder: deadline within 1h and not sent
        if not t.reminder_1h_sent and dl <= one_hour_ahead:
            pending.append(t)
        # Due reminder: deadline passed and not sent
        elif not t.reminder_due_sent and dl <= now:
            pending.append(t)

    return [task_to_response(t) for t in pending]


@router.post("/reminders/{task_id}/ack")
def ack_reminder(
    task_id: int,
    reminder_type: str = Query(..., pattern="^(1h|due)$"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Acknowledge a reminder was sent (so it's not sent again)."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if reminder_type == "1h":
        task.reminder_1h_sent = True
    elif reminder_type == "due":
        task.reminder_due_sent = True

    db.commit()
    return {"ok": True}


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single task."""
    task = db.query(Task).options(joinedload(Task.agent)).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not has_task_access(user, task, "read"):
        raise HTTPException(status_code=403, detail="Access denied")
    return task_to_response(task)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    data: TaskUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a task (partial). Resets reminders if deadline changes."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not has_task_access(user, task, "write"):
        raise HTTPException(status_code=403, detail="Access denied")

    update_data = data.model_dump(exclude_unset=True)

    # Non-admin agents can't reassign tasks
    if not user.get("full_access") and "agent_id" in update_data:
        if update_data["agent_id"] != task.agent_id:
            raise HTTPException(status_code=403, detail="Cannot reassign tasks")

    # Reset reminder flags if deadline changes
    if "deadline" in update_data and update_data["deadline"] != task.deadline:
        task.reminder_1h_sent = False
        task.reminder_due_sent = False

    for key, val in update_data.items():
        setattr(task, key, val)

    db.commit()
    db.refresh(task)
    return task_to_response(task)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not has_task_access(user, task, "write"):
        raise HTTPException(status_code=403, detail="Access denied")
    db.delete(task)
    db.commit()
