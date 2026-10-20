"""
Database initialization runner.
Creates all tables defined in models.py and seeds initial league data.

Usage:
    python -m src.database.init_db
"""

import logging

from src.database.connection import engine, get_session
from src.database.models import Base
from src.database.seeds.leagues import seed_leagues
from src.utils.logging_config import setup_logging
from src.config import DATABASE_URL, LOG_LEVEL

setup_logging(log_level=LOG_LEVEL)
logger = logging.getLogger("init_db")


def init_database() -> None:
    """Initialize database tables via SQLAlchemy metadata and run seeds."""
    logger.info("=" * 60)
    logger.info("Initializing database...")
    logger.info("  URL: %s", DATABASE_URL)
    logger.info("=" * 60)

    # 1. Create all tables defined in models.py
    Base.metadata.create_all(bind=engine)
    logger.info("[Schema] Tables created successfully.")

    # 2. Seed initial data (dim_leagues)
    with get_session() as session:
        seed_leagues(session)

    # 3. Log registered table names
    table_names = list(Base.metadata.tables.keys())
    logger.info("[Verify] Registered tables: %s", table_names)

    logger.info("Database initialization completed.")


if __name__ == "__main__":
    init_database()
