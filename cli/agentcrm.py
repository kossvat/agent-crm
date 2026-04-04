#!/usr/bin/env python3
"""agentcrm — universal CLI for AI Agent CRM.

Works with any agent framework (OpenClaw, Hermes, custom).
Syncs agents, files, and costs to myaiagentscrm.com.

Usage:
    agentcrm login           — authenticate with API key
    agentcrm status          — check connection & workspace info
    agentcrm agents sync     — sync agents from local config
    agentcrm agents list     — list agents in CRM
    agentcrm files sync      — sync agent files (SOUL.md, etc.)
    agentcrm costs push      — push spending data
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: 'requests' package required. Install: pip install requests")
    sys.exit(1)

CONFIG_DIR = Path.home() / ".agentcrm"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_URL = "https://myaiagentscrm.com"


# --- Config ---

def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    CONFIG_FILE.chmod(0o600)


def get_api_key() -> str:
    cfg = load_config()
    key = os.environ.get("AGENTCRM_API_KEY") or cfg.get("api_key")
    if not key:
        print("Error: No API key. Run 'agentcrm login' first or set AGENTCRM_API_KEY.")
        sys.exit(1)
    return key


def get_base_url() -> str:
    cfg = load_config()
    return os.environ.get("AGENTCRM_URL") or cfg.get("url", DEFAULT_URL)


def api(method: str, path: str, **kwargs) -> requests.Response:
    """Make an authenticated API request."""
    url = f"{get_base_url()}{path}"
    headers = {"X-Api-Key": get_api_key()}
    headers.update(kwargs.pop("headers", {}))
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    return resp


def die(resp: requests.Response):
    """Print error and exit."""
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    print(f"Error ({resp.status_code}): {detail}")
    sys.exit(1)


# --- Commands ---

def cmd_login(args):
    """Interactive login — save API key."""
    url = input(f"CRM URL [{DEFAULT_URL}]: ").strip() or DEFAULT_URL
    api_key = input("API key: ").strip()
    if not api_key:
        print("Error: API key required. Generate one in CRM → Settings.")
        sys.exit(1)

    # Test connection
    print("Testing connection...")
    headers = {"X-Api-Key": api_key}
    try:
        resp = requests.get(f"{url}/api/auth/me", headers=headers, timeout=10)
    except requests.ConnectionError:
        print(f"Error: Cannot connect to {url}")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"Error: Authentication failed ({resp.status_code})")
        sys.exit(1)

    data = resp.json()
    ws = data.get("workspace", {})
    print(f"✅ Connected to workspace: {ws.get('name', '?')} (tier: {ws.get('tier', '?')})")

    save_config({"url": url, "api_key": api_key})
    print(f"Config saved to {CONFIG_FILE}")


def cmd_status(args):
    """Check connection and workspace info."""
    resp = api("GET", "/api/auth/me")
    if resp.status_code != 200:
        die(resp)
    data = resp.json()
    user = data.get("user", {})
    ws = data.get("workspace", {})
    print(f"User:      {user.get('name', '?')}")
    print(f"Workspace: {ws.get('name', '?')} (id={ws.get('id')})")
    print(f"Tier:      {ws.get('tier', '?')}")
    print(f"Agents:    {ws.get('agent_limit', '?')} max")

    # Count agents
    resp2 = api("GET", "/api/agents")
    if resp2.status_code == 200:
        agents = resp2.json()
        if isinstance(agents, list):
            print(f"Current:   {len(agents)} agents")


def cmd_agents_list(args):
    """List agents in CRM."""
    resp = api("GET", "/api/agents")
    if resp.status_code != 200:
        die(resp)
    agents = resp.json()
    if not agents:
        print("No agents found. Run 'agentcrm agents sync' to add some.")
        return
    print(f"{'Name':<15} {'Role':<20} {'Model':<30} {'Status'}")
    print("-" * 75)
    for a in agents:
        print(f"{a.get('emoji','')} {a['name']:<13} {a.get('role',''):<20} {a.get('model',''):<30} {a.get('status','')}")


def cmd_agents_sync(args):
    """Sync agents from a local config file."""
    config_path = Path(args.config) if args.config else _find_agents_config()
    if not config_path or not config_path.exists():
        print("Error: No agents config found.")
        print("Provide --config path/to/agents.json or create ~/.agentcrm/agents.json")
        print("\nExample agents.json:")
        print(json.dumps([
            {"name": "MyAgent", "emoji": "🤖", "role": "Assistant", "model": "gpt-4o"},
        ], indent=2))
        sys.exit(1)

    agents = json.loads(config_path.read_text())
    if not isinstance(agents, list):
        print("Error: agents config must be a JSON array of agent objects.")
        sys.exit(1)

    print(f"Syncing {len(agents)} agents from {config_path}...")
    created = 0
    updated = 0

    for agent in agents:
        name = agent.get("name")
        if not name:
            continue

        # Try to find existing
        resp = api("GET", "/api/agents")
        if resp.status_code != 200:
            die(resp)
        existing = [a for a in resp.json() if a["name"] == name]

        if existing:
            # Update
            agent_id = existing[0]["id"]
            payload = {}
            for key in ("emoji", "role", "model", "bio", "session_key"):
                if key in agent:
                    payload[key] = agent[key]
            if payload:
                resp = api("PATCH", f"/api/agents/{agent_id}", json=payload)
                if resp.status_code == 200:
                    updated += 1
                    print(f"  ✏️  Updated: {name}")
                else:
                    print(f"  ❌ Failed to update {name}: {resp.status_code}")
        else:
            # Create
            resp = api("POST", "/api/agents", json=agent)
            if resp.status_code in (200, 201):
                created += 1
                print(f"  ✅ Created: {name}")
            else:
                print(f"  ❌ Failed to create {name}: {resp.status_code}")

    print(f"\nDone: {created} created, {updated} updated.")


def cmd_files_sync(args):
    """Sync agent files (SOUL.md, IDENTITY.md, MEMORY.md)."""
    files_dir = Path(args.dir) if args.dir else _find_files_dir()
    if not files_dir:
        print("Error: No files directory found.")
        print("Provide --dir or organize files as: dir/AgentName/SOUL.md")
        sys.exit(1)

    viewable = {"SOUL.md", "IDENTITY.md", "MEMORY.md"}
    items = []

    # Scan directory: expect dir/<AgentName>/<filename>
    for agent_dir in sorted(files_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_name = agent_dir.name
        for f in sorted(agent_dir.iterdir()):
            if f.name in viewable and f.is_file():
                content = f.read_text(encoding="utf-8", errors="replace")
                items.append({
                    "agent_name": agent_name,
                    "filename": f.name,
                    "content": content,
                })

    # Also support flat structure: dir/SOUL.md with agent name from config
    if not items and args.agent:
        for f in sorted(files_dir.iterdir()):
            if f.name in viewable and f.is_file():
                content = f.read_text(encoding="utf-8", errors="replace")
                items.append({
                    "agent_name": args.agent,
                    "filename": f.name,
                    "content": content,
                })

    if not items:
        print("No files found to sync.")
        print("Expected structure: <dir>/<AgentName>/SOUL.md")
        sys.exit(1)

    print(f"Syncing {len(items)} files...")
    resp = api("POST", "/api/files/sync", json={"files": items})
    if resp.status_code != 200:
        die(resp)

    result = resp.json()
    print(f"✅ Synced: {result.get('synced', 0)} files")
    if result.get("created_agents"):
        print(f"   Created agents: {', '.join(result['created_agents'])}")


def cmd_costs_push(args):
    """Push cost/spending data."""
    data_path = Path(args.file) if args.file else None
    if not data_path or not data_path.exists():
        print("Error: Provide --file with cost data JSON.")
        print("\nExample costs.json:")
        print(json.dumps([{
            "agent_name": "MyAgent",
            "date": "2026-04-04",
            "input_tokens": 50000,
            "output_tokens": 10000,
            "cost_usd": 0.50,
            "model": "gpt-4o",
        }], indent=2))
        sys.exit(1)

    costs = json.loads(data_path.read_text())
    if not isinstance(costs, list):
        costs = [costs]

    print(f"Pushing {len(costs)} cost records...")
    resp = api("POST", "/api/costs/ingest", json={"records": costs})
    if resp.status_code != 200:
        die(resp)
    result = resp.json()
    print(f"✅ Ingested: {result.get('ingested', result)}")


# --- Task commands ---

def cmd_task_create(args):
    """Create a task."""
    payload = {
        "title": args.title,
        "description": args.description or "",
        "priority": args.priority or "medium",
        "status": "todo",
    }
    # Resolve agent name → id
    if args.agent:
        agent_id = _resolve_agent_id(args.agent)
        if agent_id:
            payload["agent_id"] = agent_id

    resp = api("POST", "/api/tasks", json=payload)
    if resp.status_code not in (200, 201):
        die(resp)
    task = resp.json()
    print(f"✅ Task #{task['id']} created: {task['title']}")


def cmd_task_list(args):
    """List tasks."""
    resp = api("GET", "/api/tasks")
    if resp.status_code != 200:
        die(resp)
    tasks = resp.json()
    if not tasks:
        print("No tasks.")
        return
    print(f"{'#':<5} {'Status':<12} {'Priority':<8} {'Title':<40} {'Agent'}")
    print("-" * 80)
    for t in tasks:
        agent_name = t.get("agent", {}).get("name", "") if t.get("agent") else ""
        print(f"{t['id']:<5} {t['status']:<12} {t.get('priority',''):<8} {t['title'][:40]:<40} {agent_name}")


def cmd_task_update(args):
    """Update task status."""
    payload = {}
    if args.status:
        payload["status"] = args.status
    if args.title:
        payload["title"] = args.title
    if not payload:
        print("Nothing to update. Use --status or --title.")
        return
    resp = api("PATCH", f"/api/tasks/{args.id}", json=payload)
    if resp.status_code != 200:
        die(resp)
    print(f"✅ Task #{args.id} updated.")


# --- Journal commands ---

def cmd_journal_add(args):
    """Add a journal entry."""
    from datetime import date as _date
    payload = {
        "date": args.date or _date.today().isoformat(),
        "content": args.content,
        "source": "cli",
    }
    if args.agent:
        agent_id = _resolve_agent_id(args.agent)
        if agent_id:
            payload["agent_id"] = agent_id

    resp = api("POST", "/api/journal", json=payload)
    if resp.status_code not in (200, 201):
        die(resp)
    entry = resp.json()
    print(f"✅ Journal entry #{entry.get('id', '?')} added for {payload['date']}")


# --- Alert commands ---

def cmd_alert_send(args):
    """Send an alert."""
    payload = {
        "message": args.message,
        "type": args.type or "info",
    }
    if args.agent:
        agent_id = _resolve_agent_id(args.agent)
        if agent_id:
            payload["agent_id"] = agent_id

    resp = api("POST", "/api/alerts", json=payload)
    if resp.status_code not in (200, 201):
        die(resp)
    print(f"✅ Alert sent: [{payload['type']}] {args.message}")


# --- Helpers ---

def _resolve_agent_id(name: str) -> Optional[int]:
    """Look up agent by name, return ID."""
    resp = api("GET", "/api/agents")
    if resp.status_code != 200:
        return None
    agents = resp.json()
    for a in agents:
        if a["name"].lower() == name.lower():
            return a["id"]
    print(f"Warning: Agent '{name}' not found.")
    return None


def _find_agents_config() -> Optional[Path]:
    """Try common locations for agents config."""
    candidates = [
        CONFIG_DIR / "agents.json",
        Path.cwd() / "agents.json",
        Path.cwd() / ".agentcrm" / "agents.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _find_files_dir() -> Optional[Path]:
    """Try common locations for agent files."""
    candidates = [
        CONFIG_DIR / "files",
        Path.cwd() / "agent-files",
        Path.cwd() / ".agentcrm" / "files",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        prog="agentcrm",
        description="Universal CLI for AI Agent CRM — works with any agent framework.",
    )
    sub = parser.add_subparsers(dest="command")

    # login
    sub.add_parser("login", help="Authenticate with API key")

    # status
    sub.add_parser("status", help="Check connection & workspace info")

    # agents
    agents_parser = sub.add_parser("agents", help="Manage agents")
    agents_sub = agents_parser.add_subparsers(dest="agents_command")
    agents_sub.add_parser("list", help="List agents")
    sync_parser = agents_sub.add_parser("sync", help="Sync agents from config file")
    sync_parser.add_argument("--config", "-c", help="Path to agents.json")

    # files
    files_parser = sub.add_parser("files", help="Manage agent files")
    files_sub = files_parser.add_subparsers(dest="files_command")
    files_sync = files_sub.add_parser("sync", help="Sync agent files")
    files_sync.add_argument("--dir", "-d", help="Directory containing agent files")
    files_sync.add_argument("--agent", "-a", help="Agent name (for flat directory structure)")

    # costs
    costs_parser = sub.add_parser("costs", help="Push spending data")
    costs_sub = costs_parser.add_subparsers(dest="costs_command")
    costs_push = costs_sub.add_parser("push", help="Push cost records")
    costs_push.add_argument("--file", "-f", help="Path to costs.json")

    # task
    task_parser = sub.add_parser("task", help="Manage tasks")
    task_sub = task_parser.add_subparsers(dest="task_command")
    task_sub.add_parser("list", help="List tasks")
    task_create = task_sub.add_parser("create", help="Create a task")
    task_create.add_argument("title", help="Task title")
    task_create.add_argument("--description", "-d", default="", help="Task description")
    task_create.add_argument("--agent", "-a", help="Assign to agent (by name)")
    task_create.add_argument("--priority", "-p", choices=["low", "medium", "high"], default="medium")
    task_update = task_sub.add_parser("update", help="Update a task")
    task_update.add_argument("id", type=int, help="Task ID")
    task_update.add_argument("--status", "-s", choices=["todo", "in_progress", "done"])
    task_update.add_argument("--title", "-t")

    # journal
    journal_parser = sub.add_parser("journal", help="Journal entries")
    journal_sub = journal_parser.add_subparsers(dest="journal_command")
    journal_add = journal_sub.add_parser("add", help="Add journal entry")
    journal_add.add_argument("content", help="Entry content")
    journal_add.add_argument("--agent", "-a", help="Agent name")
    journal_add.add_argument("--date", help="Date (YYYY-MM-DD, default: today)")

    # alert
    alert_parser = sub.add_parser("alert", help="Send alerts")
    alert_sub = alert_parser.add_subparsers(dest="alert_command")
    alert_send = alert_sub.add_parser("send", help="Send an alert")
    alert_send.add_argument("message", help="Alert message")
    alert_send.add_argument("--type", "-t", choices=["info", "warning", "error"], default="info")
    alert_send.add_argument("--agent", "-a", help="Agent name")

    args = parser.parse_args()

    if args.command == "login":
        cmd_login(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "agents":
        if args.agents_command == "list":
            cmd_agents_list(args)
        elif args.agents_command == "sync":
            cmd_agents_sync(args)
        else:
            agents_parser.print_help()
    elif args.command == "files":
        if args.files_command == "sync":
            cmd_files_sync(args)
        else:
            files_parser.print_help()
    elif args.command == "costs":
        if args.costs_command == "push":
            cmd_costs_push(args)
        else:
            costs_parser.print_help()
    elif args.command == "task":
        if args.task_command == "create":
            cmd_task_create(args)
        elif args.task_command == "list":
            cmd_task_list(args)
        elif args.task_command == "update":
            cmd_task_update(args)
        else:
            task_parser.print_help()
    elif args.command == "journal":
        if args.journal_command == "add":
            cmd_journal_add(args)
        else:
            journal_parser.print_help()
    elif args.command == "alert":
        if args.alert_command == "send":
            cmd_alert_send(args)
        else:
            alert_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
