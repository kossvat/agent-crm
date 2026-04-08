"""Tests for workspace isolation — user A cannot see user B data."""

import pytest
from backend.models import Agent, Task


class TestWorkspaceIsolation:
    @pytest.fixture(autouse=True)
    def setup_agents(self, db):
        """Create agents in different workspaces."""
        # Workspace 1 agent
        if not db.query(Agent).filter(Agent.name == "WS1Bot", Agent.workspace_id == 1).first():
            db.add(Agent(name="WS1Bot", emoji="🤖", workspace_id=1))
        # Workspace 2 agent
        if not db.query(Agent).filter(Agent.name == "WS2Bot", Agent.workspace_id == 2).first():
            db.add(Agent(name="WS2Bot", emoji="👾", workspace_id=2))
        db.commit()

    def test_owner_sees_only_own_agents(self, client, auth_headers):
        resp = client.get("/api/agents", headers=auth_headers)
        assert resp.status_code == 200
        names = [a["name"] for a in resp.json()]
        assert "WS1Bot" in names
        assert "WS2Bot" not in names

    def test_other_user_sees_only_own_agents(self, client, other_auth_headers):
        resp = client.get("/api/agents", headers=other_auth_headers)
        assert resp.status_code == 200
        names = [a["name"] for a in resp.json()]
        assert "WS2Bot" in names
        assert "WS1Bot" not in names

    def test_owner_cannot_access_other_workspace_agent(self, client, auth_headers, db):
        ws2_agent = db.query(Agent).filter(Agent.name == "WS2Bot").first()
        if ws2_agent:
            resp = client.get(f"/api/agents/{ws2_agent.id}", headers=auth_headers)
            assert resp.status_code == 404

    def test_dashboard_scoped_to_workspace(self, client, auth_headers, other_auth_headers):
        resp1 = client.get("/api/dashboard", headers=auth_headers)
        resp2 = client.get("/api/dashboard", headers=other_auth_headers)
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # Different agent counts per workspace
        names1 = [a["name"] for a in resp1.json()["agents"]]
        names2 = [a["name"] for a in resp2.json()["agents"]]
        assert "WS2Bot" not in names1
        assert "WS1Bot" not in names2

    def test_tasks_scoped_to_workspace(self, client, auth_headers, other_auth_headers, db):
        # Create task in workspace 1
        resp = client.post("/api/tasks", headers=auth_headers, json={
            "title": "WS1 Task", "status": "todo"
        })
        assert resp.status_code == 201
        task_id = resp.json()["id"]

        # Other user should NOT see it
        resp2 = client.get("/api/tasks", headers=other_auth_headers)
        task_ids = [t["id"] for t in resp2.json()]
        assert task_id not in task_ids

        # Cleanup
        client.delete(f"/api/tasks/{task_id}", headers=auth_headers)
