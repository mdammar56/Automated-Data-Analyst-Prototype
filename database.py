"""
backend/database.py

PostgreSQL connection/session management. The application supports a
first-run setup wizard, so the SQLAlchemy engine is created lazily and can be
re-created once the user has supplied/tested connection details, rather than
being fixed at import time.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from backend.config import get_settings

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _build_url(host: str, port: int, user: str, password: str, database: str) -> str:
    # psycopg (v3) driver, credentials never logged or returned to the client.
    from urllib.parse import quote_plus

    return f"postgresql+psycopg://{user}:{quote_plus(password)}@{host}:{port}/{database}"


def build_admin_url(host: str, port: int, user: str, password: str) -> str:
    """URL pointing at the 'postgres' maintenance database, used to create
    a new database if it does not yet exist."""
    return _build_url(host, port, user, password, "postgres")


def init_engine(host: str, port: int, user: str, password: str, database: str) -> Engine:
    """(Re)initialize the global engine after a successful setup-wizard test."""
    global _engine, _SessionLocal
    url = _build_url(host, port, user, password, database)
    _engine = create_engine(url, pool_pre_ping=True, future=True, connect_args={"connect_timeout": 5})
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.has_database_name:
            raise RuntimeError(
                "No database configured yet. Complete the PostgreSQL setup wizard first."
            )
        init_engine(
            settings.database_host,
            settings.database_port,
            settings.database_user,
            settings.database_password,
            settings.database_name,
        )
    return _engine  # type: ignore[return-value]


def is_configured() -> bool:
    global _engine
    if _engine is not None:
        return True
    settings = get_settings()
    return bool(settings.has_database_name and settings.database_password)


def is_connected() -> bool:
    """Check if the currently configured database is reachable and accepting queries."""
    global _engine
    if _engine is not None:
        try:
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    settings = get_settings()
    if not (settings.has_database_name and settings.database_password):
        return False

    ok, _ = test_connection(
        settings.database_host,
        settings.database_port,
        settings.database_user,
        settings.database_password,
        settings.database_name,
    )
    return ok


def get_current_database_name() -> str:
    global _engine
    if _engine is not None:
        try:
            return str(_engine.url.database or "")
        except Exception:
            pass
    settings = get_settings()
    return settings.database_name or ""


@contextmanager
def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        get_engine()
    session: Session = _SessionLocal()  # type: ignore[misc]
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_connection(host: str, port: int, user: str, password: str, database: str) -> tuple[bool, str]:
    """Attempt a lightweight connection test without mutating global state."""
    try:
        url = _build_url(host, port, user, password, database)
        engine = create_engine(url, pool_pre_ping=True, future=True, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True, "Connection successful."
    except Exception as exc:  # noqa: BLE001 - surfaced as a user-facing message
        return False, str(exc)


def database_exists(host: str, port: int, user: str, password: str, database: str) -> bool:
    admin_url = build_admin_url(host, port, user, password)
    engine = create_engine(admin_url, pool_pre_ping=True, future=True, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database}
            )
            return result.first() is not None
    finally:
        engine.dispose()


def create_database(host: str, port: int, user: str, password: str, database: str) -> None:
    """Create the requested database from the admin connection. CREATE DATABASE
    cannot run inside a transaction block, so autocommit isolation is used."""
    admin_url = build_admin_url(host, port, user, password)
    engine = create_engine(admin_url, pool_pre_ping=True, future=True, connect_args={"connect_timeout": 5}, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            # Identifier cannot be parameterized; validate it defensively first.
            safe_name = _safe_identifier(database)
            conn.execute(text(f'CREATE DATABASE "{safe_name}"'))
    finally:
        engine.dispose()


def _safe_identifier(name: str) -> str:
    import re

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(
            "Database/table names must start with a letter or underscore and contain only "
            "letters, digits and underscores."
        )
    return name
