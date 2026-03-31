#!/usr/bin/env python3
"""
Apply pending CRM commands to the local OpenClaw instance.

Polls the CRM API for pending commands, applies them (e.g. model changes
to openclaw.json), and acknowledges completion.

Usage:
    python3 scripts/apply_commands.py --url https://myaiagentscrm.com --token TOKEN

Cron setup (hourly, alongside sync_spending):
    0 * * * * python3 /path/to/apply_commands.py --url https://myaiagentscrm.com --token YOUR_TOKEN
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# openclaw.json default location
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"

# Agent display name → openclaw config agent id
AGENT_CONFIG_MAP = {
    "Caramel": "main",
    "Sixteen": "sixteen",
    "Rex": "career",
    "Vibe": "social",
    "Mira": "mira",
}


def api_get(url: str, token: str, path: str) -> list | dict:
    """GET request to CRM API with workspace token."""
    req = Request(
        f"{url.rstrip('/')}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        return []
    except URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        return []


def api_post(url: str, token: str, path: str, data: dict) -> dict:
    """POST request to CRM API with workspace token."""
    payload = json.dumps(data).encode()
    req = Request(
        f"{url.rstrip('/')}{path}",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        return {"ok": False, "error": body}
    except URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        return {"ok": False, "error": str(e.reason)}


def apply_model_change(agent_name: str, model: str, config_path: Path) -> tuple[bool, str]:
    """Update model.primary for the given agent in openclaw.json."""
    if not config_path.exists():
        return False, f"openclaw.json not found at {config_path}"

    try:
        config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Failed to read openclaw.json: {e}"

    agent_id = AGENT_CONFIG_MAP.get(agent_name)
    if not agent_id:
        return False, f"Unknown agent name: {agent_name} (not in AGENT_CONFIG_MAP)"

    # Find agent in config.agents array
    agents = config.get("agents", [])
    found = False
    for agent in agents:
        if agent.get("id") == agent_id:
            if "model" not in agent:
                agent["model"] = {}
            agent["model"]["primary"] = model
            found = True
            break

    if not found:
        return False, f"Agent id '{agent_id}' not found in openclaw.json agents"

    try:
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    except OSError as e:
        return False, f"Failed to write openclaw.json: {e}"

    return True, f"Updated {agent_name} ({agent_id}) model to {model}"


def restart_gateway() -> tuple[bool, str]:
    """Restart OpenClaw gateway."""
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "restart"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True, "Gateway restarted successfully"
        else:
            return False, f"Gateway restart failed: {result.stderr or result.stdout}"
    except FileNotFoundError:
        return False, "openclaw CLI not found in PATH"
    except subprocess.TimeoutExpired:
        return False, "Gateway restart timed out"
    except Exception as e:
        return False, f"Gateway restart error: {e}"


def main():
    parser = argparse.ArgumentParser(description="Apply pending CRM commands to OpenClaw")
    parser.add_argument("--url", required=True, help="CRM base URL")
    parser.add_argument("--token", default=os.environ.get("WORKSPACE_TOKEN"), help="Workspace token")
    parser.add_argument("--config", type=str, default=str(OPENCLAW_CONFIG), help="Path to openclaw.json")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without applying")
    args = parser.parse_args()

    if not args.token:
        print("ERROR: --token or WORKSPACE_TOKEN env var required", file=sys.stderr)
        sys.exit(1)

    config_path = Path(args.config)

    # 1. Fetch pending commands
    commands = api_get(args.url, args.token, "/api/commands/pending/ws")
    if not commands:
        print("No pending commands.")
        return

    print(f"Found {len(commands)} pending command(s)")

    applied_any_model = False

    # 2. Process each command
    for cmd in commands:
        cmd_id = cmd["id"]
        cmd_type = cmd["command_type"]
        payload = json.loads(cmd["payload"]) if isinstance(cmd["payload"], str) else cmd["payload"]

        print(f"  [{cmd_id}] {cmd_type}: {payload}")

        if cmd_type == "change_model":
            agent_name = payload.get("agent_name", "")
            model = payload.get("model", "")

            if args.dry_run:
                print(f"    DRY RUN: would update {agent_name} → {model}")
                continue

            success, message = apply_model_change(agent_name, model, config_path)
            print(f"    {message}")

            # Acknowledge
            ack_data = {"status": "applied"} if success else {"status": "failed", "error": message}
            api_post(args.url, args.token, f"/api/commands/{cmd_id}/ack", ack_data)

            if success:
                applied_any_model = True
        else:
            print(f"    Unknown command type: {cmd_type}, skipping")
            api_post(
                args.url, args.token, f"/api/commands/{cmd_id}/ack",
                {"status": "failed", "error": f"Unknown command type: {cmd_type}"},
            )

    # 3. Restart gateway if any model changes were applied
    if applied_any_model and not args.dry_run:
        print("Restarting gateway...")
        success, message = restart_gateway()
        print(f"  {message}")
        if not success:
            print("WARNING: Gateway restart failed — changes saved but not yet active", file=sys.stderr)

    print("Done.")


if __name__ == "__main__":
    main()
