"""
ETL Pipeline Orchestrator / Scheduler.

Coordinates the Extract phase: reads league configurations, crawls fixtures
for each league, and publishes raw data to Kafka for downstream processing.

This script is designed to be triggered manually or by an external scheduler
(cron, GitHub Actions, Airflow, etc.).

Usage:
    python scheduler.py                         # crawl all leagues, current season
    python scheduler.py --season 2024-2025      # specific season
    python scheduler.py --league 47             # single league by ID
    python scheduler.py --dry-run               # crawl but do NOT publish to Kafka
    python scheduler.py --only-due              # crawl only leagues that are due
                                                #   (7 days passed, or a match group has finished)
"""

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import src.config as config
from src.utils.logging_config import setup_logging
from src.utils.crawl_state import due_reason, next_recrawl_time
from src.database import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    CrawlStateRepository,
    get_session,
)
from src.services.extract.crawler import extract_fixtures
from src.services.extract.publisher import publish_raw_fixtures

logger = logging.getLogger("scheduler")


def load_leagues(config_file: Path) -> List[Dict[str, Any]]:
    """Load league list from leagues.json config file."""
    if not config_file.exists():
        logger.error("Leagues config not found: %s", config_file)
        raise FileNotFoundError(f"Leagues config not found: {config_file}")

    with open(config_file, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    return data.get("leagues", [])


def league_id_of(league: Dict[str, Any]) -> Any:
    return league.get("id") or league.get("fotmob_id")


def crawl_league(
    league: Dict[str, Any],
    season: str,
    dry_run: bool = False,
) -> Optional[List[Dict[str, Any]]]:
    """
    Crawl fixtures for a single league and optionally publish to Kafka.

    Args:
        league: League config dict (must contain 'id' and 'name').
        season: Season string, e.g. '2025-2026'.
        dry_run: If True, skip Kafka publishing.

    Returns:
        The crawled fixtures, or None on failure.
    """
    league_id = league_id_of(league)
    league_name = league.get("name", f"League {league_id}")

    logger.info("Crawling [%s] season=%s ...", league_name, season)

    try:
        fixtures = extract_fixtures(league=league, season=season)
        logger.info("  -> Fetched %d matches.", len(fixtures))

        if not dry_run:
            publish_raw_fixtures(
                league_id=int(league_id),
                season=season,
                fixtures=fixtures,
            )
            logger.info("  -> Published to Kafka topic '%s'.", config.TOPIC_RAW_FIXTURES)
        else:
            logger.info("  -> [DRY RUN] Skipping Kafka publish.")

        return fixtures

    except Exception as exc:
        logger.error("  -> Failed to crawl [%s]: %s", league_name, exc)
        return None


def record_state(
    league_id: Any,
    season: str,
    status: str,
    fixtures: Optional[List[Dict[str, Any]]] = None,
    error: Optional[str] = None,
) -> bool:
    """Append a row to crawl_state_log. Returns False if the DB write fails."""
    now = datetime.now(timezone.utc)
    try:
        with get_session() as session:
            CrawlStateRepository(session).record_crawl(
                league_id=int(league_id),
                season=season,
                status=status,
                fixtures_count=len(fixtures) if fixtures is not None else None,
                next_recrawl_at=next_recrawl_time(fixtures, now) if fixtures else None,
                error=error,
                crawled_at=now,
            )
        return True
    except Exception as exc:
        logger.error("  -> Failed to record crawl state for league %s: %s", league_id, exc)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Football ETL Scheduler - triggers the Extract phase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--season",
        default=config.DEFAULT_SEASON,
        help=f"Target season (default: {config.DEFAULT_SEASON})",
    )
    parser.add_argument(
        "--league",
        type=int,
        default=None,
        help="Run for a single league ID only (default: all leagues)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Crawl data but do NOT publish to Kafka (crawl state is not recorded)",
    )
    parser.add_argument(
        "--only-due",
        action="store_true",
        help="Only crawl leagues that are due: 7 days since the last crawl, "
             "or a group of scheduled matches has finished",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between league crawls (default: 2.0)",
    )
    args = parser.parse_args()

    setup_logging(log_level=config.LOG_LEVEL, log_file=config.LOG_FILE)

    logger.info("=" * 60)
    logger.info("Football ETL Scheduler starting")
    logger.info("  Season   : %s", args.season)
    logger.info("  Dry run  : %s", args.dry_run)
    logger.info("  Only due : %s", args.only_due)
    logger.info("=" * 60)

    leagues = load_leagues(config.LEAGUES_CONFIG_FILE)

    if args.league is not None:
        leagues = [lg for lg in leagues if league_id_of(lg) == args.league]
        if not leagues:
            logger.error("No league found with ID=%d in config.", args.league)
            raise SystemExit(1)

    logger.info("Processing %d league(s)...", len(leagues))

    # Latest crawl state (latest SUCCESS row) of every league
    latest_success: Dict[int, Any] = {}
    if args.only_due:
        with get_session() as session:
            rows = CrawlStateRepository(session).get_latest_success_by_league(args.season)
            # Copy the values out before the session is closed
            latest_success = {
                lid: (row.crawled_at, row.next_recrawl_at) for lid, row in rows.items()
            }

    results = {"success": 0, "failed": 0, "skipped": 0, "total_fixtures": 0}
    crawled_any = False

    for league in leagues:
        league_id = league_id_of(league)
        league_name = league.get("name", f"League {league_id}")

        if args.only_due:
            last_at, next_at = latest_success.get(int(league_id), (None, None))
            reason = due_reason(last_at, next_at, datetime.now(timezone.utc))
            if reason is None:
                logger.info("Skip [%s]: not due yet.", league_name)
                results["skipped"] += 1
                continue
            logger.info("[%s] is due: %s", league_name, reason)

        if crawled_any:
            time.sleep(args.delay)
        crawled_any = True

        fixtures = crawl_league(league=league, season=args.season, dry_run=args.dry_run)

        if fixtures is None:
            results["failed"] += 1
            if not args.dry_run:
                record_state(
                    league_id, args.season, STATUS_FAILED,
                    error="crawl or publish failed",
                )
            continue

        results["success"] += 1
        results["total_fixtures"] += len(fixtures)

        # Crawl + publish succeeded -> log it (resets the 7-day counter and
        # stores the max kickoff time of the pending match groups)
        if not args.dry_run:
            if not record_state(league_id, args.season, STATUS_SUCCESS, fixtures=fixtures):
                # Published but the state was not saved -> the next run will crawl
                # this league again (safe because the load step upserts)
                results["success"] -= 1
                results["failed"] += 1

    logger.info("=" * 60)
    logger.info("Scheduler finished.")
    logger.info("  Leagues processed : %d", results["success"])
    logger.info("  Leagues failed    : %d", results["failed"])
    logger.info("  Leagues skipped   : %d", results["skipped"])
    logger.info("  Total fixtures    : %d", results["total_fixtures"])
    logger.info("=" * 60)

    if results["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()