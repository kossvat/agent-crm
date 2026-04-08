"""Sync service — pulls data from OpenClaw into the CRM database."""

import logging
import os
import sqlite3
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession

from backend.models import Agent, Cost, Cron, AgentStatus, CronStatus
from backend.services.openclaw import get_agent_configs, get_crontab_entries, get_sessions

log = logging.getLogger("agent-crm.sync")

SPENDING_DB = os.path.expanduser("~/projects/spending-tracker/spending.db")

# Default workspace_id for sync operations (the local instance)
DEFAULT_WORKSPACE_ID = 1

# Map spending.db agent names to CRM names
SPENDING_NAME_MAP = {
    "main": "Caramel",
    "sixteen": "Sixteen",
    "career": "Rex",
    "social": "Vibe",
    "vibe": "Vibe",
}


def sync_agents(db: DBSession, workspace_id: int = DEFAULT_WORKSPACE_ID) -> int:
    """Sync agents from OpenClaw config into DB. Returns count of new agents."""
    configs = get_agent_configs()
    created = 0

    for cfg in configs:
        existing = db.query(Agent).filter(Agent.name == cfg["name"]).first()
        if existing:
            if cfg.get("emoji") and cfg["emoji"] != existing.emoji:
                existing.emoji = cfg["emoji"]
            if cfg.get("role") and cfg["role"] != existing.role:
                existing.role = cfg["role"]
            if cfg.get("bio") and cfg["bio"] != existing.bio:
                existing.bio = cfg["bio"]
            # Ensure workspace_id is set
            if not existing.workspace_id:
                existing.workspace_id = workspace_id
            continue

        agent = Agent(
            name=cfg["name"],
            emoji=cfg.get("emoji", "🤖"),
            model=cfg.get("model", ""),
            role=cfg.get("role", ""),
            bio=cfg.get("bio", ""),
            session_key=cfg.get("session_key", ""),
            status=AgentStatus.idle,
            workspace_id=workspace_id,
        )
        db.add(agent)
        created += 1
        log.info(f"Created agent: {cfg['name']}")

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        log.error(f"sync_agents commit failed: {e}")
    return created


def sync_sessions(db: DBSession):
    """Update agent last_active and model from session files."""
    sessions = get_sessions()

    for sess in sessions:
        name = sess.get("name", "")
        agent = db.query(Agent).filter(Agent.name == name).first()
        if agent:
            ts = sess.get("last_active_ts", 0)
            if ts > 0:
                last_active = datetime.fromtimestamp(ts, tz=timezone.utc)
                agent.last_active = last_active
                if (datetime.now(timezone.utc) - last_active).total_seconds() < 600:
                    agent.status = AgentStatus.active
                else:
                    agent.status = AgentStatus.idle

            model = sess.get("model", "")
            if model:
                agent.model = model

    db.commit()


def sync_crons(db: DBSession, workspace_id: int = DEFAULT_WORKSPACE_ID) -> int:
    """Sync crontab entries into DB. Returns count of new crons."""
    entries = get_crontab_entries()
    created = 0

    for entry in entries:
        existing = db.query(Cron).filter(Cron.command == entry.get("command", "")).first()
        if existing:
            if not existing.workspace_id:
                existing.workspace_id = workspace_id
            continue

        cron = Cron(
            name=entry.get("command", "")[:100],
            schedule=entry.get("schedule", ""),
            command=entry.get("command", ""),
            status=CronStatus.active,
            workspace_id=workspace_id,
        )
        db.add(cron)
        created += 1

    db.commit()
    return created


def sync_daily_costs(db: DBSession):
    """Update agent daily_cost from spending.db."""
    if not os.path.exists(SPENDING_DB):
        return

    try:
        conn = sqlite3.connect(SPENDING_DB)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT agent, total_cost FROM daily_summary WHERE date = ?", (today,)
        ).fetchall()
        conn.close()

        for agent_key, cost in rows:
            crm_name = SPENDING_NAME_MAP.get(agent_key)
            if crm_name:
                agent = db.query(Agent).filter(Agent.name == crm_name).first()
                if agent:
                    agent.daily_cost = round(float(cost), 2)

        db.commit()
    except Exception as e:
        log.error(f"sync_daily_costs failed: {e}")


def sync_costs_history(db: DBSession, workspace_id: int = DEFAULT_WORKSPACE_ID) -> int:
    """Sync historical cost data from spending.db → crm costs table."""
    if not os.path.exists(SPENDING_DB):
        return 0

    try:
        conn = sqlite3.connect(SPENDING_DB)
        rows = conn.execute("""
            SELECT date, agent, total_input_tokens, total_output_tokens, total_cost
            FROM daily_summary
            ORDER BY date DESC
        """).fetchall()
        conn.close()
    except Exception as e:
        log.error(f"sync_costs_history read failed: {e}")
        return 0

    agents = {a.session_key: a.id for a in db.query(Agent).all() if a.session_key}
    for spending_key, crm_name in SPENDING_NAME_MAP.items():
        agent = db.query(Agent).filter(Agent.name == crm_name).first()
        if agent and spending_key not in agents:
            agents[spending_key] = agent.id

    existing = set()
    for cost in db.query(Cost.agent_id, Cost.date).all():
        existing.add((cost.agent_id, str(cost.date)))

    inserted = 0
    for date_str, agent_key, input_tok, output_tok, cost_usd in rows:
        agent_id = agents.get(agent_key)
        if not agent_id:
            continue
        if (agent_id, date_str) in existing:
            db.query(Cost).filter(
                Cost.agent_id == agent_id,
                Cost.date == date_str,
            ).update({
                Cost.input_tokens: int(input_tok or 0),
                Cost.output_tokens: int(output_tok or 0),
                Cost.cost_usd: round(float(cost_usd or 0), 6),
            })
            continue

        cost = Cost(
            agent_id=agent_id,
            date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            input_tokens=int(input_tok or 0),
            output_tokens=int(output_tok or 0),
            cost_usd=round(float(cost_usd or 0), 6),
            model="",
            workspace_id=workspace_id,
        )
        db.add(cost)
        existing.add((agent_id, date_str))
        inserted += 1

    try:
        db.commit()
        log.info(f"sync_costs_history: {inserted} new rows")
    except Exception as e:
        db.rollback()
        log.error(f"sync_costs_history commit failed: {e}")
    return inserted


def full_sync(db: DBSession, workspace_id: int = DEFAULT_WORKSPACE_ID) -> dict:
    """Run all sync operations. Returns summary."""
    log.info("Starting full sync...")

    new_agents = sync_agents(db, workspace_id)
    sync_sessions(db)
    new_crons = sync_crons(db, workspace_id)
    sync_daily_costs(db)
    new_costs = sync_costs_history(db, workspace_id)

    summary = {
        "new_agents": new_agents,
        "new_crons": new_crons,
        "new_cost_rows": new_costs,
        "status": "ok",
    }
    log.info(f"Sync complete: {summary}")
    return summary
