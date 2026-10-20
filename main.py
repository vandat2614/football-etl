"""
Entry point for all ETL consumers.

Usage:
    python main.py --service transform
    python main.py --service load
"""

import argparse
import logging
import signal
import sys

import src.config as config
from src.utils.logging_config import setup_logging

logger = logging.getLogger("main")


def _build_transform():
    from src.services.transform.service import FixtureTransformService
    return FixtureTransformService()


def _build_load():
    from src.services.load.service import FixtureLoadService  # adjust to your real path
    return FixtureLoadService()


# To add a new consumer later: write one builder and add one entry here.
SERVICES = {
    "transform": _build_transform,
    "load": _build_load,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an ETL consumer service.")
    parser.add_argument(
        "--service",
        required=True,
        choices=SERVICES.keys(),
        help="Which consumer to run",
    )
    args = parser.parse_args()

    setup_logging(log_level=config.LOG_LEVEL, log_file=config.LOG_FILE)
    logger.info("Starting '%s' service...", args.service)

    service = SERVICES[args.service]()

    def _shutdown(signum, _frame) -> None:
        logger.info("Received signal %s, stopping '%s' service...", signum, args.service)
        service.stop()

    # Graceful shutdown on Ctrl+C / docker stop
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        service.start()  # blocks until stop() is called
    except Exception:
        logger.exception("'%s' service crashed.", args.service)
        sys.exit(1)


if __name__ == "__main__":
    main()