"""Skill distribution endpoints — ZIP download and setup message for AgentCRM Sync."""

import io
import json
import logging
import os
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.auth import create_workspace_token, decode_workspace_token, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup", tags=["setup"])

SKILL_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "skill_template"


def _get_base_url(request: Request) -> str:
    """Get the CRM base URL from env or request."""
    env_url = os.environ.get("WEB_APP_URL")
    if env_url:
        return env_url.rstrip("/")
    # Derive from request
    return str(request.base_url).rstrip("/")


def _validate_token(token: str) -> dict:
    """Validate workspace token and return decoded payload."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        payload = decode_workspace_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid workspace token")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid workspace token")
    return payload


@router.get("/skill")
async def download_skill_zip(request: Request, token: str = Query(..., description="Workspace token")):
    """Download the AgentCRM Sync skill as a ZIP file with pre-configured config.json."""
    _validate_token(token)
    base_url = _get_base_url(request)

    # Read skill template files
    skill_md_path = SKILL_TEMPLATE_DIR / "SKILL.md"
    apply_py_path = SKILL_TEMPLATE_DIR / "apply_commands.py"

    if not skill_md_path.exists() or not apply_py_path.exists():
        raise HTTPException(status_code=500, detail="Skill template files not found")

    skill_md = skill_md_path.read_text()
    apply_py = apply_py_path.read_text()

    # Generate config.json with the token and URL
    config_json = json.dumps({"url": base_url, "token": token}, indent=2) + "\n"

    # Create ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill_md)
        zf.writestr("apply_commands.py", apply_py)
        zf.writestr("config.json", config_json)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="agentcrm-sync.zip"'},
    )


@router.get("/message")
async def get_setup_message(
    request: Request,
    token: str = Query(None, description="Workspace token (optional if JWT auth)"),
    user: dict = Depends(get_current_user),
):
    """Get the ready-to-copy setup message for the agent.
    Can use either workspace_token query param or JWT auth.
    """
    if not token:
        # Generate a fresh workspace token from JWT user context
        ws_id = user.get("workspace_id", 1)
        token = create_workspace_token(ws_id, days=30)
    else:
        _validate_token(token)
    base_url = _get_base_url(request)

    skill_url = f"{base_url}/api/setup/skill?token={token}"
    message = (
        f"Install the AgentCRM Sync skill so I can control you from my CRM dashboard "
        f"(change models, stop/resume, monitor spending).\n\n"
        f"Steps:\n"
        f"1. Download: curl -sL \"{skill_url}\" -o /tmp/agentcrm-sync.zip\n"
        f"2. Install: mkdir -p ~/.openclaw/skills/agentcrm-sync && "
        f"unzip -o /tmp/agentcrm-sync.zip -d ~/.openclaw/skills/agentcrm-sync/ && "
        f"rm /tmp/agentcrm-sync.zip\n"
        f"3. Add cron (runs every minute):\n"
        f"(crontab -l 2>/dev/null; echo \"* * * * * cd ~/.openclaw/skills/agentcrm-sync && "
        f"python3 apply_commands.py >> /tmp/agentcrm-sync.log 2>&1\") | crontab -\n\n"
        f"Done! Commands from the CRM will auto-apply within 60 seconds."
    )

    return {"message": message}
