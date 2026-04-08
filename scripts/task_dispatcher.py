#!/usr/bin/env python3
"""
Task Dispatcher — проверяет CRM задачи in_progress и отправляет агентам.
Запускается через Overnight Employee cron или вручную.

Логика:
1. Берёт все задачи со статусом in_progress
2. Если задача назначена агенту и ещё не была отправлена (нет метки dispatched)
3. Формирует сообщение и выводит для отправки
"""

import os
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("CRM_DB_PATH", str(Path.home() / "projects/agent-crm/data/crm.db")))
DISPATCH_LOG = Path(os.getenv("DISPATCH_LOG_PATH", str(Path.home() / "projects/agent-crm/data/dispatched.json")))

OWNER_TG_ID = os.getenv("OWNER_TELEGRAM_ID", "0")

# Agent ID → session key mapping (customize for your agents)
# Format: agent_id: "agent:<session_name>:telegram:direct:<telegram_id>"
AGENT_SESSIONS = {}  # e.g. {1: f"agent:main:telegram:direct:{OWNER_TG_ID}"}

AGENT_NAMES = {}  # Populate from DB or config


def load_dispatched():
    if DISPATCH_LOG.exists():
        return json.loads(DISPATCH_LOG.read_text())
    return {}


def save_dispatched(data):
    DISPATCH_LOG.write_text(json.dumps(data, indent=2))


def get_in_progress_tasks():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("""
        SELECT t.id, t.title, t.description, t.priority, t.category, t.agent_id, a.name as agent_name
        FROM tasks t
        LEFT JOIN agents a ON t.agent_id = a.id
        WHERE t.status = 'in_progress' AND t.agent_id IS NOT NULL
        ORDER BY t.priority DESC
    """)
    tasks = [dict(r) for r in cur.fetchall()]
    conn.close()
    return tasks


def main():
    dispatched = load_dispatched()
    tasks = get_in_progress_tasks()
    
    to_dispatch = []
    for task in tasks:
        task_key = str(task["id"])
        if task_key not in dispatched:
            to_dispatch.append(task)
    
    if not to_dispatch:
        print("NO_NEW_TASKS")
        return
    
    # Output tasks to dispatch as JSON
    results = []
    for task in to_dispatch:
        agent_id = task["agent_id"]
        session_key = AGENT_SESSIONS.get(agent_id)
        agent_name = AGENT_NAMES.get(agent_id, f"Agent#{agent_id}")
        
        if not session_key:
            continue
        
        message = f"""CRM Task (auto-dispatched):

**{task['title']}**
Priority: {task['priority']}
Category: {task['category'] or 'uncategorized'}

{task['description'] or 'No description.'}

When done, update the task status in CRM to done."""
        
        results.append({
            "task_id": task["id"],
            "agent_name": agent_name,
            "session_key": session_key,
            "message": message,
        })
        
        # Mark as dispatched
        dispatched[str(task["id"])] = {
            "agent": agent_name,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
        }
    
    save_dispatched(dispatched)
    
    # Output results
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
