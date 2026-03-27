"""Watchdog — anomaly detection from spending.db.

Run via cron every 5 minutes:
  */5 * * * * cd ~/projects/agent-crm && python3 -m backend.services.watchdog >> /tmp/crm-watchdog.log 2>&1
"""

import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

from backend.config import BOT_TOKEN
from backend.database import SessionLocal
from backend.models import Alert, AlertType

log = logging.getLogger("agent-crm.watchdog")

SPENDING_DB = os.path.expanduser("~/projects/spending-tracker/spending.db")
COLLECT_SCRIPT = os.path.expanduser("~/projects/spending-tracker/collect.py")
TG_CHAT_ID = "1080204489"
ALERT_STATE_FILE = os.path.expanduser("~/projects/agent-crm/data/.watchdog_state.json")

# Thresholds (demo mode — notify only, don't stop anything)
BURST_10MIN = 2.0       # $ in 10 min
BURST_30MIN = 5.0       # $ in 30 min
DAILY_WARNING = 15.0    # $ per agent per day
DAILY_CRITICAL = 25.0   # $ per agent per day
MONTHLY_BUDGET = 200.0  # $ per month

# Cooldown: don't re-send the same alert type+agent within this window
ALERT_COOLDOWN = {
    "burst_10":   600,   # 10 min — bursts can change fast
    "burst_30":   1800,  # 30 min
    "daily":      3600,  # 1 hour — daily totals don't change fast
    "monthly":    3600,  # 1 hour
}


def _load_alert_state() -> dict:
    """Load last-sent timestamps per alert key."""
    try:
        if os.path.exists(ALERT_STATE_FILE):
            with open(ALERT_STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_alert_state(state: dict):
    """Persist alert state."""
    try:
        with open(ALERT_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        log.error(f"Failed to save alert state: {e}")


def _should_send(state: dict, key: str, category: str) -> bool:
    """Check if enough time passed since last alert for this key."""
    cooldown = ALERT_COOLDOWN.get(category, 3600)
    last_sent = state.get(key, 0)
    return (time.time() - last_sent) >= cooldown


def _mark_sent(state: dict, key: str):
    """Record that an alert was just sent."""
    state[key] = time.time()


def send_telegram(message: str):
    """Send alert to Telegram via bot."""
    if not BOT_TOKEN:
        log.warning("No BOT_TOKEN, skipping Telegram alert")
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TG_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
    except Exception as e:
        log.error(f"Telegram send failed: {e}")


def create_crm_alert(message: str, alert_type: str = "warning"):
    """Create alert in CRM database."""
    try:
        db = SessionLocal()
        alert = Alert(
            type=AlertType(alert_type),
            message=message,
        )
        db.add(alert)
        db.commit()
        db.close()
    except Exception as e:
        log.error(f"CRM alert creation failed: {e}")


def collect_fresh_data():
    """Run spending collector to get fresh data."""
    try:
        subprocess.run(
            [sys.executable, COLLECT_SCRIPT, "collect"],
            capture_output=True, timeout=30,
            cwd=os.path.dirname(COLLECT_SCRIPT),
        )
    except Exception as e:
        log.error(f"Collect failed: {e}")


def query_spending(minutes: int) -> list[dict]:
    """Query spending per agent for last N minutes."""
    if not os.path.exists(SPENDING_DB):
        return []

    conn = sqlite3.connect(SPENDING_DB)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()

    rows = conn.execute("""
        SELECT agent, SUM(cost_total) as cost, COUNT(*) as msgs,
               GROUP_CONCAT(DISTINCT session_id) as sessions
        FROM usage_log
        WHERE timestamp > ?
        GROUP BY agent
        HAVING cost > 0
        ORDER BY cost DESC
    """, (cutoff,)).fetchall()
    conn.close()

    return [{"agent": r[0], "cost": r[1], "msgs": r[2], "sessions": r[3]} for r in rows]


def query_daily_spending() -> list[dict]:
    """Query today's spending per agent."""
    if not os.path.exists(SPENDING_DB):
        return []

    conn = sqlite3.connect(SPENDING_DB)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT agent, total_cost
        FROM daily_summary
        WHERE date = ?
    """, (today,)).fetchall()
    conn.close()

    return [{"agent": r[0], "cost": r[1]} for r in rows]


def query_monthly_spending() -> float:
    """Query current month's total spending."""
    if not os.path.exists(SPENDING_DB):
        return 0.0

    conn = sqlite3.connect(SPENDING_DB)
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")

    row = conn.execute("""
        SELECT COALESCE(SUM(total_cost), 0)
        FROM daily_summary
        WHERE date >= ?
    """, (month_start,)).fetchone()
    conn.close()

    return float(row[0]) if row else 0.0


def query_7day_average(minutes: int) -> dict:
    """Query 7-day average spending per agent for comparison."""
    if not os.path.exists(SPENDING_DB):
        return {}

    conn = sqlite3.connect(SPENDING_DB)
    # Get average daily cost per agent for last 7 days
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT agent, AVG(total_cost) as avg_daily
        FROM daily_summary
        WHERE date >= ?
        GROUP BY agent
    """, (week_ago,)).fetchall()
    conn.close()

    # Scale to per-minute rate
    return {r[0]: r[1] / 1440.0 * minutes for r in rows}


def check_anomalies():
    """Main anomaly detection loop. Returns list of (type, msg, key, category)."""
    alerts = []

    # Burst detection: 10 min
    burst_10 = query_spending(10)
    avg_10 = query_7day_average(10)
    for entry in burst_10:
        agent, cost = entry["agent"], entry["cost"]
        avg = avg_10.get(agent, BURST_10MIN / 3)  # fallback
        if cost > BURST_10MIN or (avg > 0 and cost > avg * 3):
            session = entry["sessions"].split(",")[0] if entry["sessions"] else "?"
            msg = f"⚡ Burst: {agent} spent ${cost:.2f} in 10min (avg ${avg:.2f}). Session: {session[:16]}"
            alerts.append(("warning", msg, f"burst_10:{agent}", "burst_10"))

    # Burst detection: 30 min
    burst_30 = query_spending(30)
    for entry in burst_30:
        agent, cost = entry["agent"], entry["cost"]
        if cost > BURST_30MIN:
            session = entry["sessions"].split(",")[0] if entry["sessions"] else "?"
            msg = f"🔥 Burst: {agent} spent ${cost:.2f} in 30min. Session: {session[:16]}"
            alerts.append(("warning", msg, f"burst_30:{agent}", "burst_30"))

    # Daily limits
    daily = query_daily_spending()
    for entry in daily:
        agent, cost = entry["agent"], entry["cost"]
        if cost > DAILY_CRITICAL:
            msg = f"🚨 Daily critical: {agent} at ${cost:.2f} (limit ${DAILY_CRITICAL})"
            alerts.append(("error", msg, f"daily_crit:{agent}", "daily"))
        elif cost > DAILY_WARNING:
            msg = f"⚠️ Daily warning: {agent} at ${cost:.2f} (limit ${DAILY_WARNING})"
            alerts.append(("warning", msg, f"daily_warn:{agent}", "daily"))

    # Monthly budget
    monthly = query_monthly_spending()
    pct = monthly / MONTHLY_BUDGET * 100 if MONTHLY_BUDGET > 0 else 0
    if pct >= 90:
        msg = f"🔴 Monthly budget at {pct:.0f}%: ${monthly:.2f}/${MONTHLY_BUDGET}"
        alerts.append(("error", msg, "monthly_90", "monthly"))
    elif pct >= 80:
        msg = f"🟡 Monthly budget at {pct:.0f}%: ${monthly:.2f}/${MONTHLY_BUDGET}"
        alerts.append(("warning", msg, "monthly_80", "monthly"))

    return alerts


def run():
    """Main watchdog run."""
    log.info(f"Watchdog run at {datetime.now(timezone.utc).isoformat()}")

    # Step 1: collect fresh data
    collect_fresh_data()

    # Step 2: detect anomalies
    alerts = check_anomalies()

    if not alerts:
        log.info("No anomalies detected")
        return

    # Step 3: deduplicate and notify
    state = _load_alert_state()
    sent = 0
    skipped = 0

    for alert_type, msg, key, category in alerts:
        if _should_send(state, key, category):
            log.warning(msg)
            create_crm_alert(msg, alert_type)
            send_telegram(f"🤖 <b>CRM Alert</b>\n{msg}")
            _mark_sent(state, key)
            sent += 1
        else:
            skipped += 1
            log.info(f"Cooldown skip: {key}")

    _save_alert_state(state)
    log.info(f"Sent {sent} alerts, skipped {skipped} (cooldown)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run()
