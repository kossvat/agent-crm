"""Unit tests for workspace owner auth and sensitive owner-only flows."""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.auth import create_access_token, get_current_user
from backend.models import User, Workspace, TierType
from backend.routers.auth_router import BudgetUpdateRequest, update_budget, generate_api_key
from backend.routers.connect import generate_connect_token, redeem_connect_token


def _request_with_token(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "client": ("127.0.0.1", 12345),
        }
    )


@pytest.fixture
def workspace_owner_user(db):
    user = db.query(User).filter(User.id == 2).first()
    if not user:
        user = User(id=2, telegram_id=999999, name="WorkspaceOwner", onboarding_complete=True)
        db.add(user)
        db.flush()
        db.add(Workspace(id=2, name="OwnerWorkspace", owner_id=2, tier=TierType.hobby, agent_limit=3))
        db.commit()
    return user


@pytest.fixture
def foreign_user(db):
    user = db.query(User).filter(User.id == 3).first()
    if not user:
        user = User(id=3, telegram_id=333333, name="ForeignUser", onboarding_complete=True)
        db.add(user)
        db.flush()
        db.add(Workspace(id=3, name="ForeignWorkspace", owner_id=3, tier=TierType.hobby, agent_limit=3))
        db.commit()
    return user


def test_workspace_owner_gets_full_access(workspace_owner_user):
    request = _request_with_token(create_access_token(workspace_owner_user.id, 2))

    user = get_current_user(request)

    assert user["workspace_id"] == 2
    assert user["is_workspace_owner"] is True
    assert user["full_access"] is True
    assert user["is_owner"] is False


def test_cross_workspace_token_is_rejected(foreign_user):
    request = _request_with_token(create_access_token(foreign_user.id, 1))

    with pytest.raises(HTTPException) as exc:
        get_current_user(request)

    assert exc.value.status_code == 401
    assert "workspace access" in exc.value.detail.lower()


def test_workspace_owner_can_update_budget(workspace_owner_user, db):
    user = get_current_user(_request_with_token(create_access_token(workspace_owner_user.id, 2)))

    resp = update_budget(BudgetUpdateRequest(monthly_budget=250), user=user, db=db)

    assert resp["ok"] is True
    assert resp["monthly_budget"] == 250
    workspace = db.query(Workspace).filter(Workspace.id == 2).first()
    assert workspace.monthly_budget == 250


def test_workspace_owner_can_generate_and_redeem_connect_token(workspace_owner_user, db):
    user = get_current_user(_request_with_token(create_access_token(workspace_owner_user.id, 2)))

    generated = generate_connect_token(user=user, db=db)
    redeemed = redeem_connect_token(generated.token, db=db)

    assert generated.connect_url.endswith(generated.token)
    assert redeemed.workspace_id == 2


def test_connect_token_generation_rejects_non_owner_context(db):
    with pytest.raises(HTTPException) as exc:
        generate_connect_token(
            user={"workspace_id": 1, "is_workspace_owner": False, "is_superadmin": False},
            db=db,
        )

    assert exc.value.status_code == 403


def test_api_key_generation_rejects_non_owner_context(db):
    with pytest.raises(HTTPException) as exc:
        generate_api_key(
            user={"workspace_id": 1, "is_workspace_owner": False, "is_superadmin": False},
            db=db,
        )

    assert exc.value.status_code == 403
