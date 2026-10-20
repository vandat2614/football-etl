"""Repository for the crawl_state_log table."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

try:
    from ..models import CrawlStateLog
    from .base import BaseRepository
except ImportError:
    from models import CrawlStateLog
    from repositories.base import BaseRepository


STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"


class CrawlStateRepository(BaseRepository[CrawlStateLog]):
    """Repository specialized in crawl state / crawl history operations."""

    def __init__(self, session: Session):
        super().__init__(session, CrawlStateLog)

    def record_crawl(
        self,
        league_id: int,
        season: str,
        status: str,
        trigger: str,
        fixtures_count: Optional[int] = None,
        next_recrawl_at: Optional[datetime] = None,
        error: Optional[str] = None,
        crawled_at: Optional[datetime] = None,
    ) -> CrawlStateLog:
        """
        Append one crawl run (successful or failed) to crawl_state_log.

        Args:
            league_id: League identifier.
            season: Target season (e.g. '2025-2026').
            status: STATUS_SUCCESS or STATUS_FAILED.
            trigger: Why the crawl ran (e.g. 'manual', 'refresh_7d').
            fixtures_count: Number of fixtures crawled.
            next_recrawl_at: When the league must be crawled again (UTC), or None.
            error: Error message for failed runs.
            crawled_at: Crawl completion time (defaults to now, UTC).

        Returns:
            The inserted log row.
        """
        row = CrawlStateLog(
            league_id=int(league_id),
            season=season,
            crawled_at=crawled_at or datetime.now(timezone.utc),
            trigger=trigger,
            status=status,
            fixtures_count=fixtures_count,
            next_recrawl_at=next_recrawl_at,
            error=error[:2000] if error else None,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_latest_success_by_league(self, season: str) -> Dict[int, CrawlStateLog]:
        """Latest SUCCESS row of every league in a season, as {league_id: row}."""
        latest = (
            select(
                CrawlStateLog.league_id.label("league_id"),
                func.max(CrawlStateLog.crawled_at).label("max_at"),
            )
            .where(CrawlStateLog.season == season, CrawlStateLog.status == STATUS_SUCCESS)
            .group_by(CrawlStateLog.league_id)
            .subquery()
        )
        stmt = (
            select(CrawlStateLog)
            .join(
                latest,
                and_(
                    CrawlStateLog.league_id == latest.c.league_id,
                    CrawlStateLog.crawled_at == latest.c.max_at,
                ),
            )
            .where(CrawlStateLog.season == season, CrawlStateLog.status == STATUS_SUCCESS)
        )
        return {row.league_id: row for row in self.session.scalars(stmt).all()}

    def get_history(
        self, league_id: int, season: str, limit: int = 50
    ) -> List[CrawlStateLog]:
        """Crawl history of one league and season, newest first."""
        stmt = (
            select(CrawlStateLog)
            .where(CrawlStateLog.league_id == league_id, CrawlStateLog.season == season)
            .order_by(CrawlStateLog.crawled_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())