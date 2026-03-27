"""Daily Journal endpoints."""

import logging
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import JournalEntry, Cost
from backend.schemas import (
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalEntryResponse,
    JournalDayResponse,
)
from backend.auth import get_current_user

router = APIRouter(prefix="/api/journal", tags=["journal"])
log = logging.getLogger("agent-crm.journal")

OPENCLAW_DIR = os.path.expanduser("~/.openclaw")

# Workspace dirs per agent
AGENT_WORKSPACES = {
    "main": "workspace",
    "sixteen": "workspace-sixteen",
    "career": "workspace-career",
    "social": "workspace-social",
}


@router.get("", response_model=list[JournalDayResponse])
def list_journal_days(
    limit: int = Query(14, ge=1, le=90),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List journal days with entries, most recent first."""
    entries = (
        db.query(JournalEntry)
        .options(joinedload(JournalEntry.agent))
        .order_by(JournalEntry.date.desc(), JournalEntry.created.desc())
        .all()
    )

    # Group by date
    days: dict[date, list] = {}
    for e in entries:
        days.setdefault(e.date, []).append(e)

    # Get cost per day
    cost_rows = (
        db.query(Cost.date, Cost.cost_usd)
        .order_by(Cost.date.desc())
        .all()
    )
    daily_costs: dict[date, float] = {}
    for d, c in cost_rows:
        daily_costs[d] = daily_costs.get(d, 0) + c

    result = []
    for d in sorted(days.keys(), reverse=True)[:limit]:
        result.append(JournalDayResponse(
            date=d,
            entries=[JournalEntryResponse.model_validate(e) for e in days[d]],
            total_cost=round(daily_costs.get(d, 0), 2),
        ))

    return result


@router.post("", response_model=JournalEntryResponse, status_code=201)
def create_journal_entry(
    data: JournalEntryCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a journal entry."""
    entry = JournalEntry(**data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=JournalEntryResponse)
def update_journal_entry(
    entry_id: int,
    data: JournalEntryUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a journal entry."""
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(entry, key, val)

    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_journal_entry(
    entry_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a journal entry."""
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()


@router.post("/import-memory", response_model=dict)
def import_from_memory(
    target_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import journal entries from agent memory/ files.

    Scans each agent's workspace/memory/YYYY-MM-DD.md files.
    Skips entries that already exist (same date + agent + source=memory).
    """
    if not user.get("full_access") and not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="Owner only")

    from backend.models import Agent
    agents = {a.session_key: a for a in db.query(Agent).all() if a.session_key}

    imported = 0
    for agent_key, ws_dir in AGENT_WORKSPACES.items():
        agent = agents.get(agent_key)
        if not agent:
            continue

        memory_dir = Path(OPENCLAW_DIR) / ws_dir / "memory"
        if not memory_dir.exists():
            continue

        for md_file in sorted(memory_dir.glob("*.md")):
            # Extract date from filename (YYYY-MM-DD.md)
            match = re.match(r"^(\d{4}-\d{2}-\d{2})\.md$", md_file.name)
            if not match:
                continue

            file_date = match.group(1)
            if target_date and file_date != target_date:
                continue

            entry_date = datetime.strptime(file_date, "%Y-%m-%d").date()

            # Skip if already imported
            existing = (
                db.query(JournalEntry)
                .filter(
                    JournalEntry.date == entry_date,
                    JournalEntry.agent_id == agent.id,
                    JournalEntry.source == "memory",
                )
                .first()
            )
            if existing:
                continue

            content = md_file.read_text(encoding="utf-8").strip()
            if not content:
                continue

            entry = JournalEntry(
                date=entry_date,
                agent_id=agent.id,
                content=content,
                source="memory",
            )
            db.add(entry)
            imported += 1

    db.commit()
    return {"imported": imported}
