"""Spending data endpoints — reads from spending.db (read-only).

Uses 5-hour rolling window to match Anthropic's rate limit system.

Fallback: when spending.db is not available (production), reads from CRM's
`costs` table in PostgreSQL, filtered by the current user's workspace_id.
"""

import os
import sqlite3
from datetime import datetime, date as date_type, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func, cast, String

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Workspace, Cost, Agent
from backend.plan_limits import get_plan_by_budget

router = APIRouter(prefix="/api/spending", tags=["spending"])

SPENDING_DB = os.path.expanduser("~/projects/spending-tracker/spending.db")

ROLLING_WINDOW_HOURS = 5


def _get_conn():
    if not os.path.exists(SPENDING_DB):
        return None
    return sqlite3.connect(SPENDING_DB)


# ---------------------------------------------------------------------------
# CRM costs table helpers (fallback when spending.db is unavailable)
# ---------------------------------------------------------------------------

def _costs_current(ws_id: int, db: DBSession) -> dict:
    """Build /current response from CRM costs table."""
    now = datetime.now(timezone.utc)
    today = now.date()
    month_start = today.replace(day=1)

    # Today total
    today_total = (
        db.query(func.coalesce(func.sum(Cost.cost_usd), 0))
        .filter(Cost.workspace_id == ws_id, Cost.date == today)
        .scalar()
    )
    # Month total
    month_total = (
        db.query(func.coalesce(func.sum(Cost.cost_usd), 0))
        .filter(Cost.workspace_id == ws_id, Cost.date >= month_start)
        .scalar()
    )
    # Per-agent today
    agent_rows = (
        db.query(
            Agent.name,
            func.sum(Cost.cost_usd),
            func.sum(Cost.input_tokens + Cost.output_tokens),
        )
        .join(Agent, Agent.id == Cost.agent_id)
        .filter(Cost.workspace_id == ws_id, Cost.date == today)
        .group_by(Agent.name)
        .order_by(func.sum(Cost.cost_usd).desc())
        .all()
    )
    agents = [
        {"agent": name, "cost": round(float(cost or 0), 2), "messages": int(tokens or 0)}
        for name, cost, tokens in agent_rows
    ]
    return {
        "today": round(float(today_total), 2),
        "month": round(float(month_total), 2),
        "agents": agents,
    }


def _costs_timeline(ws_id: int, db: DBSession, range_: str, agent_filter: str | None) -> dict:
    """Build /timeline response from CRM costs table."""
    days = {"day": 1, "week": 7, "month": 30}.get(range_, 7)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()

    q = db.query(Cost.date, func.sum(Cost.cost_usd)).filter(
        Cost.workspace_id == ws_id, Cost.date >= cutoff
    )
    if agent_filter:
        q = q.join(Agent, Agent.id == Cost.agent_id).filter(Agent.name == agent_filter)
    rows = q.group_by(Cost.date).order_by(Cost.date).all()

    labels = [str(r[0]) for r in rows]
    data = [round(float(r[1] or 0), 2) for r in rows]
    return {"labels": labels, "data": data, "range": range_}


def _costs_sessions(ws_id: int, db: DBSession) -> list:
    """Build /sessions response from CRM costs table (group by agent + date)."""
    today = datetime.now(timezone.utc).date()
    rows = (
        db.query(
            Agent.name,
            Cost.date,
            func.sum(Cost.cost_usd),
            func.sum(Cost.input_tokens + Cost.output_tokens),
        )
        .join(Agent, Agent.id == Cost.agent_id)
        .filter(Cost.workspace_id == ws_id, Cost.date == today)
        .group_by(Agent.name, Cost.date)
        .order_by(func.sum(Cost.cost_usd).desc())
        .limit(20)
        .all()
    )
    return [
        {
            "session_id": f"{name}-{str(d)}",
            "agent": name or "unknown",
            "cost": round(float(cost or 0), 2),
            "messages": int(tokens or 0),
            "last_active": str(d),
        }
        for name, d, cost, tokens in rows
    ]


def _costs_models_timeline(ws_id: int, db: DBSession, range_: str) -> dict:
    """Build /models-timeline response from CRM costs table."""
    days = 7 if range_ == "week" else 30
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()

    rows = (
        db.query(Cost.date, Cost.model, func.sum(Cost.cost_usd))
        .filter(Cost.workspace_id == ws_id, Cost.date >= cutoff)
        .group_by(Cost.date, Cost.model)
        .order_by(Cost.date)
        .all()
    )
    all_dates = sorted(set(str(r[0]) for r in rows))
    all_models = sorted(set((r[1] or "unknown") for r in rows))

    model_data = {m: {} for m in all_models}
    for d, model, cost in rows:
        resolved = model if model else "unknown"
        model_data[resolved][str(d)] = round(float(cost or 0), 2)

    datasets = {}
    for m in all_models:
        datasets[m] = [model_data[m].get(d, 0) for d in all_dates]

    return {
        "models": all_models,
        "labels": [d[5:] for d in all_dates],
        "datasets": datasets,
    }


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


def _get_weekly_reset_start(plan: dict) -> datetime:
    """Get the start of the current weekly period (last Saturday 8pm EST = Sunday 01:00 UTC)."""
    now = datetime.now(timezone.utc)
    reset_day = plan.get("weekly_reset_day", 6)  # 6=Sunday
    reset_hour = plan.get("weekly_reset_utc_hour", 1)

    # Find the most recent reset point
    days_since = (now.weekday() - reset_day) % 7
    last_reset = (now - timedelta(days=days_since)).replace(
        hour=reset_hour, minute=0, second=0, microsecond=0
    )
    if last_reset > now:
        last_reset -= timedelta(days=7)
    return last_reset


def _next_weekly_reset(plan: dict) -> datetime:
    """Get next weekly reset time."""
    return _get_weekly_reset_start(plan) + timedelta(days=7)


def _aggregate_by_model(rows, agent_model_map):
    """Aggregate usage rows by resolved model."""
    model_data = {}
    total_tokens = 0
    total_cost = 0.0
    for m, agent, tokens, cost, msgs in rows:
        resolved = m if m else agent_model_map.get(agent, 'unknown')
        if resolved not in model_data:
            model_data[resolved] = {"tokens": 0, "cost": 0.0, "msgs": 0}
        model_data[resolved]["tokens"] += (tokens or 0)
        model_data[resolved]["cost"] += float(cost or 0)
        model_data[resolved]["msgs"] += msgs
        total_tokens += (tokens or 0)
        total_cost += float(cost or 0)
    return model_data, total_tokens, total_cost


def _build_model_usage(model_data, limits):
    """Build per-model usage list with limits and percentages."""
    result = []
    for model_name, data in sorted(model_data.items(), key=lambda x: -x[1]["tokens"]):
        limit = limits.get(model_name, limits.get("_all", 1))
        pct = round(data["tokens"] / limit * 100, 1) if limit > 0 else 0
        result.append({
            "model": model_name,
            "used": data["tokens"],
            "limit": limit,
            "pct": min(pct, 999.9),
            "cost": round(data["cost"], 2),
            "messages": data["msgs"],
        })
    return result


@router.get("/current")
def spending_current(
    user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Current spending with dual rate limits like Anthropic: weekly + 5hr session."""
    monthly_budget = _get_budget(user, db)
    plan = get_plan_by_budget(monthly_budget)

    session_hours = plan.get("session_hours", 5)
    weekly_cost_limit = plan.get("weekly_cost_limit", 243)
    session_cost_limit = plan.get("session_cost_limit", 177)

    conn = _get_conn()
    if not conn:
        # Fallback: read from CRM costs table
        crm = _costs_current(user.get("workspace_id", 1), db)
        empty = {"used": 0, "limit": 0, "pct": 0, "models": []}
        return {
            "today": crm["today"], "month": crm["month"], "plan": plan["name"],
            "weekly": {**empty, "limit": weekly_cost_limit, "resets_in_minutes": 0},
            "session": {**empty, "limit": session_cost_limit, "resets_in_minutes": 0},
            "agents": crm["agents"],
        }

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")
    agent_model_map = _get_agent_model_map(conn)

    # === Cost totals ===
    today_total = conn.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM daily_summary WHERE date = ?", (today,)
    ).fetchone()[0]
    month_total = conn.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM daily_summary WHERE date >= ?", (month_start,)
    ).fetchone()[0]

    # === Weekly session (cost-based) ===
    # Note: timestamps in spending.db use ISO format with 'T' separator (2026-03-28T15:30:00Z)
    # SQLite string comparison requires matching format — use REPLACE to normalize
    weekly_start = _get_weekly_reset_start(plan)
    weekly_start_str = weekly_start.strftime("%Y-%m-%d %H:%M:%S")
    weekly_rows = conn.execute("""
        SELECT COALESCE(NULLIF(model, ''), '') as m, agent,
               SUM(output_tokens) as out_t, SUM(cost_total) as cost, COUNT(*) as msgs
        FROM usage_log WHERE REPLACE(REPLACE(timestamp, 'T', ' '), 'Z', '') >= ?
        GROUP BY m, agent
    """, (weekly_start_str,)).fetchall()

    w_model_data, w_total_tokens, w_total_cost = _aggregate_by_model(weekly_rows, agent_model_map)
    w_all_pct = round(w_total_cost / weekly_cost_limit * 100, 1) if weekly_cost_limit > 0 else 0

    # Per-model cost breakdown for weekly
    w_models = []
    for model_name, data in sorted(w_model_data.items(), key=lambda x: -x[1]["cost"]):
        pct = round(data["cost"] / weekly_cost_limit * 100, 1) if weekly_cost_limit > 0 else 0
        w_models.append({
            "model": model_name,
            "cost": round(data["cost"], 2),
            "messages": data["msgs"],
            "pct": min(pct, 999.9),
        })

    next_weekly = _next_weekly_reset(plan)
    w_reset_min = max(0, int((next_weekly - now).total_seconds() / 60))

    # === Current 5hr session (cost-based) ===
    session_start_str = (now - timedelta(hours=session_hours)).strftime("%Y-%m-%d %H:%M:%S")
    session_rows = conn.execute("""
        SELECT COALESCE(NULLIF(model, ''), '') as m, agent,
               SUM(output_tokens) as out_t, SUM(cost_total) as cost, COUNT(*) as msgs
        FROM usage_log WHERE REPLACE(REPLACE(timestamp, 'T', ' '), 'Z', '') >= ?
        GROUP BY m, agent
    """, (session_start_str,)).fetchall()

    s_model_data, s_total_tokens, s_total_cost = _aggregate_by_model(session_rows, agent_model_map)
    s_all_pct = round(s_total_cost / session_cost_limit * 100, 1) if session_cost_limit > 0 else 0

    # Per-model cost breakdown for session
    s_models = []
    for model_name, data in sorted(s_model_data.items(), key=lambda x: -x[1]["cost"]):
        pct = round(data["cost"] / session_cost_limit * 100, 1) if session_cost_limit > 0 else 0
        s_models.append({
            "model": model_name,
            "cost": round(data["cost"], 2),
            "messages": data["msgs"],
            "pct": min(pct, 999.9),
        })

    # Session reset: Anthropic shows when the window slides enough to drop usage
    # "Resets in X min" = when the oldest significant chunk expires from the 5hr window
    # Use the first message in the window — that's when the window started filling
    oldest_ts = conn.execute(
        "SELECT MIN(timestamp) FROM usage_log WHERE REPLACE(REPLACE(timestamp, 'T', ' '), 'Z', '') >= ?",
        (session_start_str,)
    ).fetchone()[0]

    s_reset_min = None
    if oldest_ts:
        try:
            oldest_dt = datetime.fromisoformat(oldest_ts.replace('Z', '+00:00'))
            # The oldest message will "fall off" the window at oldest + 5hr
            reset_at = oldest_dt + timedelta(hours=session_hours)
            diff = reset_at - now
            if diff.total_seconds() > 0:
                s_reset_min = int(diff.total_seconds() / 60)
            else:
                s_reset_min = 0
        except (ValueError, TypeError):
            pass

    # Per-agent today
    agents = conn.execute(
        "SELECT agent, total_cost, total_messages FROM daily_summary WHERE date = ? ORDER BY total_cost DESC",
        (today,)
    ).fetchall()

    conn.close()

    return {
        "today": round(float(today_total), 2),
        "month": round(float(month_total), 2),
        "plan": plan["name"],
        "weekly": {
            "used": round(w_total_cost, 2),
            "limit": weekly_cost_limit,
            "pct": min(w_all_pct, 100.0),
            "resets_in_minutes": w_reset_min,
            "models": w_models,
        },
        "session": {
            "used": round(s_total_cost, 2),
            "limit": session_cost_limit,
            "pct": min(s_all_pct, 100.0),
            "resets_in_minutes": s_reset_min,
            "models": s_models,
        },
        "agents": [{"agent": r[0], "cost": round(float(r[1]), 2), "messages": r[2]} for r in agents],
    }


@router.get("/models-timeline")
def spending_models_timeline(
    range: str = Query("week", pattern="^(week|month)$"),
    user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Per-model daily costs for chart rendering."""
    conn = _get_conn()
    if not conn:
        return _costs_models_timeline(user.get("workspace_id", 1), db, range)

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
    db: DBSession = Depends(get_db),
):
    """Timeline data for charts. day=hourly, week/month=daily. Optional agent filter."""
    conn = _get_conn()
    if not conn:
        return _costs_timeline(user.get("workspace_id", 1), db, range, agent)

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
def spending_sessions(
    user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Today's sessions grouped by agent + session_id, ordered by cost."""
    conn = _get_conn()
    if not conn:
        return _costs_sessions(user.get("workspace_id", 1), db)

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
