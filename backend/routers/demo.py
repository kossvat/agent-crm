"""Demo data endpoints — no auth required.

Returns realistic fake data so unauthenticated browser visitors
can explore the UI without a Telegram account.
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter

router = APIRouter(prefix="/api/demo", tags=["demo"])

_now = datetime.now(timezone.utc)

AGENTS = [
    {
        "id": 901,
        "name": "Aria",
        "emoji": "🔬",
        "model": "claude-sonnet-4-6",
        "status": "active",
        "role": "researcher",
        "bio": "Deep-dives into topics, synthesises papers and produces briefs",
        "daily_cost": 3.20,
        "last_active": _now.isoformat(),
    },
    {
        "id": 902,
        "name": "Nova",
        "emoji": "💻",
        "model": "claude-opus-4-6",
        "status": "active",
        "role": "coder",
        "bio": "Writes, reviews and ships production code",
        "daily_cost": 5.10,
        "last_active": (_now - timedelta(minutes=12)).isoformat(),
    },
    {
        "id": 903,
        "name": "Atlas",
        "emoji": "✍️",
        "model": "claude-sonnet-4-6",
        "status": "idle",
        "role": "writer",
        "bio": "Drafts blog posts, newsletters and marketing copy",
        "daily_cost": 2.40,
        "last_active": (_now - timedelta(hours=2)).isoformat(),
    },
    {
        "id": 904,
        "name": "Pulse",
        "emoji": "📊",
        "model": "claude-haiku-4-5-20251001",
        "status": "active",
        "role": "analyst",
        "bio": "Crunches metrics, builds dashboards and spots trends",
        "daily_cost": 1.80,
        "last_active": (_now - timedelta(minutes=35)).isoformat(),
    },
]

TASKS = [
    # todo
    {"id": 801, "title": "Research competitor pricing pages", "description": "Collect pricing structures from top 5 competitors and summarise in a table", "status": "todo", "priority": "high", "agent_id": 901, "agent_name": "Aria", "agent_emoji": "🔬", "category": "business", "created": (_now - timedelta(hours=3)).isoformat()},
    {"id": 802, "title": "Draft launch blog post", "description": "Write a 1 200-word announcement post for the v2 release", "status": "todo", "priority": "medium", "agent_id": 903, "agent_name": "Atlas", "agent_emoji": "✍️", "category": "content", "created": (_now - timedelta(hours=5)).isoformat()},
    {"id": 803, "title": "Set up error-rate alert", "description": "Configure PagerDuty alert when 5xx rate exceeds 1 %", "status": "todo", "priority": "low", "agent_id": 904, "agent_name": "Pulse", "agent_emoji": "📊", "category": "system", "created": (_now - timedelta(days=1)).isoformat()},
    # in_progress
    {"id": 804, "title": "Implement OAuth2 PKCE flow", "description": "Add PKCE support to the existing OAuth2 integration", "status": "in_progress", "priority": "high", "agent_id": 902, "agent_name": "Nova", "agent_emoji": "💻", "category": "projects", "created": (_now - timedelta(hours=8)).isoformat()},
    {"id": 805, "title": "Analyse Q1 conversion funnel", "description": "Identify biggest drop-off points and recommend fixes", "status": "in_progress", "priority": "high", "agent_id": 904, "agent_name": "Pulse", "agent_emoji": "📊", "category": "business", "created": (_now - timedelta(hours=6)).isoformat()},
    {"id": 806, "title": "Write API reference docs", "description": "Document all public endpoints with examples", "status": "in_progress", "priority": "medium", "agent_id": 903, "agent_name": "Atlas", "agent_emoji": "✍️", "category": "content", "created": (_now - timedelta(days=2)).isoformat()},
    # done
    {"id": 807, "title": "Benchmark embedding models", "description": "Compare latency and quality of 4 embedding providers", "status": "done", "priority": "medium", "agent_id": 901, "agent_name": "Aria", "agent_emoji": "🔬", "category": "projects", "created": (_now - timedelta(days=3)).isoformat()},
    {"id": 808, "title": "Fix CSV export encoding bug", "description": "UTF-8 BOM was missing, causing Excel to mangle accented characters", "status": "done", "priority": "high", "agent_id": 902, "agent_name": "Nova", "agent_emoji": "💻", "category": "system", "created": (_now - timedelta(days=2)).isoformat()},
    {"id": 809, "title": "Create weekly KPI dashboard", "description": "Automated Grafana dashboard refreshing every Monday", "status": "done", "priority": "low", "agent_id": 904, "agent_name": "Pulse", "agent_emoji": "📊", "category": "business", "created": (_now - timedelta(days=4)).isoformat()},
    {"id": 810, "title": "Social media copy for Product Hunt", "description": "Wrote 10 tweet variants and a LinkedIn post for launch day", "status": "done", "priority": "medium", "agent_id": 903, "agent_name": "Atlas", "agent_emoji": "✍️", "category": "content", "created": (_now - timedelta(days=5)).isoformat()},
]


@router.get("/dashboard")
def demo_dashboard():
    active = [t for t in TASKS if t["status"] != "done"]
    done = [t for t in TASKS if t["status"] == "done"]
    total_cost = sum(a["daily_cost"] for a in AGENTS)
    return {
        "agents": AGENTS,
        "tasks_active": len(active),
        "tasks_done": len(done),
        "total_cost": round(total_cost, 2),
        "alerts_unread": 0,
    }


@router.get("/tasks")
def demo_tasks():
    return TASKS


@router.get("/agents")
def demo_agents():
    return AGENTS
