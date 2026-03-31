"""SQLAlchemy database setup — supports SQLite (dev) and PostgreSQL (prod)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import Generator

from backend.config import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")
_engine_kwargs: dict = {"echo": False}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a DB session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables and add missing columns (SQLite only; PostgreSQL uses Alembic)."""
    Base.metadata.create_all(bind=engine)
    if _is_sqlite:
        _migrate_columns()


def _migrate_columns():
    """Add missing columns to existing tables (SQLite doesn't do this via create_all)."""
    import sqlalchemy
    inspector = sqlalchemy.inspect(engine)

    migrations = {
        "agents": {
            "role": "VARCHAR(100) DEFAULT ''",
            "bio": "TEXT DEFAULT ''",
            "workspace_id": "INTEGER REFERENCES workspaces(id)",
        },
        "tasks": {
            "workspace_id": "INTEGER REFERENCES workspaces(id)",
        },
        "crons": {
            "workspace_id": "INTEGER REFERENCES workspaces(id)",
        },
        "costs": {
            "workspace_id": "INTEGER REFERENCES workspaces(id)",
        },
        "journal_entries": {
            "workspace_id": "INTEGER REFERENCES workspaces(id)",
        },
        "alerts": {
            "workspace_id": "INTEGER REFERENCES workspaces(id)",
        },
        "users": {
            "is_superadmin": "BOOLEAN DEFAULT 0",
        },
    }

    with engine.connect() as conn:
        for table_name, columns in migrations.items():
            if not inspector.has_table(table_name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            for col_name, col_type in columns.items():
                if col_name not in existing:
                    conn.execute(sqlalchemy.text(
                        f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                    ))
                    conn.commit()

        # Seed default User and Workspace if they don't exist
        if inspector.has_table("users"):
            row = conn.execute(sqlalchemy.text("SELECT id FROM users WHERE id = 1")).fetchone()
            if not row:
                conn.execute(sqlalchemy.text(
                    "INSERT INTO users (id, telegram_id, name, onboarding_complete) "
                    "VALUES (1, 1080204489, 'Sviatoslav', 1)"
                ))
                conn.commit()

        # Seed superadmin flag
        if inspector.has_table("users"):
            conn.execute(sqlalchemy.text(
                "UPDATE users SET is_superadmin = 1 WHERE telegram_id = 1080204489"
            ))
            conn.commit()

        if inspector.has_table("workspaces"):
            row = conn.execute(sqlalchemy.text("SELECT id FROM workspaces WHERE id = 1")).fetchone()
            if not row:
                conn.execute(sqlalchemy.text(
                    "INSERT INTO workspaces (id, name, owner_id, tier, agent_limit) "
                    "VALUES (1, 'Default', 1, 'hobby', 3)"
                ))
                conn.commit()

        # Create agent_files table if missing (SQLite — Alembic handles PostgreSQL)
        if not inspector.has_table("agent_files"):
            conn.execute(sqlalchemy.text("""
                CREATE TABLE agent_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id INTEGER NOT NULL REFERENCES agents(id),
                    filename VARCHAR(255) NOT NULL,
                    content TEXT DEFAULT '',
                    size INTEGER DEFAULT 0,
                    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
                    updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(agent_id, filename, workspace_id)
                )
            """))
            conn.commit()

        # Backfill workspace_id=1 for all existing rows with NULL workspace_id
        for table_name in ["agents", "tasks", "crons", "costs", "journal_entries", "alerts"]:
            if inspector.has_table(table_name):
                conn.execute(sqlalchemy.text(
                    f"UPDATE {table_name} SET workspace_id = 1 WHERE workspace_id IS NULL"
                ))
                conn.commit()
