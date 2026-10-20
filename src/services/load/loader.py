"""
Fixture Loader Module.
Takes cleaned/transformed match payloads and persists them into the database
using FixtureRepository (idempotent upsert via SQLAlchemy).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from src.database import (
    STATUS_SUCCESS,
    CrawlStateRepository,
    FixtureRepository,
    get_session,
)
from src.utils.crawl_state import next_recrawl_time

def load_fixtures(
    fixtures: List[Dict[str, Any]],
    league_id: int,
    season: str
) -> Dict[str, Any]:
    """
    Persist transformed fixture records into database using SQLAlchemy ORM.

    Args:
        fixtures: List of cleaned match dictionaries from the Transform phase.
        league_id: Identifier of the tournament.
        season: Target season string (e.g. '2025-2026').

    Returns:
        Summary dict containing execution metrics.
    """
    if not fixtures:
        return {"loaded_matches": 0, "status": "skipped_empty"}

    with get_session() as session:
        repo = FixtureRepository(session)
        loaded_count = repo.upsert_fixtures(
            fixtures=fixtures,
            league_id=league_id,
            season=season,
        )

        now = datetime.now(timezone.utc)
        CrawlStateRepository(session).record_crawl(
            league_id=league_id,
            season=season,
            status=STATUS_SUCCESS,
            fixtures_count=len(fixtures),
            next_recrawl_at=next_recrawl_time(fixtures, now),
            crawled_at=now,
        )

    return {
        "status": "success",
        "loaded_matches": loaded_count,
        "league_id": league_id,
        "season": season,
    }
