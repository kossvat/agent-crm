#!/usr/bin/env python3
"""AgentCRM MCP Server — JSON-RPC 2.0 over stdio.

Zero dependencies beyond Python 3.10+ stdlib + requests.
Wraps the AgentCRM REST API as MCP tools.

Usage:
    python3 server.py                          # uses ~/.agentcrm/config.json
    AGENTCRM_URL=http://... AGENTCRM_API_KEY=crm_... python3 server.py

mcporter config:
    mcporter config add agentcrm --stdio "python3 /path/to/server.py"
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("Error: 'requests' required. pip install requests", file=sys.stderr)
    sys.exit(1)

# --- Config ---

CONFIG_FILE = Path.home() / ".agentcrm" / "config.json"


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def _get_api_key() -> str:
    cfg = _load_config()
    return os.environ.get("AGENTCRM_API_KEY") or cfg.get("api_key", "")


def _get_base_url() -> str:
    cfg = _load_config()
    return os.environ.get("AGENTCRM_URL") or cfg.get("url", "https://myaiagentscrm.com")


def _api(method: str, path: str, **kwargs) -> dict:
    """Make authenticated API request, return parsed JSON."""
    url = f"{_get_base_url()}{path}"
    headers = {"X-Api-Key": _get_api_key()}
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp.json()


# --- MCP Tool Definitions ---

TOOLS = [
    {
        "name": "agents_list",
        "description": "List all agents in the CRM workspace",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "task_list",
        "description": "List tasks, optionally filtered by status or agent",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["todo", "in_progress", "done"], "description": "Filter by status"},
                "agent_id": {"type": "integer", "description": "Filter by agent ID"},
            },
        },
    },
    {
        "name": "task_create",
        "description": "Create a new task",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task description"},
                "agent_id": {"type": "integer", "description": "Assign to agent (ID)"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["title"],
        },
    },
    {
        "name": "task_update",
        "description": "Update a task's status or title",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Task ID"},
                "status": {"type": "string", "enum": ["todo", "in_progress", "done"]},
                "title": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "journal_add",
        "description": "Add a journal entry",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Entry content"},
                "agent_id": {"type": "integer", "description": "Agent ID"},
                "date": {"type": "string", "description": "Date YYYY-MM-DD (default: today)"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "alert_send",
        "description": "Send an alert notification",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Alert message"},
                "type": {"type": "string", "enum": ["info", "warning", "error"]},
                "agent_id": {"type": "integer"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "costs_summary",
        "description": "Get spending summary per agent",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
        },
    },
    {
        "name": "commands_pending",
        "description": "List pending commands from CRM",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]

# --- Tool Handlers ---


def handle_agents_list(_params: dict) -> Any:
    return _api("GET", "/api/agents")


def handle_task_list(params: dict) -> Any:
    query = {}
    if params.get("status"):
        query["status"] = params["status"]
    if params.get("agent_id"):
        query["agent_id"] = params["agent_id"]
    return _api("GET", "/api/tasks", params=query)


def handle_task_create(params: dict) -> Any:
    payload = {"title": params["title"], "status": "todo"}
    if params.get("description"):
        payload["description"] = params["description"]
    if params.get("agent_id"):
        payload["agent_id"] = params["agent_id"]
    if params.get("priority"):
        payload["priority"] = params["priority"]
    return _api("POST", "/api/tasks", json=payload)


def handle_task_update(params: dict) -> Any:
    task_id = params.pop("id")
    return _api("PATCH", f"/api/tasks/{task_id}", json=params)


def handle_journal_add(params: dict) -> Any:
    from datetime import date as _date
    payload = {
        "content": params["content"],
        "date": params.get("date") or _date.today().isoformat(),
        "source": "mcp",
    }
    if params.get("agent_id"):
        payload["agent_id"] = params["agent_id"]
    return _api("POST", "/api/journal", json=payload)


def handle_alert_send(params: dict) -> Any:
    payload = {"message": params["message"], "type": params.get("type", "info")}
    if params.get("agent_id"):
        payload["agent_id"] = params["agent_id"]
    return _api("POST", "/api/alerts", json=payload)


def handle_costs_summary(params: dict) -> Any:
    query = {}
    if params.get("date_from"):
        query["date_from"] = params["date_from"]
    if params.get("date_to"):
        query["date_to"] = params["date_to"]
    return _api("GET", "/api/costs/summary", params=query)


def handle_commands_pending(_params: dict) -> Any:
    return _api("GET", "/api/commands/pending")


HANDLERS = {
    "agents_list": handle_agents_list,
    "task_list": handle_task_list,
    "task_create": handle_task_create,
    "task_update": handle_task_update,
    "journal_add": handle_journal_add,
    "alert_send": handle_alert_send,
    "costs_summary": handle_costs_summary,
    "commands_pending": handle_commands_pending,
}

# --- JSON-RPC / MCP Protocol ---

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "agentcrm"
SERVER_VERSION = "1.0.0"


def _jsonrpc_response(id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _jsonrpc_error(id: Any, code: int, message: str, data: Any = None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id, "error": err}


def handle_request(msg: dict) -> dict | None:
    """Process a single JSON-RPC request."""
    method = msg.get("method", "")
    params = msg.get("params", {})
    msg_id = msg.get("id")

    # --- MCP lifecycle ---
    if method == "initialize":
        return _jsonrpc_response(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    if method == "notifications/initialized":
        return None  # notification, no response

    if method == "ping":
        return _jsonrpc_response(msg_id, {})

    # --- Tools ---
    if method == "tools/list":
        return _jsonrpc_response(msg_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        handler = HANDLERS.get(tool_name)
        if not handler:
            return _jsonrpc_error(msg_id, -32602, f"Unknown tool: {tool_name}")

        try:
            result = handler(arguments)
            text = json.dumps(result, indent=2, default=str)
            return _jsonrpc_response(msg_id, {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            })
        except requests.HTTPError as e:
            return _jsonrpc_response(msg_id, {
                "content": [{"type": "text", "text": f"API error: {e.response.status_code} {e.response.text[:500]}"}],
                "isError": True,
            })
        except Exception as e:
            return _jsonrpc_response(msg_id, {
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "isError": True,
            })

    # Unknown method
    if msg_id is not None:
        return _jsonrpc_error(msg_id, -32601, f"Method not found: {method}")
    return None  # notification for unknown method — ignore


def main():
    """MCP stdio transport: read JSON-RPC from stdin, write to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            resp = _jsonrpc_error(None, -32700, "Parse error")
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        response = handle_request(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
