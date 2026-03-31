"""Skill distribution endpoints — ZIP download and setup message for AgentCRM Sync."""

import io
import json
import logging
import os
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.auth import decode_workspace_token

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
async def get_setup_message(request: Request, token: str = Query(..., description="Workspace token")):
    """Get the ready-to-copy setup message for the agent."""
    _validate_token(token)
    base_url = _get_base_url(request)

    skill_url = f"{base_url}/api/setup/skill?token={token}"
    message = (
        f"Install the AgentCRM sync skill to enable remote control from my CRM dashboard. "
        f"Download and extract: {skill_url} — extract to ~/.openclaw/skills/agentcrm-sync/ "
        f"and set up a cron job: add this line to crontab (crontab -e): "
        f"* * * * * cd ~/.openclaw/skills/agentcrm-sync && python3 apply_commands.py >> /tmp/agentcrm-sync.log 2>&1"
    )

    return {"message": message}
