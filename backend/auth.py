"""Telegram Mini App initData HMAC-SHA256 validation."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote

from fastapi import Request, HTTPException
from backend.config import BOT_TOKEN, DEV_MODE


def validate_init_data(init_data: str) -> dict:
    """
    Validate Telegram WebApp initData using HMAC-SHA256.
    Returns parsed user data on success.
    Raises ValueError on failure.

    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        raise ValueError("Empty initData")

    # Parse query string
    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = parsed.pop("hash", [None])[0]

    if not received_hash:
        raise ValueError("No hash in initData")

    # Build data-check-string: sorted key=value pairs joined by \n
    data_pairs = []
    for key in sorted(parsed.keys()):
        val = parsed[key][0]
        data_pairs.append(f"{key}={val}")
    data_check_string = "\n".join(data_pairs)

    # Compute HMAC
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Invalid hash")

    # Check auth_date freshness (allow 24h)
    auth_date = int(parsed.get("auth_date", [0])[0])
    if time.time() - auth_date > 86400:
        raise ValueError("initData expired")

    # Extract user
    user_raw = parsed.get("user", ["{}"])[0]
    user = json.loads(unquote(user_raw))

    return {
        "user_id": user.get("id"),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "username": user.get("username", ""),
        "language_code": user.get("language_code", "en"),
    }


# Owner Telegram user_id — full access
OWNER_USER_ID = 1080204489

# Agent name → agent_id mapping (set after first DB sync)
# Agents with full access (owner + Caramel)
FULL_ACCESS_AGENT_IDS = {2}  # Caramel

# Agent name → CRM agent_id (populated at runtime or hardcoded)
AGENT_NAME_TO_ID = {
    "rex": 1,
    "caramel": 2,
    "sixteen": 3,
    "vibe": 4,
}


def _is_local_request(request: Request) -> bool:
    """Check if request comes from localhost."""
    client = request.client
    if not client:
        return False
    return client.host in ("127.0.0.1", "::1", "localhost")


def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency — extract and validate Telegram user from request.
    - Local agent-to-agent calls: X-Agent-Id header from localhost
    - Telegram Mini App: X-Telegram-Init-Data header (HMAC validated)
    - Everything else: 401
    """
    # Agent-to-agent calls from localhost (OpenClaw agents)
    agent_header = request.headers.get("X-Agent-Id", "")
    if agent_header and _is_local_request(request):
        agent_id = int(agent_header) if agent_header.isdigit() else AGENT_NAME_TO_ID.get(agent_header.lower(), 0)
        return {
            "user_id": 0,
            "agent_id": agent_id,
            "is_owner": False,
            "full_access": agent_id in FULL_ACCESS_AGENT_IDS,
            "username": agent_header,
        }

    # Telegram Mini App auth
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        raise HTTPException(status_code=401, detail="Unauthorized — open via Telegram bot")

    try:
        user = validate_init_data(init_data)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # Only allow owner
    if user.get("user_id") != OWNER_USER_ID:
        raise HTTPException(status_code=403, detail="Access denied")

    user["is_owner"] = True
    user["full_access"] = True
    user["agent_id"] = None
    return user


def has_task_access(user: dict, task, action: str = "read") -> bool:
    """Check if user has access to a specific task.
    
    Full access (owner + Caramel): everything.
    Agents: read/write only their own tasks.
    """
    if user.get("full_access"):
        return True

    agent_id = user.get("agent_id")
    if not agent_id:
        return False

    if action == "read":
        return task.agent_id == agent_id or task.agent_id is None
    else:  # write, delete
        return task.agent_id == agent_id
