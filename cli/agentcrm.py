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


# --- Real pricing for recalculation ---
# OpenClaw reports Vercel AI Gateway prices (~3x lower than actual Anthropic billing).
# We recalculate from raw token counts.

_MODEL_PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-haiku-3-5": {"input": 0.8, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
    "gpt-4o": {"input": 2.5, "output": 10.0, "cache_read": 1.25, "cache_write": 2.5},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6, "cache_read": 0.075, "cache_write": 0.15},
}

# Default model per OpenClaw agent (when JSONL says "delivery-mirror")
_AGENT_MODEL_DEFAULTS = {
    "main": "claude-sonnet-4-6",
    "sixteen": "claude-opus-4-6",
    "social": "claude-sonnet-4-6",
    "career": "claude-sonnet-4-6",
    "vibe": "claude-sonnet-4-6",
    "mira": "claude-sonnet-4-6",
    "luna": "claude-sonnet-4-6",
    "rex": "claude-sonnet-4-6",
}

# OpenClaw agent dir name → CRM display name mapping
# Override for agents whose directory name doesn't match their CRM name
_AGENT_NAME_MAP = {
    "main": "Caramel",
    "social": "Vibe",
    "career": "Rex",
}


def _recalc_cost(input_t, output_t, cache_read, cache_write, model, agent=""):
    """Recalculate cost from raw tokens using real Anthropic pricing."""
    resolved = model
    if not resolved or resolved in ("delivery-mirror", "unknown", ""):
        resolved = _AGENT_MODEL_DEFAULTS.get(agent, "claude-sonnet-4-6")
    # Strip provider prefix (e.g. "anthropic/claude-opus-4-6" → "claude-opus-4-6")
    if "/" in resolved:
        resolved = resolved.split("/", 1)[1]
    pricing = _MODEL_PRICING.get(resolved, _MODEL_PRICING.get("claude-sonnet-4-6"))
    return (
        (input_t or 0) * pricing["input"] / 1_000_000
        + (output_t or 0) * pricing["output"] / 1_000_000
        + (cache_read or 0) * pricing["cache_read"] / 1_000_000
        + (cache_write or 0) * pricing["cache_write"] / 1_000_000
    )


def _parse_openclaw_sessions(agents_dir: Path, since_ts: Optional[str] = None):
    """Parse OpenClaw JSONL session logs, aggregate by agent+date+model.
    
    Returns list of dicts: {agent_name, date, model, input_tokens, output_tokens, cost_usd}
    """
    from datetime import datetime as _dt
    from collections import defaultdict

    # Aggregation key: (agent_name, date_str, model)
    agg = defaultdict(lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0})

    since_dt = None
    if since_ts:
        try:
            since_dt = _dt.fromisoformat(since_ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()]
    sessions_scanned = 0
    messages_scanned = 0

    for agent_dir in agent_dirs:
        agent_name = agent_dir.name
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.exists():
            continue

        for jsonl_file in sessions_dir.glob("*.jsonl"):
            # Skip deleted/reset files unless they have usage data
            fname = jsonl_file.name
            if ".deleted." in fname or ".reset." in fname:
                continue

            sessions_scanned += 1
            try:
                with open(jsonl_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if entry.get("type") != "message":
                            continue
                        msg = entry.get("message", {})
                        usage = msg.get("usage")
                        if not usage:
                            continue

                        # Check timestamp filter
                        ts = entry.get("timestamp", "")
                        if since_dt and ts:
                            try:
                                entry_dt = _dt.fromisoformat(ts.replace("Z", "+00:00"))
                                if entry_dt < since_dt:
                                    continue
                            except (ValueError, AttributeError):
                                pass

                        # Extract model
                        model = msg.get("model", "")

                        # Extract date from timestamp
                        date_str = ts[:10] if len(ts) >= 10 else _dt.now().strftime("%Y-%m-%d")

                        key = (agent_name, date_str, model)
                        agg[key]["input"] += usage.get("input", 0)
                        agg[key]["output"] += usage.get("output", 0)
                        agg[key]["cache_read"] += usage.get("cacheRead", 0)
                        agg[key]["cache_write"] += usage.get("cacheWrite", 0)
                        messages_scanned += 1
            except (PermissionError, OSError) as e:
                print(f"  ⚠ Cannot read {jsonl_file.name}: {e}")

    print(f"  Scanned {sessions_scanned} sessions, {messages_scanned} messages")

    # Build records with recalculated costs, skip zero-usage entries
    records = []
    for (agent_name, date_str, model), tokens in agg.items():
        total_tokens = tokens["input"] + tokens["output"] + tokens["cache_read"] + tokens["cache_write"]
        if total_tokens == 0:
            continue

        cost = _recalc_cost(
            tokens["input"], tokens["output"],
            tokens["cache_read"], tokens["cache_write"],
            model, agent_name,
        )
        resolved_model = model
        if not resolved_model or resolved_model in ("delivery-mirror", "unknown", ""):
            resolved_model = _AGENT_MODEL_DEFAULTS.get(agent_name, "unknown")
        if "/" in resolved_model:
            resolved_model = resolved_model.split("/", 1)[1]

        display_name = _AGENT_NAME_MAP.get(agent_name, agent_name.capitalize())
        records.append({
            "agent_name": display_name,
            "date": date_str,
            "model": resolved_model,
            "input_tokens": tokens["input"] + tokens["cache_read"],
            "output_tokens": tokens["output"] + tokens["cache_write"],
            "cost_usd": round(cost, 4),
        })

    return records


def cmd_costs_auto(args):
    """Auto-collect costs from local agent framework logs."""
    from datetime import datetime as _dt

    source = args.source or "openclaw"
    state_file = CONFIG_DIR / "costs_sync_state.json"

    # Load last sync state
    state = {}
    if state_file.exists():
        state = json.loads(state_file.read_text())

    last_sync = state.get("last_sync")
    if args.full:
        last_sync = None
        print("Full rescan mode (ignoring last sync timestamp)")

    if source == "openclaw":
        # Auto-detect OpenClaw agents directory
        agents_dir = Path(args.path) if args.path else Path.home() / ".openclaw" / "agents"
        if not agents_dir.exists():
            print(f"Error: OpenClaw agents directory not found at {agents_dir}")
            print("Use --path to specify the directory.")
            sys.exit(1)

        print(f"📊 Scanning OpenClaw logs at {agents_dir}")
        if last_sync:
            print(f"  Since: {last_sync}")
        else:
            print("  Full scan (no previous sync)")

        records = _parse_openclaw_sessions(agents_dir, since_ts=last_sync)

        if not records:
            print("No cost data found.")
            return

        # Show summary before pushing
        total_cost = sum(r["cost_usd"] for r in records)
        agents_seen = set(r["agent_name"] for r in records)
        dates_seen = set(r["date"] for r in records)
        print(f"\n  Found {len(records)} records:")
        print(f"  Agents: {', '.join(sorted(agents_seen))}")
        print(f"  Dates: {min(dates_seen)} → {max(dates_seen)}")
        print(f"  Total cost: ${total_cost:.2f}")

        if args.dry_run:
            print("\n[DRY RUN] Would push these records:")
            for r in sorted(records, key=lambda x: (x["date"], x["agent_name"])):
                print(f"  {r['date']} | {r['agent_name']:<10} | {r['model']:<25} | ${r['cost_usd']:>8.4f}")
            return

        # Push to CRM
        print(f"\nPushing {len(records)} records to CRM...")
        resp = api("POST", "/api/costs", json={"records": records})
        if resp.status_code not in (200, 201):
            die(resp)
        result = resp.json()
        print(f"✅ Ingested: {result.get('ingested', 0)}, Updated: {result.get('updated', 0)}")
        if result.get("created_agents"):
            print(f"  New agents: {', '.join(result['created_agents'])}")

        # Save sync state
        from datetime import timezone as _tz
        state["last_sync"] = _dt.now(_tz.utc).isoformat()
        state["last_records"] = len(records)
        state["last_cost"] = total_cost
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2))
        print(f"  Sync state saved to {state_file}")

    else:
        print(f"Error: Unknown source '{source}'. Supported: openclaw")
        print("More sources coming: litellm, langchain, openai")
        sys.exit(1)


# --- Commands (bidirectional control) ---

# Agent display name → openclaw config agent id
_AGENT_CONFIG_MAP = {
    "Caramel": "main",
    "Sixteen": "sixteen",
    "Rex": "career",
    "Vibe": "social",
    "Mira": "mira",
    "Luna": "luna",
}


def _apply_model_change(agent_name: str, model: str, config_path: Path) -> tuple:
    """Update model.primary for the given agent in openclaw.json."""
    if not config_path.exists():
        return False, f"openclaw.json not found at {config_path}"
    try:
        config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Failed to read openclaw.json: {e}"

    agent_id = _AGENT_CONFIG_MAP.get(agent_name)
    if not agent_id:
        return False, f"Unknown agent: {agent_name}"

    agents_section = config.get("agents", {})
    agents = agents_section.get("list", []) if isinstance(agents_section, dict) else agents_section
    found = False
    for agent in agents:
        if agent.get("id") == agent_id:
            if "model" not in agent:
                agent["model"] = {}
            if "/" not in model:
                model = f"anthropic/{model}"
            agent["model"]["primary"] = model
            found = True
            break

    if not found:
        return False, f"Agent '{agent_id}' not found in openclaw.json"

    try:
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    except OSError as e:
        return False, f"Failed to write: {e}"

    return True, f"Updated {agent_name} → {model}"


def _handle_system_command(cmd_type: str) -> tuple:
    """Execute system commands (stop/resume/fix)."""
    import subprocess

    if cmd_type == "stop_gateway":
        try:
            r = subprocess.run(["openclaw", "gateway", "stop"], capture_output=True, text=True, timeout=20)
            return (r.returncode == 0), f"Gateway {'stopped' if r.returncode == 0 else 'failed: ' + r.stderr[:100]}"
        except Exception as e:
            return False, str(e)

    elif cmd_type == "resume_gateway":
        try:
            r = subprocess.run(["openclaw", "gateway", "start"], capture_output=True, text=True, timeout=20)
            return (r.returncode == 0), f"Gateway {'started' if r.returncode == 0 else 'failed: ' + r.stderr[:100]}"
        except Exception as e:
            return False, str(e)

    elif cmd_type == "restart_gateway":
        try:
            r = subprocess.run(["openclaw", "gateway", "restart"], capture_output=True, text=True, timeout=30)
            return (r.returncode == 0), f"Gateway {'restarted' if r.returncode == 0 else 'failed: ' + r.stderr[:100]}"
        except Exception as e:
            return False, str(e)

    return False, f"Unknown system command: {cmd_type}"


def cmd_commands_poll(args):
    """Poll and optionally apply pending CRM commands."""
    resp = api("GET", "/api/commands/pending")
    if resp.status_code != 200:
        die(resp)

    commands = resp.json()
    if not commands:
        print("No pending commands.")
        return

    print(f"Found {len(commands)} pending command(s):")
    openclaw_config = Path(args.config) if args.config else Path.home() / ".openclaw" / "openclaw.json"

    for cmd in commands:
        cmd_id = cmd["id"]
        cmd_type = cmd["command_type"]
        try:
            payload = json.loads(cmd["payload"]) if isinstance(cmd["payload"], str) else cmd["payload"]
        except (json.JSONDecodeError, TypeError):
            payload = {}

        print(f"\n  [{cmd_id}] {cmd_type}: {payload}")

        if args.dry_run:
            print(f"    [DRY RUN] Would apply {cmd_type}")
            continue

        if not args.apply:
            print(f"    Use --apply to execute, or --dry-run to preview")
            continue

        # Apply the command
        success, message = False, "Unknown command type"

        if cmd_type == "change_model":
            agent_name = payload.get("agent_name", "")
            model = payload.get("model", "")
            success, message = _apply_model_change(agent_name, model, openclaw_config)

        elif cmd_type in ("stop_gateway", "resume_gateway", "restart_gateway", "fix_system"):
            success, message = _handle_system_command(cmd_type)

        print(f"    {'✅' if success else '❌'} {message}")

        # Acknowledge
        ack_data = {"status": "applied"} if success else {"status": "failed", "error": message}
        ack_resp = api("POST", f"/api/commands/{cmd_id}/ack", json=ack_data)
        if ack_resp.status_code == 200:
            print(f"    Acknowledged")
        else:
            print(f"    ⚠ ACK failed: {ack_resp.status_code}")


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
    costs_push = costs_sub.add_parser("push", help="Push cost records from JSON file")
    costs_push.add_argument("--file", "-f", help="Path to costs.json")
    costs_auto = costs_sub.add_parser("auto", help="Auto-collect costs from agent framework logs")
    costs_auto.add_argument("--source", "-s", default="openclaw", help="Source: openclaw (default), litellm, langchain")
    costs_auto.add_argument("--path", "-p", help="Path to agents directory (auto-detected for openclaw)")
    costs_auto.add_argument("--full", action="store_true", help="Full rescan (ignore last sync)")
    costs_auto.add_argument("--dry-run", action="store_true", help="Show what would be pushed without sending")

    # commands
    cmds_parser = sub.add_parser("commands", help="Bidirectional CRM ↔ agent control")
    cmds_sub = cmds_parser.add_subparsers(dest="cmds_command")
    cmds_poll = cmds_sub.add_parser("poll", help="Poll and apply pending commands from CRM")
    cmds_poll.add_argument("--apply", action="store_true", help="Actually execute commands (default: list only)")
    cmds_poll.add_argument("--dry-run", action="store_true", help="Show what would be done")
    cmds_poll.add_argument("--config", help="Path to openclaw.json (auto-detected)")

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
        elif args.costs_command == "auto":
            cmd_costs_auto(args)
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
    elif args.command == "commands":
        if args.cmds_command == "poll":
            cmd_commands_poll(args)
        else:
            cmds_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
