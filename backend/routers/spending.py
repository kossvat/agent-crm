"""Spending data endpoints — reads from spending.db (read-only)."""

import os
import sqlite3
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from backend.auth import get_current_user

router = APIRouter(prefix="/api/spending", tags=["spending"])

SPENDING_DB = os.path.expanduser("~/projects/spending-tracker/spending.db")


def _get_conn():
    if not os.path.exists(SPENDING_DB):
        return None
    return sqlite3.connect(SPENDING_DB)


@router.get("/current")
def spending_current(user: dict = Depends(get_current_user)):
    """Current spending: today, week, month totals + per-agent breakdown."""
    conn = _get_conn()
    if not conn:
        return {"today": 0, "week": 0, "month": 0, "budget": 200, "agents": []}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")

    today_total = conn.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM daily_summary WHERE date = ?", (today,)
    ).fetchone()[0]

    week_total = conn.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM daily_summary WHERE date >= ?", (week_ago,)
    ).fetchone()[0]

    month_total = conn.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM daily_summary WHERE date >= ?", (month_start,)
    ).fetchone()[0]

    agents = conn.execute(
        "SELECT agent, total_cost, total_messages FROM daily_summary WHERE date = ? ORDER BY total_cost DESC",
        (today,)
    ).fetchall()

    conn.close()
    return {
        "today": round(float(today_total), 2),
        "week": round(float(week_total), 2),
        "month": round(float(month_total), 2),
        "budget": 200.0,
        "agents": [{"agent": r[0], "cost": round(float(r[1]), 2), "messages": r[2]} for r in agents],
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
        # Hourly for last 24h
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        if agent:
            rows = conn.execute("""
                SELECT strftime('%H', timestamp) as hour, SUM(cost_total) as cost
                FROM usage_log
                WHERE timestamp > ? AND agent = ?
                GROUP BY hour
                ORDER BY hour
            """, (cutoff, agent)).fetchall()
        else:
            rows = conn.execute("""
                SELECT strftime('%H', timestamp) as hour, SUM(cost_total) as cost
                FROM usage_log
                WHERE timestamp > ?
                GROUP BY hour
                ORDER BY hour
            """, (cutoff,)).fetchall()
        labels = [f"{r[0]}:00" for r in rows]
        data = [round(float(r[1]), 3) for r in rows]
    else:
        # Daily
        days = 7 if range == "week" else 30
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        if agent:
            rows = conn.execute("""
                SELECT date, SUM(total_cost) as cost
                FROM daily_summary
                WHERE date >= ? AND agent = ?
                GROUP BY date
                ORDER BY date
            """, (cutoff, agent)).fetchall()
        else:
            rows = conn.execute("""
                SELECT date, SUM(total_cost) as cost
                FROM daily_summary
                WHERE date >= ?
                GROUP BY date
                ORDER BY date
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
        FROM usage_log
        WHERE timestamp > ?
        GROUP BY agent, session_id
        ORDER BY cost DESC
        LIMIT 20
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
        FROM alerts
        ORDER BY timestamp DESC
        LIMIT 50
    """).fetchall()
    conn.close()

    return [
        {"id": r[0], "timestamp": r[1], "type": r[2], "message": r[3], "resolved": bool(r[4])}
        for r in rows
    ]
