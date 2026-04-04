"""File viewer for agent workspace files — workspace-isolated.

Local filesystem is only used for workspace_id=1 (the host owner).
All other workspaces read from the database (synced via /files/sync).
Agent names are never hardcoded — they come from the user's workspace.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user, decode_workspace_token
from backend.config import OPENCLAW_DIR
from backend.database import SessionLocal
from backend.models import Agent, AgentFile

router = APIRouter(prefix="/api/files", tags=["files"])

# Viewable filenames (whitelist)
VIEWABLE_FILES = ["SOUL.md", "IDENTITY.md", "MEMORY.md"]

# Workspace directory mapping for the LOCAL owner (workspace_id=1).
# Maps agent session_key to their workspace folder name.
LOCAL_WORKSPACE_MAP = {
    "caramel": "workspace",
    "sixteen": "workspace-sixteen",
    "career": "workspace-career",
    "vibe": "workspace-vibe",
}


def _is_local_owner(workspace_id: int) -> bool:
    """Only workspace_id=1 may use the local filesystem."""
    return workspace_id == 1 and Path(OPENCLAW_DIR).exists()


def _list_files_local(workspace_id: int) -> list[dict]:
    """List files from local filesystem for the owner workspace."""
    db: Session = SessionLocal()
    try:
        agents = (
            db.query(Agent)
            .filter(Agent.workspace_id == workspace_id)
            .order_by(Agent.name)
            .all()
        )
        openclaw_path = Path(OPENCLAW_DIR)
        result = []
        for agent in agents:
            # Try to find workspace dir by session_key
            ws_folder = LOCAL_WORKSPACE_MAP.get(
                (agent.session_key or "").lower()
            )
            for filename in VIEWABLE_FILES:
                exists = False
                size = 0
                if ws_folder:
                    filepath = openclaw_path / ws_folder / filename
                    if filepath.exists():
                        exists = True
                        size = filepath.stat().st_size
                result.append({
                    "agent": agent.name,
                    "filename": filename,
                    "exists": exists,
                    "size": size,
                })
        return result
    finally:
        db.close()


def _list_files_from_db(workspace_id: int) -> list[dict]:
    """List files from database for remote workspaces."""
    db: Session = SessionLocal()
    try:
        # Get all agents in this workspace
        agents = (
            db.query(Agent)
            .filter(Agent.workspace_id == workspace_id)
            .order_by(Agent.name)
            .all()
        )
        # Get synced files
        rows = (
            db.query(AgentFile, Agent.name)
            .join(Agent, AgentFile.agent_id == Agent.id)
            .filter(AgentFile.workspace_id == workspace_id)
            .all()
        )
        db_files = {}
        for af, agent_name in rows:
            db_files[(agent_name, af.filename)] = af

        result = []
        for agent in agents:
            for filename in VIEWABLE_FILES:
                af = db_files.get((agent.name, filename))
                result.append({
                    "agent": agent.name,
                    "filename": filename,
                    "exists": af is not None and bool(af.content),
                    "size": af.size if af else 0,
                })
        return result
    finally:
        db.close()


def _read_file_local(agent_name: str, filename: str, workspace_id: int) -> Optional[dict]:
    """Read from local filesystem (owner only)."""
    db: Session = SessionLocal()
    try:
        agent = (
            db.query(Agent)
            .filter(Agent.name == agent_name, Agent.workspace_id == workspace_id)
            .first()
        )
        if not agent:
            return None
        ws_folder = LOCAL_WORKSPACE_MAP.get(
            (agent.session_key or "").lower()
        )
        if not ws_folder:
            return None
        openclaw_path = Path(OPENCLAW_DIR)
        filepath = openclaw_path / ws_folder / filename
        if not filepath.exists():
            return None
        # Prevent path traversal
        try:
            filepath.resolve().relative_to(openclaw_path.resolve())
        except ValueError:
            return None
        content = filepath.read_text(encoding="utf-8", errors="replace")
        return {
            "agent": agent_name,
            "filename": filename,
            "content": content,
            "size": len(content),
        }
    finally:
        db.close()


def _read_file_from_db(agent_name: str, filename: str, workspace_id: int) -> Optional[dict]:
    """Read from database."""
    db: Session = SessionLocal()
    try:
        row = (
            db.query(AgentFile)
            .join(Agent, AgentFile.agent_id == Agent.id)
            .filter(
                Agent.name == agent_name,
                AgentFile.filename == filename,
                AgentFile.workspace_id == workspace_id,
            )
            .first()
        )
        if not row:
            return None
        return {
            "agent": agent_name,
            "filename": filename,
            "content": row.content or "",
            "size": row.size,
        }
    finally:
        db.close()


@router.get("")
def list_files(user: dict = Depends(get_current_user)):
    """List all viewable files for the current user's workspace."""
    ws_id = user.get("workspace_id", 1)
    if _is_local_owner(ws_id):
        return _list_files_local(ws_id)
    return _list_files_from_db(ws_id)


@router.get("/{agent}/{filename}")
def read_file(agent: str, filename: str, user: dict = Depends(get_current_user)):
    """Read a whitelisted file (markdown content)."""
    if filename not in VIEWABLE_FILES:
        raise HTTPException(status_code=403, detail=f"File '{filename}' not in whitelist")

    ws_id = user.get("workspace_id", 1)

    # Local filesystem for owner only
    if _is_local_owner(ws_id):
        result = _read_file_local(agent, filename, ws_id)
        if result:
            return result

    # Database for everyone (including owner fallback)
    result = _read_file_from_db(agent, filename, ws_id)
    if result:
        return result

    raise HTTPException(status_code=404, detail="File not found")


# --- Sync endpoint (workspace token auth, like ingest) ---

class FileSyncItem(BaseModel):
    agent_name: str
    filename: str
    content: str


class FileSyncRequest(BaseModel):
    files: list[FileSyncItem]


class FileSyncResponse(BaseModel):
    synced: int
    created_agents: list[str]


def _get_workspace_id(request: Request) -> int:
    """Extract workspace_id from Authorization: Bearer <workspace_token>."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing workspace token")
    token = auth_header[7:]
    try:
        payload = decode_workspace_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return payload["workspace_id"]


@router.post("/sync", response_model=FileSyncResponse)
def sync_files(data: FileSyncRequest, request: Request):
    """Upsert agent files from remote sync script.

    Auth: workspace_token (Bearer header).
    """
    ws_id = _get_workspace_id(request)

    db: Session = SessionLocal()
    try:
        created_agents: list[str] = []
        synced = 0

        for item in data.files:
            # Find or create agent
            agent = (
                db.query(Agent)
                .filter(Agent.name == item.agent_name, Agent.workspace_id == ws_id)
                .first()
            )
            if not agent:
                agent = Agent(
                    name=item.agent_name,
                    emoji="🤖",
                    workspace_id=ws_id,
                )
                db.add(agent)
                db.flush()
                created_agents.append(item.agent_name)

            # Upsert file
            existing = (
                db.query(AgentFile)
                .filter(
                    AgentFile.agent_id == agent.id,
                    AgentFile.filename == item.filename,
                    AgentFile.workspace_id == ws_id,
                )
                .first()
            )
            if existing:
                existing.content = item.content
                existing.size = len(item.content.encode("utf-8"))
            else:
                af = AgentFile(
                    agent_id=agent.id,
                    filename=item.filename,
                    content=item.content,
                    size=len(item.content.encode("utf-8")),
                    workspace_id=ws_id,
                )
                db.add(af)

            synced += 1

        db.commit()
        return FileSyncResponse(synced=synced, created_agents=created_agents)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
