"""OpenClaw integration — parse status, sessions, crontab, config management."""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from backend.config import OPENCLAW_BIN, OPENCLAW_DIR

log = logging.getLogger("agent-crm.openclaw")

# Agent dir name → display name mapping
AGENT_MAP = {
    "main": {"name": "Caramel", "emoji": "🍬", "workspace": "workspace", "role": "Coordinator", "bio": "Lead agent, team coordination"},
    "sixteen": {"name": "Sixteen", "emoji": "🔧", "workspace": "workspace-sixteen", "role": "CTO / Architect", "bio": "Code, architecture, debugging"},
    "career": {"name": "Rex", "emoji": "🦅", "workspace": "workspace-career", "role": "Career / Business", "bio": "Job search, business development"},
    "social": {"name": "Vibe", "emoji": "⚡", "workspace": "workspace-social", "role": "Content / SMM", "bio": "Social media, content planning"},
    "vibe": {"name": "Vibe", "emoji": "⚡", "workspace": "workspace-vibe", "role": "Content / SMM", "bio": "Social media, content planning"},
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
    """Get agent last-active times and models from session files."""
    sessions = []
    agents_dir = Path(OPENCLAW_DIR) / "agents"
    if not agents_dir.exists():
        return sessions

    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir() or agent_dir.name in SKIP_AGENTS:
            continue

        sessions_file = agent_dir / "sessions" / "sessions.json"
        if sessions_file.exists() and sessions_file.stat().st_size > 2:
            mtime = sessions_file.stat().st_mtime
            mapped = AGENT_MAP.get(agent_dir.name, {})

            # Extract model from session data
            model = ""
            try:
                data = json.loads(sessions_file.read_text())
                if isinstance(data, dict):
                    for key, val in data.items():
                        if isinstance(val, dict) and "model" in val:
                            model = val["model"]
                            break
            except Exception:
                pass

            sessions.append({
                "agent_dir": agent_dir.name,
                "name": mapped.get("name", agent_dir.name),
                "last_active_ts": mtime,
                "model": model,
            })

    return sessions


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
            "role": mapped.get("role", ""),
            "bio": mapped.get("bio", ""),
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


# --- Config management ---

CONFIG_PATH = Path(OPENCLAW_DIR) / "openclaw.json"

# Track whether a restart is needed after config change
_restart_pending = False


def read_config() -> dict:
    """Read and parse openclaw.json."""
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _write_config(config: dict) -> None:
    """Atomically write openclaw.json with backup.

    1. Serialize to string and validate
    2. Backup current file to .bak
    3. Write to temp file in same dir
    4. Atomic rename
    """
    # Serialize and validate roundtrip
    config_str = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    json.loads(config_str)  # validate — raises on bad JSON

    # Backup
    bak_path = CONFIG_PATH.with_suffix(".json.bak")
    if CONFIG_PATH.exists():
        shutil.copy2(CONFIG_PATH, bak_path)

    # Atomic write: temp file in same directory, then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=CONFIG_PATH.parent, suffix=".tmp", prefix="openclaw_"
    )
    try:
        os.write(fd, config_str.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp_path, CONFIG_PATH)
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def get_config_agent_models() -> dict[str, str]:
    """Return {agent_id: model_primary} from openclaw.json."""
    config = read_config()
    agents_list = config.get("agents", {}).get("list", [])
    result = {}
    for agent in agents_list:
        aid = agent.get("id", "")
        model = agent.get("model", {})
        if isinstance(model, dict):
            result[aid] = model.get("primary", "")
        elif isinstance(model, str):
            result[aid] = model
    return result


def update_agent_model(agent_config_id: str, new_model: str) -> bool:
    """Update model.primary for a specific agent in openclaw.json.

    Args:
        agent_config_id: The agent id in openclaw.json (e.g. "main", "sixteen")
        new_model: Full model string (e.g. "anthropic/claude-opus-4-6")

    Returns:
        True if updated, False if agent not found.
    """
    global _restart_pending

    config = read_config()
    agents_list = config.get("agents", {}).get("list", [])

    for agent in agents_list:
        if agent.get("id") == agent_config_id:
            if not isinstance(agent.get("model"), dict):
                agent["model"] = {"primary": new_model}
            else:
                agent["model"]["primary"] = new_model

            _write_config(config)
            _restart_pending = True
            log.info(f"Updated model for {agent_config_id} → {new_model}")
            return True

    log.warning(f"Agent {agent_config_id} not found in openclaw.json")
    return False


def is_restart_pending() -> bool:
    """Check if gateway restart is needed."""
    return _restart_pending


def restart_gateway() -> tuple[bool, str]:
    """Restart OpenClaw gateway. Returns (success, message)."""
    global _restart_pending

    code, stdout, stderr = run_cmd([OPENCLAW_BIN, "gateway", "restart"], timeout=30)
    if code == 0:
        _restart_pending = False
        log.info("Gateway restarted successfully")
        return True, "Gateway restarted"
    else:
        log.error(f"Gateway restart failed: {stderr}")
        return False, f"Restart failed: {stderr}"
