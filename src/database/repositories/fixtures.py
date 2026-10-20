"""
Fixtures Repository Module.
Handles database persistence and retrieval for fixtures, matches, and teams.
Fully decoupled from raw SQL queries using SQLAlchemy ORM.
"""

from datetime import date
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from ..models import DimTeam, FactMatch
    from .base import BaseRepository
except ImportError:
    from models import DimTeam, FactMatch
    from repositories.base import BaseRepository


class FixtureRepository(BaseRepository[FactMatch]):
    """Repository specialized in fixture and match data operations."""

    def __init__(self, session: Session):
        super().__init__(session, FactMatch)

    def upsert_teams_from_fixtures(self, fixtures: List[Dict[str, Any]]) -> int:
        """
        Extract unique home and away teams from transformed fixtures
        and upsert them into dim_teams.

        Args:
            fixtures: List of transformed fixture records.

        Returns:
            Number of unique teams upserted.
        """
        teams_map: Dict[str, str] = {}
        for item in fixtures:
            h_id = item.get("home_team_id")
            h_name = item.get("home_team")
            a_id = item.get("away_team_id")
            a_name = item.get("away_team")

            if h_id and h_name:
                teams_map[str(h_id)] = str(h_name)
            if a_id and a_name:
                teams_map[str(a_id)] = str(a_name)

        for t_id, t_name in teams_map.items():
            team_obj = DimTeam(team_id=t_id, team_name=t_name)
            self.session.merge(team_obj)

        self.session.flush()
        return len(teams_map)

    def upsert_fixtures(
        self,
        fixtures: List[Dict[str, Any]],
        league_id: int,
        season: str,
    ) -> int:
        """
        Persist transformed fixtures into fact_matches.
        Automatically updates dim_teams first to satisfy foreign key constraints.

        Args:
            fixtures: List of transformed fixture records.
            league_id: League identifier.
            season: Target season (e.g. '2025-2026').

        Returns:
            Number of fixture records upserted.
        """
        # 1. Ensure all referenced teams exist in dim_teams
        self.upsert_teams_from_fixtures(fixtures)

        # 2. Upsert each match into fact_matches
        count = 0
        for item in fixtures:
            m_date: Optional[date] = None
            if item.get("match_date"):
                try:
                    m_date = date.fromisoformat(str(item["match_date"]))
                except (ValueError, TypeError):
                    pass

            match_obj = FactMatch(
                match_id=str(item["match_id"]),
                league_id=league_id,
                season=season,
                round=str(item.get("round", "")),
                round_name=str(item.get("round_name", "")),
                stage=str(item.get("stage", "LEAGUE_STAGE")),
                match_date=m_date,
                match_time=item.get("match_time"),
                utc_time=item.get("utc_time"),
                home_team_id=str(item["home_team_id"]),
                away_team_id=str(item["away_team_id"]),
                status=str(item.get("status", "SCHEDULED")),
                score=item.get("score"),
                home_score=item.get("home_score"),
                away_score=item.get("away_score"),
                match_result=item.get("match_result"),
                home_points=item.get("home_points"),
                away_points=item.get("away_points"),
                goal_difference=item.get("goal_difference"),
                match_url=item.get("match_url"),
            )

            self.session.merge(match_obj)
            count += 1

        self.session.flush()
        return count

    def get_fixtures_by_league(
        self, league_id: int, season: str, stage: Optional[str] = None
    ) -> List[FactMatch]:
        """Query fixtures for a specific league and season, with optional stage filter."""
        stmt = (
            select(FactMatch)
            .where(FactMatch.league_id == league_id, FactMatch.season == season)
            .order_by(FactMatch.match_date, FactMatch.round)
        )
        if stage:
            stmt = stmt.where(FactMatch.stage == stage)

        return list(self.session.scalars(stmt).all())
