"""Tests for Ingest API — remote agent usage data ingestion."""

import pytest
from backend.auth import create_workspace_token, decode_workspace_token
from backend.models import Agent, Cost


@pytest.fixture
def ws_token():
    """Valid workspace token for workspace 1."""
    return create_workspace_token(1, days=1)


@pytest.fixture
def ws_headers(ws_token):
    """Auth headers with workspace token."""
    return {"Authorization": f"Bearer {ws_token}"}


class TestWorkspaceToken:
    def test_create_and_decode(self):
        token = create_workspace_token(1, days=1)
        payload = decode_workspace_token(token)
        assert payload["workspace_id"] == 1

    def test_reject_user_token_as_workspace(self):
        """User JWT should not pass as workspace token."""
        from backend.auth import create_access_token
        user_token = create_access_token(1, 1)
        with pytest.raises(ValueError, match="Not a workspace token"):
            decode_workspace_token(user_token)

    def test_reject_garbage_token(self):
        with pytest.raises(ValueError):
            decode_workspace_token("garbage")


class TestIngestEndpoint:
    def test_ingest_single_record(self, client, ws_headers, db):
        resp = client.post("/api/ingest", headers=ws_headers, json={
            "records": [{
                "agent_name": "ingest-test-bot",
                "model": "claude-opus-4-6",
                "input_tokens": 1000,
                "output_tokens": 500,
                "cost_usd": 0.10,
                "timestamp": "2026-03-29T04:00:00Z",
            }]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ingested"] == 1

        # Verify in DB
        agent = db.query(Agent).filter(Agent.name == "ingest-test-bot", Agent.workspace_id == 1).first()
        assert agent is not None
        cost = db.query(Cost).filter(Cost.agent_id == agent.id).first()
        assert cost is not None
        assert cost.cost_usd == pytest.approx(0.10)

    def test_ingest_creates_missing_agent(self, client, ws_headers, db):
        resp = client.post("/api/ingest", headers=ws_headers, json={
            "records": [{
                "agent_name": "brand-new-agent",
                "model": "gpt-5",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.01,
            }]
        })
        assert resp.status_code == 200
        assert "brand-new-agent" in resp.json()["created_agents"]

        agent = db.query(Agent).filter(Agent.name == "brand-new-agent", Agent.workspace_id == 1).first()
        assert agent is not None

    def test_ingest_upsert_cost(self, client, ws_headers, db):
        """Same agent+date+model should accumulate, not duplicate."""
        payload = {
            "records": [{
                "agent_name": "upsert-bot",
                "model": "claude-sonnet",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.05,
                "timestamp": "2026-01-15T12:00:00Z",
            }]
        }
        # First ingest
        client.post("/api/ingest", headers=ws_headers, json=payload)
        # Second ingest — same day, same model
        client.post("/api/ingest", headers=ws_headers, json=payload)

        agent = db.query(Agent).filter(Agent.name == "upsert-bot", Agent.workspace_id == 1).first()
        costs = db.query(Cost).filter(
            Cost.agent_id == agent.id,
            Cost.model == "claude-sonnet",
        ).all()
        # Should be exactly 1 row, with accumulated values
        assert len(costs) == 1
        assert costs[0].input_tokens == 200
        assert costs[0].cost_usd == pytest.approx(0.10)

    def test_ingest_unauthorized(self, client):
        resp = client.post("/api/ingest", json={"records": []})
        assert resp.status_code == 401

    def test_ingest_invalid_token(self, client):
        resp = client.post("/api/ingest",
            headers={"Authorization": "Bearer bad-token"},
            json={"records": []})
        assert resp.status_code == 401

    def test_ingest_empty_records(self, client, ws_headers):
        resp = client.post("/api/ingest", headers=ws_headers, json={"records": []})
        assert resp.status_code == 200
        assert resp.json()["ingested"] == 0

    def test_ingest_batch(self, client, ws_headers):
        resp = client.post("/api/ingest", headers=ws_headers, json={
            "records": [
                {"agent_name": "batch-agent-1", "model": "m1", "cost_usd": 0.01},
                {"agent_name": "batch-agent-2", "model": "m2", "cost_usd": 0.02},
                {"agent_name": "batch-agent-3", "model": "m3", "cost_usd": 0.03},
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ingested"] == 3
        assert len(data["created_agents"]) == 3

    def test_ingest_workspace_isolation(self, client, db):
        """Workspace 2 token should not see workspace 1 data."""
        ws2_token = create_workspace_token(2, days=1)
        headers = {"Authorization": f"Bearer {ws2_token}"}

        resp = client.post("/api/ingest", headers=headers, json={
            "records": [{
                "agent_name": "ws2-only-agent",
                "model": "test",
                "cost_usd": 0.01,
            }]
        })
        assert resp.status_code == 200

        # Agent should be in workspace 2, not 1
        agent_ws1 = db.query(Agent).filter(
            Agent.name == "ws2-only-agent", Agent.workspace_id == 1
        ).first()
        agent_ws2 = db.query(Agent).filter(
            Agent.name == "ws2-only-agent", Agent.workspace_id == 2
        ).first()
        assert agent_ws1 is None
        assert agent_ws2 is not None
