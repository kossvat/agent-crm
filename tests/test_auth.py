"""Tests for JWT auth, workspace resolution, and auth endpoints."""

import pytest
from backend.auth import create_access_token, create_workspace_token, decode_access_token


class TestJWT:
    def test_create_and_decode_token(self):
        token = create_access_token(1, 1)
        payload = decode_access_token(token)
        assert payload["user_id"] == 1
        assert payload["workspace_id"] == 1
        assert "exp" in payload

    def test_decode_invalid_token(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token("garbage.token.here")

    def test_decode_empty_token(self):
        with pytest.raises(ValueError):
            decode_access_token("")

    def test_decode_workspace_token_rejected_as_access_token(self):
        token = create_workspace_token(1)
        with pytest.raises(ValueError, match="not a user access token"):
            decode_access_token(token)


class TestAuthEndpoints:
    def test_me_with_jwt(self, client, auth_headers):
        resp = client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["telegram_id"] == 1080204489
        assert data["workspace"]["id"] == 1
        assert data["workspace"]["tier"] == "hobby"

    def test_me_without_auth(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_bad_token(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer bad"})
        assert resp.status_code == 401

    def test_me_with_workspace_token_returns_401(self, client):
        token = create_workspace_token(1)
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "not a user access token" in resp.json()["detail"]

    def test_onboarding_complete(self, client, auth_headers, db):
        from backend.models import User
        # Reset onboarding
        user = db.query(User).filter(User.id == 1).first()
        user.onboarding_complete = False
        db.commit()

        resp = client.patch("/api/auth/onboarding-complete", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify
        db.refresh(user)
        assert user.onboarding_complete is True

    def test_onboarding_can_be_reset(self, client, auth_headers, db):
        from backend.models import User

        user = db.query(User).filter(User.id == 1).first()
        user.onboarding_complete = True
        db.commit()

        resp = client.patch(
            "/api/auth/onboarding-complete",
            headers=auth_headers,
            json={"complete": False},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "onboarding_complete": False}

        db.refresh(user)
        assert user.onboarding_complete is False

    def test_workspace_owner_can_update_own_budget(self, client, other_auth_headers, db):
        from backend.models import Workspace

        resp = client.patch(
            "/api/auth/workspace/budget",
            headers=other_auth_headers,
            json={"monthly_budget": 250},
        )
        assert resp.status_code == 200
        assert resp.json()["monthly_budget"] == 250

        workspace = db.query(Workspace).filter(Workspace.id == 2).first()
        assert workspace.monthly_budget == 250

    def test_cross_workspace_token_rejected(self, client, cross_workspace_headers):
        resp = client.get("/api/auth/me", headers=cross_workspace_headers)
        assert resp.status_code == 401
        assert "workspace access" in resp.json()["detail"].lower()

    def test_agent_id_header_backward_compat(self, client):
        """X-Agent-Id from localhost should work and resolve to workspace_id=1.
        Note: TestClient doesn't set client.host to 127.0.0.1, so this tests
        that without local IP, X-Agent-Id alone is not enough (falls through to 401).
        In production, localhost requests with X-Agent-Id work correctly.
        """
        resp = client.get("/api/tasks", headers={"X-Agent-Id": "3"})
        # TestClient is not recognized as localhost → falls through to 401
        # This is correct security behavior: non-local X-Agent-Id is rejected
        assert resp.status_code == 401
