"""Tests for tier-based agent limits."""

import pytest
from backend.models import Agent, Workspace


class TestTierLimits:
    def test_hobby_tier_limit_3(self, client, auth_headers, db):
        """Hobby tier should allow max 3 agents."""
        ws = db.query(Workspace).filter(Workspace.id == 1).first()
        ws.agent_limit = 3
        ws.tier = "hobby"
        db.commit()

        # Count existing agents
        existing = db.query(Agent).filter(Agent.workspace_id == 1).count()

        # Add agents up to limit
        created = []
        for i in range(3 - existing):
            resp = client.post("/api/agents", headers=auth_headers, json={
                "name": f"TierTestAgent{i}", "emoji": "🧪"
            })
            if resp.status_code == 201:
                created.append(resp.json()["id"])

        # Try to exceed limit
        resp = client.post("/api/agents", headers=auth_headers, json={
            "name": "OneMoreAgent", "emoji": "❌"
        })
        assert resp.status_code == 403
        assert "Agent limit reached" in resp.json()["detail"]

        # Cleanup
        for aid in created:
            db.query(Agent).filter(Agent.id == aid).delete()
        db.commit()

    def test_pro_tier_unlimited(self, client, auth_headers, db):
        """Pro tier should allow unlimited agents (-1)."""
        ws = db.query(Workspace).filter(Workspace.id == 1).first()
        original_limit = ws.agent_limit
        original_tier = ws.tier
        ws.agent_limit = -1
        ws.tier = "pro"
        db.commit()

        resp = client.post("/api/agents", headers=auth_headers, json={
            "name": "ProUnlimitedAgent", "emoji": "🚀"
        })
        assert resp.status_code == 201

        # Cleanup
        agent_id = resp.json()["id"]
        db.query(Agent).filter(Agent.id == agent_id).delete()
        ws.agent_limit = original_limit
        ws.tier = original_tier
        db.commit()

    def test_duplicate_agent_name_rejected(self, client, auth_headers, db):
        """Duplicate agent name in same workspace should be rejected."""
        # Create first
        resp1 = client.post("/api/agents", headers=auth_headers, json={
            "name": "DuplicateTest", "emoji": "🔁"
        })
        if resp1.status_code == 201:
            # Try duplicate
            resp2 = client.post("/api/agents", headers=auth_headers, json={
                "name": "DuplicateTest", "emoji": "🔁"
            })
            assert resp2.status_code == 409

            # Cleanup
            db.query(Agent).filter(Agent.id == resp1.json()["id"]).delete()
            db.commit()
