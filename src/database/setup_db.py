"""
One-shot database setup: create tables, seed leagues, import historical data.

Usage:
    python -m src.database.setup_db                  # tables + seed + import
    python -m src.database.setup_db --reset          # drop everything first (asks to confirm)
    python -m src.database.setup_db --reset --yes    # same, without the prompt
    python -m src.database.setup_db --skip-import    # tables + seed only
"""

import argparse
import logging
from pathlib import Path

from src.config import LOG_LEVEL
from src.database.connection import engine
from src.database.import_history import import_history
from src.database.init_db import init_database
from src.database.models import Base
from src.utils.logging_config import setup_logging

logger = logging.getLogger("setup_db")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up the database from scratch")
    parser.add_argument("--reset", action="store_true", help="Drop all tables first (destroys all data)")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt for --reset")
    parser.add_argument("--skip-import", action="store_true", help="Do not import historical data")
    parser.add_argument("--data-dir", default="data/raw")
    parser.add_argument("--max-season", default="2025-2026", help="Maximum season to import")
    args = parser.parse_args()
    setup_logging(log_level=LOG_LEVEL)

    if args.reset:
        if not args.yes:
            target = engine.url.render_as_string(hide_password=True)
            answer = input(f"This will DELETE ALL DATA in {target}\nType 'reset' to continue: ")
            if answer.strip() != "reset":
                logger.info("Aborted.")
                return
        Base.metadata.drop_all(bind=engine)
        logger.info("[Reset] All tables dropped.")

    init_database()

    if args.skip_import:
        logger.info("Skipping history import.")
        return

    ok, failed = import_history(Path(args.data_dir), max_season=args.max_season)
    logger.info("History import finished: files ok=%d, failed=%d", ok, failed)


if __name__ == "__main__":
    main()