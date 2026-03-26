"""OpenClaw integration — parse status, sessions, crontab."""

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from backend.config import OPENCLAW_BIN, OPENCLAW_DIR

log = logging.getLogger("agent-crm.openclaw")

# Agent dir name → display name mapping
AGENT_MAP = {
    "main": {"name": "Caramel", "emoji": "🍬", "workspace": "workspace"},
    "sixteen": {"name": "Sixteen", "emoji": "🔧", "workspace": "workspace-sixteen"},
    "career": {"name": "Rex", "emoji": "🦅", "workspace": "workspace-career"},
    "social": {"name": "Vibe", "emoji": "⚡", "workspace": "workspace-social"},
    "vibe": {"name": "Vibe", "emoji": "⚡", "workspace": "workspace-vibe"},
}

# Skip these agent dirs
SKIP_AGENTS = {"claude-code"}


def run_cmd(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        log.warning(f"Command timed out: {' '.join(cmd)}")
        return -1, "", "timeout"
    except FileNotFoundError:
        log.error(f"Command not found: {cmd[0]}")
        return -1, "", "not found"


def get_openclaw_status() -> Optional[dict]:
    """Run 'openclaw status' and parse output."""
    code, stdout, stderr = run_cmd([OPENCLAW_BIN, "status"])
    if code != 0:
        log.error(f"openclaw status failed: {stderr}")
        return None

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        pass

    return {"raw": stdout}


def get_sessions() -> list[dict]:
    """Get active OpenClaw sessions. Currently disabled — openclaw CLI sessions command is slow/broken."""
    # TODO: re-enable when openclaw sessions CLI is fixed
    return []


def get_crontab_entries() -> list[dict]:
    """Read crontab and filter for openclaw-related entries."""
    code, stdout, stderr = run_cmd(["crontab", "-l"])
    if code != 0:
        return []

    entries = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if any(kw in line.lower() for kw in ["openclaw", "agent", "token", "refresh"]):
            parts = line.split(None, 5)
            if len(parts) >= 6:
                entries.append({
                    "schedule": " ".join(parts[:5]),
                    "command": parts[5],
                    "raw": line,
                })
            else:
                entries.append({"schedule": "", "command": line, "raw": line})

    return entries


def get_agent_configs() -> list[dict]:
    """Read agent configs from OpenClaw directory."""
    agents_dir = Path(OPENCLAW_DIR) / "agents"
    if not agents_dir.exists():
        return []

    agents = []
    seen_names = set()

    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue

        dir_name = agent_dir.name
        if dir_name in SKIP_AGENTS:
            continue

        # Use mapping if available
        mapped = AGENT_MAP.get(dir_name, {})
        display_name = mapped.get("name", dir_name.capitalize())

        # Deduplicate (vibe and social both map to Vibe)
        if display_name in seen_names:
            continue
        seen_names.add(display_name)

        agent_info = {
            "name": display_name,
            "emoji": mapped.get("emoji", "🤖"),
            "model": "",
            "session_key": "",
        }

        # Try reading IDENTITY.md from specific workspace
        ws_name = mapped.get("workspace", f"workspace-{dir_name}")
        ws_dir = Path(OPENCLAW_DIR) / ws_name
        identity_file = ws_dir / "IDENTITY.md"

        if identity_file.exists():
            try:
                content = identity_file.read_text()
                emoji_match = re.search(r"Emoji[:\s]+\**(\S+?)\**\s*$", content, re.MULTILINE)
                if emoji_match:
                    agent_info["emoji"] = emoji_match.group(1)
                name_match = re.search(r"Name[:\s]+\**(.+?)\**\s*$", content, re.MULTILINE)
                if name_match:
                    agent_info["name"] = name_match.group(1).strip()
            except Exception:
                pass

        agents.append(agent_info)

    return agents
