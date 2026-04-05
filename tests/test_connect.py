"""Tests for Connect API — magic link token generation and redemption."""

import pytest
from datetime import datetime, timezone, timedelta
from backend.models import ConnectToken


class TestGenerateConnectToken:
    def test_owner_can_generate(self, client, auth_headers):
        resp = client.post("/api/connect/generate", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "connect_url" in data
        assert "expires" in data
        assert data["connect_url"].endswith(data["token"])

    def test_workspace_owner_can_generate_for_own_workspace(self, client, other_auth_headers):
        resp = client.post("/api/connect/generate", headers=other_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["connect_url"].endswith(resp.json()["token"])

    def test_cross_workspace_token_cannot_generate(self, client, cross_workspace_headers):
        resp = client.post("/api/connect/generate", headers=cross_workspace_headers)
        assert resp.status_code == 401

    def test_no_auth_cannot_generate(self, client):
        resp = client.post("/api/connect/generate")
        assert resp.status_code == 401


class TestRedeemConnectToken:
    def test_redeem_valid_token(self, client, auth_headers):
        # Generate
        gen_resp = client.post("/api/connect/generate", headers=auth_headers)
        token = gen_resp.json()["token"]

        # Redeem (no auth needed)
        resp = client.get(f"/api/connect/{token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_id"] == 1
        assert "workspace_token" in data
        assert "workspace_name" in data

    def test_redeem_workspace_2_token(self, client, other_auth_headers):
        gen_resp = client.post("/api/connect/generate", headers=other_auth_headers)
        token = gen_resp.json()["token"]

        resp = client.get(f"/api/connect/{token}")
        assert resp.status_code == 200
        assert resp.json()["workspace_id"] == 2

    def test_redeem_invalid_token(self, client):
        resp = client.get("/api/connect/totally-invalid-token-here")
        assert resp.status_code == 404

    def test_redeem_used_token(self, client, auth_headers):
        # Generate and use
        gen_resp = client.post("/api/connect/generate", headers=auth_headers)
        token = gen_resp.json()["token"]
        client.get(f"/api/connect/{token}")

        # Try again
        resp = client.get(f"/api/connect/{token}")
        assert resp.status_code == 410
        assert "already used" in resp.json()["detail"]

    def test_redeem_expired_token(self, client, auth_headers, db):
        # Generate
        gen_resp = client.post("/api/connect/generate", headers=auth_headers)
        token = gen_resp.json()["token"]

        # Manually expire it
        ct = db.query(ConnectToken).filter(ConnectToken.token == token).first()
        ct.expires = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

        resp = client.get(f"/api/connect/{token}")
        assert resp.status_code == 410
        assert "expired" in resp.json()["detail"].lower()


class TestConnectStatus:
    def test_status_lists_active_tokens(self, client, auth_headers):
        # Generate 2 tokens
        client.post("/api/connect/generate", headers=auth_headers)
        client.post("/api/connect/generate", headers=auth_headers)

        resp = client.get("/api/connect/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        # All should be unused
        for t in data:
            assert t["used"] is False

    def test_status_excludes_used_tokens(self, client, auth_headers):
        # Generate and use
        gen_resp = client.post("/api/connect/generate", headers=auth_headers)
        token = gen_resp.json()["token"]
        client.get(f"/api/connect/{token}")

        resp = client.get("/api/connect/status", headers=auth_headers)
        tokens_in_status = [t["token"] for t in resp.json()]
        assert token not in tokens_in_status

    def test_status_requires_auth(self, client):
        resp = client.get("/api/connect/status")
        assert resp.status_code == 401
