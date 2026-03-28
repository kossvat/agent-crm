"""Spending data endpoints — reads from spending.db (read-only)."""

import os
import sqlite3
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DBSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Workspace

router = APIRouter(prefix="/api/spending", tags=["spending"])

SPENDING_DB = os.path.expanduser("~/projects/spending-tracker/spending.db")


def _get_conn():
    if not os.path.exists(SPENDING_DB):
        return None
    return sqlite3.connect(SPENDING_DB)


def _week_start() -> str:
    """Monday 00:00 UTC of current week."""
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")


def _get_budget(user: dict, db: DBSession) -> float:
    """Get monthly budget from workspace."""
    ws_id = user.get("workspace_id", 1)
    ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
    if ws and ws.monthly_budget:
        return float(ws.monthly_budget)
    return 100.0


@router.get("/current")
def spending_current(
    user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Current spending with budget info and per-model breakdown."""
    monthly_budget = _get_budget(user, db)
    weekly_budget = round(monthly_budget / 4.33, 2)

    conn = _get_conn()
    if not conn:
        return {
            "today": 0, "week": 0, "month": 0,
            "budget": {
                "monthly": monthly_budget, "weekly": weekly_budget,
                "weekly_used": 0, "weekly_pct": 0,
                "monthly_used": 0, "monthly_pct": 0,
            },
            "by_model": [],
            "agents": [],
        }

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_start = _week_start()
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")

    # Totals
    today_total = conn.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM daily_summary WHERE date = ?", (today,)
    ).fetchone()[0]

    week_total = conn.execute(
        "SELECT COALESCE(SUM(cost_total), 0) FROM usage_log WHERE date >= ?", (week_start,)
    ).fetchone()[0]

    month_total = conn.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM daily_summary WHERE date >= ?", (month_start,)
    ).fetchone()[0]

    # Per-model breakdown (current week)
    model_rows = conn.execute("""
        SELECT COALESCE(NULLIF(model, ''), 'unknown') as m,
               SUM(cost_total) as cost,
               COUNT(*) as msgs
        FROM usage_log
        WHERE date >= ?
        GROUP BY m
        ORDER BY cost DESC
    """, (week_start,)).fetchall()

    by_model = []
    for m, cost, msgs in model_rows:
        pct = round(cost / weekly_budget * 100, 1) if weekly_budget > 0 else 0
        by_model.append({
            "model": m,
            "cost": round(float(cost), 2),
            "messages": msgs,
            "pct": min(pct, 999.9),
        })

    # Per-agent (today)
    agents = conn.execute(
        "SELECT agent, total_cost, total_messages FROM daily_summary WHERE date = ? ORDER BY total_cost DESC",
        (today,)
    ).fetchall()

    conn.close()

    week_used = round(float(week_total), 2)
    month_used = round(float(month_total), 2)

    return {
        "today": round(float(today_total), 2),
        "week": week_used,
        "month": month_used,
        "budget": {
            "monthly": monthly_budget,
            "weekly": weekly_budget,
            "weekly_used": week_used,
            "weekly_pct": round(min(week_used / weekly_budget * 100, 999.9), 1) if weekly_budget > 0 else 0,
            "monthly_used": month_used,
            "monthly_pct": round(min(month_used / monthly_budget * 100, 999.9), 1) if monthly_budget > 0 else 0,
        },
        "by_model": by_model,
        "agents": [{"agent": r[0], "cost": round(float(r[1]), 2), "messages": r[2]} for r in agents],
    }


@router.get("/models-timeline")
def spending_models_timeline(
    range: str = Query("week", pattern="^(week|month)$"),
    user: dict = Depends(get_current_user),
):
    """Per-model daily costs for chart rendering."""
    conn = _get_conn()
    if not conn:
        return {"models": [], "labels": [], "datasets": {}}

    days = 7 if range == "week" else 30
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT date, COALESCE(NULLIF(model, ''), 'unknown') as m, SUM(cost_total) as cost
        FROM usage_log
        WHERE date >= ?
        GROUP BY date, m
        ORDER BY date
    """, (cutoff,)).fetchall()
    conn.close()

    # Collect all dates and models
    all_dates = sorted(set(r[0] for r in rows))
    all_models = sorted(set(r[1] for r in rows))

    # Build datasets
    model_data = {m: {} for m in all_models}
    for date, model, cost in rows:
        model_data[model][date] = round(float(cost), 2)

    datasets = {}
    for m in all_models:
        datasets[m] = [model_data[m].get(d, 0) for d in all_dates]

    return {
        "models": all_models,
        "labels": [d[5:] for d in all_dates],  # "03-22" format
        "datasets": datasets,
    }


@router.get("/timeline")
def spending_timeline(
    range: str = Query("week", pattern="^(day|week|month)$"),
    agent: str = Query(None),
    user: dict = Depends(get_current_user),
):
    """Timeline data for charts. day=hourly, week/month=daily. Optional agent filter."""
    conn = _get_conn()
    if not conn:
        return {"labels": [], "data": [], "range": range}

    if range == "day":
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        if agent:
            rows = conn.execute("""
                SELECT strftime('%H', timestamp) as hour, SUM(cost_total) as cost
                FROM usage_log WHERE timestamp > ? AND agent = ?
                GROUP BY hour ORDER BY hour
            """, (cutoff, agent)).fetchall()
        else:
            rows = conn.execute("""
                SELECT strftime('%H', timestamp) as hour, SUM(cost_total) as cost
                FROM usage_log WHERE timestamp > ?
                GROUP BY hour ORDER BY hour
            """, (cutoff,)).fetchall()
        labels = [f"{r[0]}:00" for r in rows]
        data = [round(float(r[1]), 3) for r in rows]
    else:
        days = 7 if range == "week" else 30
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        if agent:
            rows = conn.execute("""
                SELECT date, SUM(total_cost) as cost
                FROM daily_summary WHERE date >= ? AND agent = ?
                GROUP BY date ORDER BY date
            """, (cutoff, agent)).fetchall()
        else:
            rows = conn.execute("""
                SELECT date, SUM(total_cost) as cost
                FROM daily_summary WHERE date >= ?
                GROUP BY date ORDER BY date
            """, (cutoff,)).fetchall()
        labels = [r[0] for r in rows]
        data = [round(float(r[1]), 2) for r in rows]

    conn.close()
    return {"labels": labels, "data": data, "range": range}


@router.get("/sessions")
def spending_sessions(user: dict = Depends(get_current_user)):
    """Today's sessions grouped by agent + session_id, ordered by cost."""
    conn = _get_conn()
    if not conn:
        return []

    today_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    rows = conn.execute("""
        SELECT agent, session_id, SUM(cost_total) as cost, COUNT(*) as messages,
               MAX(timestamp) as last_active
        FROM usage_log WHERE timestamp > ?
        GROUP BY agent, session_id ORDER BY cost DESC LIMIT 20
    """, (today_start,)).fetchall()
    conn.close()

    return [
        {
            "session_id": r[1] or "unknown",
            "agent": r[0] or "unknown",
            "cost": round(float(r[2]), 2),
            "messages": r[3],
            "last_active": r[4],
        }
        for r in rows
    ]


@router.get("/anomalies")
def spending_anomalies(user: dict = Depends(get_current_user)):
    """Recent anomalies from spending.db alerts table."""
    conn = _get_conn()
    if not conn:
        return []

    rows = conn.execute("""
        SELECT id, timestamp, alert_type, message, resolved
        FROM alerts ORDER BY timestamp DESC LIMIT 50
    """).fetchall()
    conn.close()

    return [
        {"id": r[0], "timestamp": r[1], "type": r[2], "message": r[3], "resolved": bool(r[4])}
        for r in rows
    ]
