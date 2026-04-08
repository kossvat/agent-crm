"""File viewer for agent workspace files — filesystem first, DB fallback."""

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

AGENT_FILES = {
    "Caramel": {"workspace": "workspace", "files": ["SOUL.md", "IDENTITY.md", "MEMORY.md"]},
    "Sixteen": {"workspace": "workspace-sixteen", "files": ["SOUL.md", "IDENTITY.md", "MEMORY.md"]},
    "Rex": {"workspace": "workspace-career", "files": ["SOUL.md", "IDENTITY.md", "MEMORY.md"]},
    "Vibe": {"workspace": "workspace-vibe", "files": ["SOUL.md", "IDENTITY.md", "MEMORY.md"]},
}


def _has_local_filesystem() -> bool:
    """Check if the local OpenClaw directory exists."""
    return Path(OPENCLAW_DIR).exists()


def _list_files_from_fs() -> list[dict]:
    """Read file listing from local filesystem."""
    openclaw_path = Path(OPENCLAW_DIR)
    result = []
    for agent_name, cfg in AGENT_FILES.items():
        ws_dir = openclaw_path / cfg["workspace"]
        for filename in cfg["files"]:
            filepath = ws_dir / filename
            result.append({
                "agent": agent_name,
                "filename": filename,
                "exists": filepath.exists(),
                "size": filepath.stat().st_size if filepath.exists() else 0,
            })
    return result


def _list_files_from_db(workspace_id: int) -> list[dict]:
    """Read file listing from database."""
    db: Session = SessionLocal()
    try:
        rows = (
            db.query(AgentFile, Agent.name)
            .join(Agent, AgentFile.agent_id == Agent.id)
            .filter(AgentFile.workspace_id == workspace_id)
            .all()
        )
        # Build lookup of what we have in DB
        db_files = {}
        for af, agent_name in rows:
            db_files[(agent_name, af.filename)] = af

        result = []
        for agent_name, cfg in AGENT_FILES.items():
            for filename in cfg["files"]:
                af = db_files.get((agent_name, filename))
                result.append({
                    "agent": agent_name,
                    "filename": filename,
                    "exists": af is not None and bool(af.content),
                    "size": af.size if af else 0,
                })
        return result
    finally:
        db.close()


def _read_file_from_fs(agent: str, filename: str) -> Optional[dict]:
    """Try to read file from local filesystem. Returns None if not available."""
    openclaw_path = Path(OPENCLAW_DIR)
    if not openclaw_path.exists():
        return None

    cfg = AGENT_FILES.get(agent)
    if not cfg:
        return None

    filepath = openclaw_path / cfg["workspace"] / filename
    if not filepath.exists():
        return None

    # Prevent path traversal
    try:
        filepath.resolve().relative_to(Path(OPENCLAW_DIR).resolve())
    except ValueError:
        return None

    content = filepath.read_text(encoding="utf-8", errors="replace")
    return {
        "agent": agent,
        "filename": filename,
        "content": content,
        "size": len(content),
    }


def _read_file_from_db(agent: str, filename: str, workspace_id: int) -> Optional[dict]:
    """Try to read file from database. Returns None if not found."""
    db: Session = SessionLocal()
    try:
        row = (
            db.query(AgentFile)
            .join(Agent, AgentFile.agent_id == Agent.id)
            .filter(
                Agent.name == agent,
                AgentFile.filename == filename,
                AgentFile.workspace_id == workspace_id,
            )
            .first()
        )
        if not row:
            return None
        return {
            "agent": agent,
            "filename": filename,
            "content": row.content or "",
            "size": row.size,
        }
    finally:
        db.close()


@router.get("")
def list_files(user: dict = Depends(get_current_user)):
    """List all viewable files grouped by agent."""
    if _has_local_filesystem():
        return _list_files_from_fs()
    return _list_files_from_db(user.get("workspace_id", 1))


@router.get("/{agent}/{filename}")
def read_file(agent: str, filename: str, user: dict = Depends(get_current_user)):
    """Read a whitelisted file (markdown content)."""
    cfg = AGENT_FILES.get(agent)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Agent '{agent}' not found")
    if filename not in cfg["files"]:
        raise HTTPException(status_code=403, detail=f"File '{filename}' not in whitelist")

    # Try filesystem first
    result = _read_file_from_fs(agent, filename)
    if result:
        return result

    # Fallback to DB
    result = _read_file_from_db(agent, filename, user.get("workspace_id", 1))
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
