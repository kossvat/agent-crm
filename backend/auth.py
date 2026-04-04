"""Telegram Mini App initData HMAC-SHA256 validation + JWT auth."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs, unquote

import jwt
from fastapi import Request, HTTPException
from backend.config import BOT_TOKEN, DEV_MODE, SECRET_KEY

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def create_access_token(user_id: int, workspace_id: int) -> str:
    """Create a JWT token with user_id and workspace_id."""
    payload = {
        "user_id": user_id,
        "workspace_id": workspace_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_workspace_token(workspace_id: int, days: int = 30) -> str:
    """Create a long-lived JWT for remote agent ingest. No user_id — workspace-scoped."""
    payload = {
        "workspace_id": workspace_id,
        "type": "workspace",
        "exp": datetime.now(timezone.utc) + timedelta(days=days),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_workspace_token(token: str) -> dict:
    """Decode a workspace-scoped JWT. Returns {workspace_id}."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("Workspace token expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid workspace token: {e}")
    if payload.get("type") != "workspace":
        raise ValueError("Not a workspace token")
    return {"workspace_id": payload["workspace_id"]}


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT token. Returns payload dict."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}")


def validate_init_data(init_data: str) -> dict:
    """
    Validate Telegram WebApp initData using HMAC-SHA256.
    Returns parsed user data on success.
    Raises ValueError on failure.
    """
    if not init_data:
        raise ValueError("Empty initData")

    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = parsed.pop("hash", [None])[0]

    if not received_hash:
        raise ValueError("No hash in initData")

    data_pairs = []
    for key in sorted(parsed.keys()):
        val = parsed[key][0]
        data_pairs.append(f"{key}={val}")
    data_check_string = "\n".join(data_pairs)

    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Invalid hash")

    auth_date = int(parsed.get("auth_date", [0])[0])
    if time.time() - auth_date > 86400:
        raise ValueError("initData expired")

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
    FastAPI dependency — extract and validate user from request.
    Supports: JWT Bearer token, local agent X-Agent-Id, Telegram initData, DEV_MODE.
    """
    # 1. API key auth (X-Api-Key header) — for CLI and external integrations
    api_key = request.headers.get("X-Api-Key", "")
    if api_key:
        import hashlib
        from backend.database import SessionLocal
        from backend.models import Workspace
        _db = SessionLocal()
        try:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            workspace = _db.query(Workspace).filter(Workspace.api_key == key_hash).first()
            if not workspace:
                raise HTTPException(status_code=401, detail="Invalid API key")
            return {
                "user_id": workspace.owner_id,
                "workspace_id": workspace.id,
                "is_owner": True,
                "is_superadmin": False,
                "full_access": True,
                "agent_id": None,
                "username": "api_key",
                "auth_method": "api_key",
            }
        finally:
            _db.close()

    # 2. JWT Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_access_token(token)
            jwt_user_id = payload["user_id"]
            # Resolve is_owner and is_superadmin from DB
            from backend.database import SessionLocal
            from backend.models import User
            _db = SessionLocal()
            _user = _db.query(User).filter(User.id == jwt_user_id).first()
            _is_owner = _user and _user.telegram_id == OWNER_USER_ID if _user else False
            _is_superadmin = _user.is_superadmin if _user else False
            _db.close()
            return {
                "user_id": jwt_user_id,
                "workspace_id": payload["workspace_id"],
                "is_owner": _is_owner,
                "is_superadmin": _is_superadmin,
                "full_access": _is_owner,
                "agent_id": None,
                "username": _user.name if _user else "jwt_user",
            }
        except ValueError as e:
            raise HTTPException(status_code=401, detail=str(e))

    # 2. Agent-to-agent calls from localhost (OpenClaw agents)
    agent_header = request.headers.get("X-Agent-Id", "")
    if agent_header and _is_local_request(request):
        agent_id = int(agent_header) if agent_header.isdigit() else AGENT_NAME_TO_ID.get(agent_header.lower(), 0)
        return {
            "user_id": 0,
            "workspace_id": 1,
            "agent_id": agent_id,
            "is_owner": False,
            "full_access": agent_id in FULL_ACCESS_AGENT_IDS,
            "username": agent_header,
        }

    # 3. DEV_MODE bypass for screenshots/testing
    if DEV_MODE and _is_local_request(request):
        return {
            "user_id": OWNER_USER_ID,
            "workspace_id": 1,
            "is_owner": True,
            "full_access": True,
            "agent_id": None,
            "username": "dev",
        }

    # 4. Telegram Mini App auth
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        raise HTTPException(status_code=401, detail="Unauthorized — open via Telegram bot")

    try:
        user = validate_init_data(init_data)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # Only allow owner (legacy — multi-tenant uses JWT path)
    if user.get("user_id") != OWNER_USER_ID:
        raise HTTPException(status_code=403, detail="Access denied")

    user["is_owner"] = True
    user["full_access"] = True
    user["agent_id"] = None
    user["workspace_id"] = 1
    return user


def has_task_access(user: dict, task, action: str = "read") -> bool:
    """Check if user has access to a specific task."""
    if user.get("full_access"):
        return True

    agent_id = user.get("agent_id")
    if not agent_id:
        return False

    if action == "read":
        return task.agent_id == agent_id or task.agent_id is None
    else:
        return task.agent_id == agent_id
