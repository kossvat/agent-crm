"""Tests for invite code system."""

import pytest
from backend.models import InviteCode
from datetime import datetime, timezone, timedelta


class TestInviteManagement:
    """Test invite CRUD (owner only)."""

    def test_create_invite(self, client, auth_headers, db):
        resp = client.post("/api/auth/invites", json={"max_uses": 5, "note": "test batch"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["code"]) == 8
        assert data["max_uses"] == 5
        assert data["note"] == "test batch"

    def test_create_invite_non_owner(self, client, other_auth_headers):
        resp = client.post("/api/auth/invites", json={}, headers=other_auth_headers)
        assert resp.status_code == 403

    def test_list_invites(self, client, auth_headers, db):
        # Create one first
        client.post("/api/auth/invites", json={"note": "list test"}, headers=auth_headers)
        resp = client.get("/api/auth/invites", headers=auth_headers)
        assert resp.status_code == 200
        invites = resp.json()
        assert len(invites) >= 1
        assert any(i["note"] == "list test" for i in invites)

    def test_list_invites_non_owner(self, client, other_auth_headers):
        resp = client.get("/api/auth/invites", headers=other_auth_headers)
        assert resp.status_code == 403

    def test_check_valid_invite(self, client, auth_headers, db):
        resp = client.post("/api/auth/invites", json={"max_uses": 1}, headers=auth_headers)
        code = resp.json()["code"]
        check = client.get(f"/api/auth/invites/check/{code}")
        assert check.status_code == 200
        assert check.json()["valid"] is True

    def test_check_invalid_invite(self, client):
        check = client.get("/api/auth/invites/check/FAKECODE")
        assert check.status_code == 200
        assert check.json()["valid"] is False

    def test_check_expired_invite(self, client, auth_headers, db):
        resp = client.post("/api/auth/invites", json={"expires_hours": 1}, headers=auth_headers)
        code = resp.json()["code"]
        # Manually expire it
        invite = db.query(InviteCode).filter(InviteCode.code == code).first()
        invite.expires = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        check = client.get(f"/api/auth/invites/check/{code}")
        assert check.json()["valid"] is False

    def test_check_exhausted_invite(self, client, auth_headers, db):
        resp = client.post("/api/auth/invites", json={"max_uses": 1}, headers=auth_headers)
        code = resp.json()["code"]
        invite = db.query(InviteCode).filter(InviteCode.code == code).first()
        invite.use_count = 1
        db.commit()
        check = client.get(f"/api/auth/invites/check/{code}")
        assert check.json()["valid"] is False
