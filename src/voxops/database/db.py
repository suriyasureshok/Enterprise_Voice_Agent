"""
VOXOPS AI Gateway — Database Connection & Session Manager

Provides:
  - SQLAlchemy engine (SQLite by default, switchable to PostgreSQL via DATABASE_URL)
  - Session factory & context manager
  - Base declarative class shared by all ORM models
  - init_db() to create all tables on startup
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from configs.settings import settings
from configs.logging_config import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_connect_args = (
    {"check_same_thread": False}          # SQLite only
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=settings.debug,                   # SQL logging in debug mode
    future=True,
)

# Enable WAL mode for SQLite — better concurrent read/write performance
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


# ---------------------------------------------------------------------------
# Declarative base — imported by models.py
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI-compatible dependency that yields a database session
    and guarantees it is closed afterwards.

    Usage in a route::

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Context-manager version for use outside of FastAPI (scripts, tests, etc.)::

        with session_scope() as db:
            db.add(some_object)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Create all tables declared via Base.metadata.
    Call once on application startup.
    """
    # Import models so their metadata is registered before create_all
    from src.voxops.database import models  # noqa: F401

    log.info("Initialising database at {}", settings.database_url)
    Base.metadata.create_all(bind=engine)
    log.info("Database tables created / verified.")


def check_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        log.error("Database connection check failed: {}", exc)
        return False

