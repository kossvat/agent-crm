"""Watchdog — anomaly detection from spending.db.

Run via cron every 5 minutes:
  */5 * * * * cd /path/to/agent-crm && python3 -m backend.services.watchdog >> /tmp/crm-watchdog.log 2>&1
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

SPENDING_DB = os.getenv("SPENDING_DB", os.path.expanduser("~/spending-tracker/spending.db"))
COLLECT_SCRIPT = os.getenv("COLLECT_SCRIPT", os.path.expanduser("~/spending-tracker/collect.py"))
TG_CHAT_ID = os.getenv("OWNER_TELEGRAM_ID", "")
ALERT_STATE_FILE = os.getenv("ALERT_STATE_FILE", os.path.expanduser("~/agent-crm/data/.watchdog_state.json"))

# Thresholds
BURST_10MIN = 8.0       # $ in 10 min — Opus sessions easily hit $2-5
BURST_30MIN = 20.0      # $ in 30 min
DAILY_WARNING = 30.0    # $ per agent per day
DAILY_CRITICAL = 50.0   # $ per agent per day
MONTHLY_BUDGET = 200.0  # $ per month

# Cooldowns — no spam
ALERT_COOLDOWN = {
    "burst_10":   7200,   # 2 hours
    "burst_30":   7200,   # 2 hours
    "daily":      21600,  # 6 hours
    "monthly":    14400,  # 4 hours
}


def _load_alert_state() -> dict:
    try:
        if os.path.exists(ALERT_STATE_FILE):
            with open(ALERT_STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_alert_state(state: dict):
    try:
        os.makedirs(os.path.dirname(ALERT_STATE_FILE), exist_ok=True)
        with open(ALERT_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        log.error(f"Failed to save alert state: {e}")


def _should_send(state: dict, key: str, category: str) -> bool:
    cooldown = ALERT_COOLDOWN.get(category, 7200)
    last_sent = state.get(key, 0)
    return (time.time() - last_sent) >= cooldown


def _mark_sent(state: dict, key: str):
    state[key] = time.time()


def send_telegram(message: str):
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
    try:
        subprocess.run(
            [sys.executable, COLLECT_SCRIPT, "collect"],
            capture_output=True, timeout=30,
            cwd=os.path.dirname(COLLECT_SCRIPT),
        )
    except Exception as e:
        log.error(f"Collect failed: {e}")


def query_spending(minutes: int) -> list[dict]:
    if not os.path.exists(SPENDING_DB):
        return []
    conn = sqlite3.connect(SPENDING_DB)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    rows = conn.execute("""
        SELECT agent, SUM(cost_total) as cost, COUNT(*) as msgs
        FROM usage_log
        WHERE timestamp > ?
        GROUP BY agent
        HAVING cost > 0
        ORDER BY cost DESC
    """, (cutoff,)).fetchall()
    conn.close()
    return [{"agent": r[0], "cost": r[1], "msgs": r[2]} for r in rows]


def query_daily_spending() -> list[dict]:
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


def check_anomalies():
    """Detect anomalies. Returns list of (type, msg, key, category)."""
    alerts = []

    # Burst: 10 min
    for entry in query_spending(10):
        agent, cost = entry["agent"], entry["cost"]
        if cost > BURST_10MIN:
            alerts.append((
                "warning",
                f"⚡ {agent}: ${cost:.2f} in 10min",
                f"burst_10:{agent}", "burst_10"
            ))

    # Burst: 30 min
    for entry in query_spending(30):
        agent, cost = entry["agent"], entry["cost"]
        if cost > BURST_30MIN:
            alerts.append((
                "warning",
                f"🔥 {agent}: ${cost:.2f} in 30min",
                f"burst_30:{agent}", "burst_30"
            ))

    # Daily limits
    for entry in query_daily_spending():
        agent, cost = entry["agent"], entry["cost"]
        if cost > DAILY_CRITICAL:
            alerts.append((
                "error",
                f"🚨 {agent}: ${cost:.2f} today (critical)",
                f"daily_crit:{agent}", "daily"
            ))
        elif cost > DAILY_WARNING:
            alerts.append((
                "warning",
                f"⚠️ {agent}: ${cost:.2f} today",
                f"daily_warn:{agent}", "daily"
            ))

    # Monthly budget
    monthly = query_monthly_spending()
    pct = monthly / MONTHLY_BUDGET * 100 if MONTHLY_BUDGET > 0 else 0
    if pct >= 90:
        alerts.append((
            "error",
            f"🔴 Monthly: ${monthly:.0f}/${MONTHLY_BUDGET:.0f} ({pct:.0f}%)",
            "monthly_90", "monthly"
        ))
    elif pct >= 80:
        alerts.append((
            "warning",
            f"🟡 Monthly: ${monthly:.0f}/${MONTHLY_BUDGET:.0f} ({pct:.0f}%)",
            "monthly_80", "monthly"
        ))

    return alerts


def run():
    """Main watchdog run — collect, detect, send grouped alert."""
    log.info(f"Watchdog run at {datetime.now(timezone.utc).isoformat()}")

    collect_fresh_data()
    alerts = check_anomalies()

    if not alerts:
        log.info("No anomalies detected")
        return

    # Filter by cooldown
    state = _load_alert_state()
    actionable = []
    skipped = 0

    for alert_type, msg, key, category in alerts:
        if _should_send(state, key, category):
            actionable.append((alert_type, msg, key))
        else:
            skipped += 1
            log.info(f"Cooldown skip: {key}")

    if not actionable:
        log.info(f"All {skipped} alerts on cooldown")
        return

    # Group into single CRM alert + single Telegram message
    worst_type = "error" if any(t == "error" for t, _, _ in actionable) else "warning"
    lines = [msg for _, msg, _ in actionable]
    grouped_msg = "\n".join(lines)

    # CRM: one alert with all lines
    create_crm_alert(grouped_msg, worst_type)

    # Telegram: one message
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    tg_msg = f"🤖 <b>CRM Alert</b> ({now})\n\n" + "\n".join(lines)
    send_telegram(tg_msg)

    # Mark all as sent
    for _, _, key in actionable:
        _mark_sent(state, key)
    _save_alert_state(state)

    log.info(f"Sent 1 grouped alert ({len(actionable)} items), skipped {skipped}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run()
