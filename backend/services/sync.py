"""Sync service — pulls data from OpenClaw into the CRM database."""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models import Agent, Cron, AgentStatus, CronStatus
from backend.services.openclaw import get_agent_configs, get_crontab_entries, get_sessions

log = logging.getLogger("agent-crm.sync")


def sync_agents(db: Session) -> int:
    """Sync agents from OpenClaw config into DB. Returns count of new agents."""
    configs = get_agent_configs()
    created = 0

    for cfg in configs:
        existing = db.query(Agent).filter(Agent.name == cfg["name"]).first()
        if existing:
            # Update emoji if changed
            if cfg.get("emoji") and cfg["emoji"] != existing.emoji:
                existing.emoji = cfg["emoji"]
            continue

        agent = Agent(
            name=cfg["name"],
            emoji=cfg.get("emoji", "🤖"),
            model=cfg.get("model", ""),
            session_key=cfg.get("session_key", ""),
            status=AgentStatus.idle,
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


def sync_sessions(db: Session):
    """Update agent status and last_active from OpenClaw sessions."""
    sessions = get_sessions()

    for sess in sessions:
        key = sess.get("key", "")
        # Extract agent name from session key like "agent:sixteen:telegram:..."
        parts = key.split(":")
        if len(parts) >= 2 and parts[0] == "agent":
            agent_name = parts[1]
            # Map "main" to "caramel" (default agent)
            if agent_name == "main":
                agent_name = "caramel"

            agent = db.query(Agent).filter(Agent.name == agent_name).first()
            if agent:
                agent.status = AgentStatus.active
                agent.last_active = datetime.now(timezone.utc)

                # Update model if available
                model = sess.get("model", "")
                if model:
                    agent.model = model

    db.commit()


def sync_crons(db: Session) -> int:
    """Sync crontab entries into DB. Returns count of new crons."""
    entries = get_crontab_entries()
    created = 0

    for entry in entries:
        # Check if already tracked
        existing = db.query(Cron).filter(Cron.command == entry.get("command", "")).first()
        if existing:
            continue

        cron = Cron(
            name=entry.get("command", "")[:100],
            schedule=entry.get("schedule", ""),
            command=entry.get("command", ""),
            status=CronStatus.active,
        )
        db.add(cron)
        created += 1

    db.commit()
    return created


def full_sync(db: Session) -> dict:
    """Run all sync operations. Returns summary."""
    log.info("Starting full sync...")

    new_agents = sync_agents(db)
    sync_sessions(db)
    new_crons = sync_crons(db)

    summary = {
        "new_agents": new_agents,
        "new_crons": new_crons,
        "status": "ok",
    }
    log.info(f"Sync complete: {summary}")
    return summary
