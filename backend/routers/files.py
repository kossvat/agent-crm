"""Read-only file viewer for agent workspace files."""

from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from backend.auth import get_current_user
from backend.config import OPENCLAW_DIR

router = APIRouter(prefix="/api/files", tags=["files"])

AGENT_FILES = {
    "Caramel": {"workspace": "workspace", "files": ["SOUL.md", "IDENTITY.md", "MEMORY.md"]},
    "Sixteen": {"workspace": "workspace-sixteen", "files": ["SOUL.md", "IDENTITY.md", "MEMORY.md"]},
    "Rex": {"workspace": "workspace-career", "files": ["SOUL.md", "IDENTITY.md", "MEMORY.md"]},
    "Vibe": {"workspace": "workspace-vibe", "files": ["SOUL.md", "IDENTITY.md", "MEMORY.md"]},
}


@router.get("")
def list_files(user: dict = Depends(get_current_user)):
    """List all viewable files grouped by agent."""
    result = []
    for agent_name, cfg in AGENT_FILES.items():
        ws_dir = Path(OPENCLAW_DIR) / cfg["workspace"]
        for filename in cfg["files"]:
            filepath = ws_dir / filename
            result.append({
                "agent": agent_name,
                "filename": filename,
                "exists": filepath.exists(),
                "size": filepath.stat().st_size if filepath.exists() else 0,
            })
    return result


@router.get("/{agent}/{filename}")
def read_file(agent: str, filename: str, user: dict = Depends(get_current_user)):
    """Read a whitelisted file (markdown content)."""
    cfg = AGENT_FILES.get(agent)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Agent '{agent}' not found")

    if filename not in cfg["files"]:
        raise HTTPException(status_code=403, detail=f"File '{filename}' not in whitelist")

    filepath = Path(OPENCLAW_DIR) / cfg["workspace"] / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"File not found")

    # Prevent path traversal
    try:
        filepath.resolve().relative_to(Path(OPENCLAW_DIR).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    content = filepath.read_text(encoding="utf-8", errors="replace")
    return {
        "agent": agent,
        "filename": filename,
        "content": content,
        "size": len(content),
    }
