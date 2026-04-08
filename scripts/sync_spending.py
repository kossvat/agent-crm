#!/usr/bin/env python3
"""
Sync spending data from local MagicBox spending.db → CRM prod via /api/ingest.

Usage:
    python3 scripts/sync_spending.py --url https://your-crm-domain.com --token TOKEN
    python3 scripts/sync_spending.py --url https://your-crm-domain.com --days 14

Auth: workspace connect token (--token or WORKSPACE_TOKEN env var).
State: tracks last sync in ~/.crm_sync_state.json to avoid re-sending.
Safe to run multiple times — ingest API does upsert (sums tokens/cost per agent+date+model).

Cron setup:
    # Sync spending every hour
    0 * * * * python3 /path/to/sync_spending.py --url https://your-crm-domain.com --token YOUR_TOKEN
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

STATE_FILE = Path.home() / ".crm_sync_state.json"
SPENDING_DB = Path.home() / "projects" / "spending-tracker" / "spending.db"
BATCH_SIZE = 200


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_records(db_path: Path, days: int, last_sync: str | None) -> list[dict]:
    """Read from spending.db, group by agent + date + model."""
    if not db_path.exists():
        print(f"ERROR: spending.db not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # Group by agent + date + model for efficient batching
    query = """
        SELECT agent, date, COALESCE(NULLIF(model, ''), 'unknown') as model,
               SUM(input_tokens) as input_tokens,
               SUM(output_tokens) as output_tokens,
               SUM(cost_total) as cost_usd
        FROM usage_log
        WHERE date >= ?
    """
    params: list = [cutoff_date]

    if last_sync:
        # Only records newer than last sync timestamp
        query += " AND REPLACE(REPLACE(timestamp, 'T', ' '), 'Z', '') > ?"
        params.append(last_sync)

    query += " GROUP BY agent, date, model"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    # Map spending.db agent names → CRM agent names (customize for your agents)
    AGENT_NAME_MAP = {}  # e.g. {"main": "MyAgent", "assistant": "Helper"}

    records = []
    for agent, date, model, input_t, output_t, cost in rows:
        mapped_name = AGENT_NAME_MAP.get(agent, agent) if agent else "unknown"
        records.append({
            "agent_name": mapped_name,
            "model": model or "unknown",
            "input_tokens": int(input_t or 0),
            "output_tokens": int(output_t or 0),
            "cost_usd": round(float(cost or 0), 6),
            "timestamp": f"{date}T12:00:00Z",
        })

    return records


def send_batch(url: str, token: str, records: list[dict]) -> dict:
    """POST a batch of records to /api/ingest."""
    payload = json.dumps({"records": records}).encode()
    req = Request(
        f"{url.rstrip('/')}/api/ingest",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Sync spending.db → CRM prod")
    parser.add_argument("--url", required=True, help="CRM base URL")
    parser.add_argument("--token", default=os.environ.get("WORKSPACE_TOKEN"), help="Workspace token")
    parser.add_argument("--days", type=int, default=7, help="Sync last N days (default: 7)")
    parser.add_argument("--db", type=str, default=str(SPENDING_DB), help="Path to spending.db")
    parser.add_argument("--full", action="store_true", help="Ignore last sync, re-send everything")
    args = parser.parse_args()

    if not args.token:
        print("ERROR: --token or WORKSPACE_TOKEN env var required", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    last_sync = None if args.full else state.get("last_sync")

    db_path = Path(args.db)
    records = get_records(db_path, args.days, last_sync)

    if not records:
        print("No new records to sync.")
        return

    print(f"Syncing {len(records)} aggregated records...")

    total_ingested = 0
    all_created = []

    # Send in batches
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        result = send_batch(args.url, args.token, batch)
        total_ingested += result.get("ingested", 0)
        all_created.extend(result.get("created_agents", []))
        print(f"  Batch {i // BATCH_SIZE + 1}: {result.get('ingested', 0)} ingested")

    # Update state
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    state["last_sync"] = now_str
    state["last_url"] = args.url
    state["last_count"] = total_ingested
    save_state(state)

    print(f"Done: {total_ingested} records ingested.")
    if all_created:
        print(f"New agents created: {', '.join(all_created)}")


if __name__ == "__main__":
    main()
