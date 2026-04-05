"""Shared test fixtures for AgentCRM tests."""

import os
import pytest

# Force test database before importing app
os.environ["DATABASE_URL"] = "sqlite:///test_crm.db"
os.environ["DEV_MODE"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-bytes-long!!"
os.environ["BOT_TOKEN"] = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
os.environ["DISABLE_RATE_LIMIT"] = "true"
os.environ["REQUIRE_INVITE"] = "false"
os.environ["DISABLE_STARTUP_SYNC"] = "true"
os.environ["DISABLE_WATCHDOG"] = "true"

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import Base, engine, SessionLocal
from backend.models import User, Workspace, Agent, Task, TierType
from backend.auth import create_access_token


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create tables once for test session."""
    if os.path.exists("test_crm.db"):
        os.remove("test_crm.db")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Seed default user + workspace
    db = SessionLocal()
    user = User(id=1, telegram_id=1080204489, name="TestOwner", onboarding_complete=True)
    db.add(user)
    db.flush()
    ws = Workspace(id=1, name="TestWorkspace", owner_id=1, tier=TierType.hobby, agent_limit=3)
    db.add(ws)
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("test_crm.db"):
        os.remove("test_crm.db")


@pytest.fixture
def db():
    """Yield a DB session, rollback after test."""
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def owner_token():
    """JWT token for workspace owner (user_id=1, workspace_id=1)."""
    return create_access_token(1, 1)


@pytest.fixture
def other_user_token(db):
    """JWT token for a different user in workspace 2."""
    user2 = db.query(User).filter(User.id == 2).first()
    if not user2:
        user2 = User(id=2, telegram_id=999999, name="OtherUser", onboarding_complete=False)
        db.add(user2)
        db.flush()
        ws2 = Workspace(id=2, name="OtherWorkspace", owner_id=2, tier=TierType.hobby, agent_limit=3)
        db.add(ws2)
        db.commit()
    return create_access_token(2, 2)


@pytest.fixture
def auth_headers(owner_token):
    """Auth headers for owner."""
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture
def other_auth_headers(other_user_token):
    """Auth headers for another workspace owner."""
    return {"Authorization": f"Bearer {other_user_token}"}


@pytest.fixture
def cross_workspace_headers(db):
    """JWT for a user that does not own the requested workspace."""
    user3 = db.query(User).filter(User.id == 3).first()
    if not user3:
        user3 = User(id=3, telegram_id=333333, name="CrossWorkspaceUser", onboarding_complete=False)
        db.add(user3)
        db.flush()
        ws3 = Workspace(id=3, name="ThirdWorkspace", owner_id=3, tier=TierType.hobby, agent_limit=3)
        db.add(ws3)
        db.commit()
    token = create_access_token(3, 1)
    return {"Authorization": f"Bearer {token}"}
