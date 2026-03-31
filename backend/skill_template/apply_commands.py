#!/usr/bin/env python3
"""
Apply pending CRM commands to the local OpenClaw instance.

Polls the CRM API for pending commands, applies them (e.g. model changes
to openclaw.json), and acknowledges completion.

Configuration:
    Reads from config.json in the same directory (auto-generated during setup).
    Falls back to CLI args if config.json is not found.

Cron setup (every minute):
    * * * * * cd ~/.openclaw/skills/agentcrm-sync && python3 apply_commands.py >> /tmp/agentcrm-sync.log 2>&1
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


def load_config() -> dict | None:
    """Load config from config.json in the same directory as this script."""
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: failed to read config.json: {e}", file=sys.stderr)
    return None


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
            # Ensure model has provider prefix (openclaw.json requires it)
            if "/" not in model:
                model = f"anthropic/{model}"
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


def handle_stop_gateway() -> tuple[bool, str]:
    """Stop gateway and disable all crons."""
    results = []
    try:
        r = subprocess.run(["openclaw", "gateway", "stop"], capture_output=True, text=True, timeout=20)
        results.append(f"gateway: {'stopped' if r.returncode == 0 else r.stderr[:100]}")
    except Exception as e:
        return False, f"Failed to stop gateway: {e}"

    try:
        r = subprocess.run(
            ["openclaw", "cron", "list", "--json", "--all"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            disabled = 0
            for cron in data.get("items", []):
                if cron.get("enabled"):
                    subprocess.run(["openclaw", "cron", "disable", cron["id"]], timeout=10)
                    disabled += 1
            results.append(f"crons disabled: {disabled}")
    except Exception as e:
        results.append(f"cron error: {e}")

    return True, "; ".join(results)


def handle_resume_gateway() -> tuple[bool, str]:
    """Start gateway and enable all crons."""
    results = []
    try:
        r = subprocess.run(["openclaw", "gateway", "start"], capture_output=True, text=True, timeout=20)
        results.append(f"gateway: {'started' if r.returncode == 0 else r.stderr[:100]}")
    except Exception as e:
        return False, f"Failed to start gateway: {e}"

    try:
        r = subprocess.run(
            ["openclaw", "cron", "list", "--json", "--all"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            enabled = 0
            for cron in data.get("items", []):
                if not cron.get("enabled"):
                    subprocess.run(["openclaw", "cron", "enable", cron["id"]], timeout=10)
                    enabled += 1
            results.append(f"crons enabled: {enabled}")
    except Exception as e:
        results.append(f"cron error: {e}")

    return True, "; ".join(results)


def handle_fix_system() -> tuple[bool, str]:
    """Clear large session files and disable all crons."""
    results = []

    # Clear large session files (>500KB)
    agents_dir = Path(os.path.expanduser("~/.openclaw/agents"))
    cleared = 0
    if agents_dir.exists():
        for jsonl in agents_dir.glob("*/sessions/*.jsonl"):
            try:
                if jsonl.stat().st_size > 500 * 1024:
                    jsonl.unlink()
                    cleared += 1
            except Exception:
                pass
    results.append(f"sessions cleared: {cleared}")

    # Disable all crons
    try:
        r = subprocess.run(
            ["openclaw", "cron", "list", "--json", "--all"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            disabled = 0
            for cron in data.get("items", []):
                if cron.get("enabled"):
                    subprocess.run(["openclaw", "cron", "disable", cron["id"]], timeout=10)
                    disabled += 1
            results.append(f"crons disabled: {disabled}")
    except Exception as e:
        results.append(f"cron error: {e}")

    return True, "; ".join(results)


def main():
    # Try config.json first
    file_config = load_config()

    parser = argparse.ArgumentParser(description="Apply pending CRM commands to OpenClaw")
    parser.add_argument("--url", default=file_config.get("url") if file_config else None, help="CRM base URL")
    parser.add_argument("--token", default=file_config.get("token") if file_config else os.environ.get("WORKSPACE_TOKEN"), help="Workspace token")
    parser.add_argument("--config", type=str, default=str(OPENCLAW_CONFIG), help="Path to openclaw.json")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without applying")
    args = parser.parse_args()

    if not args.url:
        print("ERROR: --url required (or set in config.json)", file=sys.stderr)
        sys.exit(1)

    if not args.token:
        print("ERROR: --token or WORKSPACE_TOKEN env var required (or set in config.json)", file=sys.stderr)
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

        elif cmd_type in ("stop_gateway", "resume_gateway", "fix_system"):
            if args.dry_run:
                print(f"    DRY RUN: would execute {cmd_type}")
                continue

            handler = {
                "stop_gateway": handle_stop_gateway,
                "resume_gateway": handle_resume_gateway,
                "fix_system": handle_fix_system,
            }[cmd_type]

            success, message = handler()
            print(f"    {message}")

            ack_data = {"status": "applied"} if success else {"status": "failed", "error": message}
            api_post(args.url, args.token, f"/api/commands/{cmd_id}/ack", ack_data)

        else:
            print(f"    Unknown command type: {cmd_type}, skipping")
            api_post(
                args.url, args.token, f"/api/commands/{cmd_id}/ack",
                {"status": "failed", "error": f"Unknown command type: {cmd_type}"},
            )

    # 3. Model changes auto-apply via OpenClaw hot reload (hybrid mode)
    if applied_any_model:
        print("Model changes written to openclaw.json — hot reload will apply automatically.")

    print("Done.")


if __name__ == "__main__":
    main()
