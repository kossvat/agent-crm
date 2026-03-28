"""Spending data endpoints — reads from spending.db (read-only).

Uses 5-hour rolling window to match Anthropic's rate limit system.
"""

import os
import sqlite3
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DBSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Workspace
from backend.plan_limits import get_plan_by_budget, get_model_limit, get_all_limit

router = APIRouter(prefix="/api/spending", tags=["spending"])

SPENDING_DB = os.path.expanduser("~/projects/spending-tracker/spending.db")

ROLLING_WINDOW_HOURS = 5


def _get_conn():
    if not os.path.exists(SPENDING_DB):
        return None
    return sqlite3.connect(SPENDING_DB)


def _get_budget(user: dict, db: DBSession) -> float:
    """Get monthly budget from workspace."""
    ws_id = user.get("workspace_id", 1)
    ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
    if ws and ws.monthly_budget:
        return float(ws.monthly_budget)
    return 100.0


def _get_agent_model_map(conn) -> dict:
    """Build agent -> most-used model map for inferring NULL models."""
    rows = conn.execute("""
        SELECT agent, model, COUNT(*) as cnt
        FROM usage_log
        WHERE model IS NOT NULL AND model != ''
        GROUP BY agent, model
        ORDER BY agent, cnt DESC
    """).fetchall()
    result = {}
    for agent, model, cnt in rows:
        if agent not in result:
            result[agent] = model
    return result


@router.get("/current")
def spending_current(
    user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Current spending with 5hr rolling window usage like Anthropic."""
    monthly_budget = _get_budget(user, db)
    plan = get_plan_by_budget(monthly_budget)
    all_limit = get_all_limit(plan)

    conn = _get_conn()
    if not conn:
        return {
            "today": 0, "week": 0, "month": 0,
            "plan": plan["name"],
            "window_hours": ROLLING_WINDOW_HOURS,
            "usage": {"all": {"used": 0, "limit": all_limit, "pct": 0}, "models": []},
            "by_model": [],
            "agents": [],
        }

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")
    window_start = (now - timedelta(hours=ROLLING_WINDOW_HOURS)).isoformat()

    agent_model_map = _get_agent_model_map(conn)

    # === Cost totals (for display) ===
    today_total = conn.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM daily_summary WHERE date = ?", (today,)
    ).fetchone()[0]

    month_total = conn.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM daily_summary WHERE date >= ?", (month_start,)
    ).fetchone()[0]

    # === 5hr rolling window — output tokens per model ===
    window_rows = conn.execute("""
        SELECT COALESCE(NULLIF(model, ''), '') as m,
               agent,
               SUM(output_tokens) as out_tokens,
               SUM(cost_total) as cost,
               COUNT(*) as msgs
        FROM usage_log
        WHERE timestamp >= ?
        GROUP BY m, agent
    """, (window_start,)).fetchall()

    # Aggregate by resolved model
    model_usage = {}  # model -> {tokens, cost, msgs}
    total_tokens = 0
    total_cost_window = 0.0
    for m, agent, tokens, cost, msgs in window_rows:
        resolved = m if m else agent_model_map.get(agent, 'unknown')
        if resolved not in model_usage:
            model_usage[resolved] = {"tokens": 0, "cost": 0.0, "msgs": 0}
        model_usage[resolved]["tokens"] += (tokens or 0)
        model_usage[resolved]["cost"] += float(cost or 0)
        model_usage[resolved]["msgs"] += msgs
        total_tokens += (tokens or 0)
        total_cost_window += float(cost or 0)

    # Build per-model usage with limits
    models_usage = []
    for model_name, data in sorted(model_usage.items(), key=lambda x: -x[1]["tokens"]):
        limit = get_model_limit(plan, model_name)
        pct = round(data["tokens"] / limit * 100, 1) if limit > 0 else 0
        models_usage.append({
            "model": model_name,
            "used": data["tokens"],
            "limit": limit,
            "pct": min(pct, 100.0),
            "cost": round(data["cost"], 2),
            "messages": data["msgs"],
        })

    # All-models combined
    all_pct = round(total_tokens / all_limit * 100, 1) if all_limit > 0 else 0

    # Calculate window reset time
    # Find oldest message in window to estimate when tokens start expiring
    oldest_in_window = conn.execute(
        "SELECT MIN(timestamp) FROM usage_log WHERE timestamp >= ?", (window_start,)
    ).fetchone()[0]

    resets_in_minutes = None
    if oldest_in_window:
        try:
            oldest_dt = datetime.fromisoformat(oldest_in_window.replace('Z', '+00:00'))
            reset_at = oldest_dt + timedelta(hours=ROLLING_WINDOW_HOURS)
            diff = reset_at - now
            if diff.total_seconds() > 0:
                resets_in_minutes = int(diff.total_seconds() / 60)
        except (ValueError, TypeError):
            pass

    # Per-agent (today)
    agents = conn.execute(
        "SELECT agent, total_cost, total_messages FROM daily_summary WHERE date = ? ORDER BY total_cost DESC",
        (today,)
    ).fetchall()

    conn.close()

    return {
        "today": round(float(today_total), 2),
        "month": round(float(month_total), 2),
        "plan": plan["name"],
        "window_hours": ROLLING_WINDOW_HOURS,
        "resets_in_minutes": resets_in_minutes,
        "usage": {
            "all": {
                "used": total_tokens,
                "limit": all_limit,
                "pct": min(all_pct, 100.0),
                "cost": round(total_cost_window, 2),
            },
            "models": models_usage,
        },
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
