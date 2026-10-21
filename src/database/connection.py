"""
Database Connection and Session Management Module.
Supports any SQLAlchemy-compatible database (SQLite, PostgreSQL, MySQL, DuckDB).
Configured via src.config.DATABASE_URL.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.config import DATABASE_URL

connect_args = {}
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Define it in .env or the environment.")

    
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

Base = declarative_base()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager for database sessions with automatic commit/rollback."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
