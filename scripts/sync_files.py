#!/usr/bin/env python3
"""Sync agent files (SOUL.md, IDENTITY.md, MEMORY.md) from local OpenClaw to remote AgentCRM.

Usage:
    python3 scripts/sync_files.py --url https://your-crm-domain.com --token TOKEN
    WORKSPACE_TOKEN=TOKEN python3 scripts/sync_files.py --url https://your-crm-domain.com

The script reads files from ~/.openclaw/<workspace>/ and POSTs them to /api/files/sync.
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

# Default agent → workspace directory mapping (customize for your agents)
# Or pass --agents "Name:workspace-dir,Name2:workspace-dir2" on CLI
AGENTS = {}  # e.g. {"MyAgent": "workspace", "Helper": "workspace-helper"}

FILES = ["SOUL.md", "IDENTITY.md", "MEMORY.md"]
OPENCLAW_DIR = Path.home() / ".openclaw"


def collect_files(agents: dict[str, str], openclaw_dir: Path) -> list[dict]:
    """Read files from local filesystem."""
    items = []
    for agent_name, workspace_dir in agents.items():
        ws_path = openclaw_dir / workspace_dir
        if not ws_path.exists():
            print(f"  SKIP {agent_name}: {ws_path} not found")
            continue
        for filename in FILES:
            filepath = ws_path / filename
            if filepath.exists():
                content = filepath.read_text(encoding="utf-8", errors="replace")
                items.append({
                    "agent_name": agent_name,
                    "filename": filename,
                    "content": content,
                })
                print(f"  READ {agent_name}/{filename} ({len(content)} bytes)")
            else:
                print(f"  SKIP {agent_name}/{filename}: not found")
    return items


def sync(url: str, token: str, files: list[dict]) -> None:
    """POST files to /api/files/sync."""
    endpoint = url.rstrip("/") + "/api/files/sync"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(endpoint, json={"files": files}, headers=headers, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n✅ Synced {data['synced']} files")
        if data.get("created_agents"):
            print(f"   Created agents: {', '.join(data['created_agents'])}")
    else:
        print(f"\n❌ Sync failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Sync agent files to AgentCRM")
    parser.add_argument("--url", required=True, help="AgentCRM base URL (e.g. https://your-crm-domain.com)")
    parser.add_argument("--token", default=None, help="Workspace token (or set WORKSPACE_TOKEN env)")
    parser.add_argument("--openclaw-dir", default=str(OPENCLAW_DIR), help="OpenClaw directory")
    parser.add_argument("--agents", default=None,
                        help="Override agents as 'Name:workspace,Name2:workspace2'")
    parser.add_argument("--dry-run", action="store_true", help="Collect files but don't send")
    args = parser.parse_args()

    token = args.token or os.environ.get("WORKSPACE_TOKEN", "")
    if not token and not args.dry_run:
        print("ERROR: --token or WORKSPACE_TOKEN env required", file=sys.stderr)
        sys.exit(1)

    # Parse agent overrides
    agents = AGENTS
    if args.agents:
        agents = {}
        for pair in args.agents.split(","):
            name, ws = pair.strip().split(":")
            agents[name.strip()] = ws.strip()

    openclaw_dir = Path(args.openclaw_dir)
    if not openclaw_dir.exists():
        print(f"ERROR: OpenClaw directory not found: {openclaw_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Collecting files from {openclaw_dir}...")
    files = collect_files(agents, openclaw_dir)

    if not files:
        print("No files found to sync.")
        sys.exit(0)

    if args.dry_run:
        print(f"\n[DRY RUN] Would sync {len(files)} files to {args.url}")
        return

    print(f"\nSyncing {len(files)} files to {args.url}...")
    sync(args.url, token, files)


if __name__ == "__main__":
    main()
