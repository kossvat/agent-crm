"""SQLAlchemy database setup — synchronous SQLite for MVP."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import Generator

from backend.config import DATABASE_URL


engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
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
    """Create all tables and add missing columns."""
    Base.metadata.create_all(bind=engine)
    _migrate_columns()


def _migrate_columns():
    """Add missing columns to existing tables (SQLite doesn't do this via create_all)."""
    import sqlalchemy
    inspector = sqlalchemy.inspect(engine)

    migrations = {
        "agents": {
            "role": "VARCHAR(100) DEFAULT ''",
            "bio": "TEXT DEFAULT ''",
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
