"""
Fixture Loader Module.
Takes cleaned/transformed match payloads and persists them into the database
using FixtureRepository (idempotent upsert via SQLAlchemy).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.database import (
    STATUS_SUCCESS,
    CrawlStateRepository,
    FixtureRepository,
    get_session,
    FactMatch
)
from sqlalchemy import select
from src.utils.crawl_state import next_recrawl_time

def load_fixtures(
    fixtures: List[Dict[str, Any]],
    league_id: int,
    season: str,
    trigger_reason: Optional[str] = None,
    crawled_at: Optional[str] = None
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

    crawl_time = (
        datetime.fromisoformat(crawled_at) if crawled_at
        else datetime.now(timezone.utc)
    )

    with get_session() as session:

        ids = [f["match_id"] for f in fixtures]
        already_finished = set(
            session.scalars(
                select(FactMatch.match_id).where(
                    FactMatch.match_id.in_(ids),
                    FactMatch.status == "FINISHED",
                )
            ).all()
        )
        new_finished = sum(
            1 for f in fixtures
            if f["status"] == "FINISHED" and f["match_id"] not in already_finished
        )

        repo = FixtureRepository(session)
        loaded_count = repo.upsert_fixtures(
            fixtures=fixtures,
            league_id=league_id,
            season=season,
        )

        CrawlStateRepository(session).record_crawl(
            league_id=league_id,
            season=season,
            status=STATUS_SUCCESS,
            trigger_reason=trigger_reason,
            fixtures_count=new_finished,   
            next_recrawl_at=next_recrawl_time(fixtures, crawl_time),
            crawled_at=crawl_time,
        )

    return {
        "status": "success",
        "loaded_matches": loaded_count,
        "league_id": league_id,
        "season": season,
    }
