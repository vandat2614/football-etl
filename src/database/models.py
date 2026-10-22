"""
SQLAlchemy ORM models definition.
Defines DimLeague, DimTeam, and FactMatch using SQLAlchemy 2.0 DeclarativeBase.
"""

from datetime import date, datetime
from typing import Any, Optional
from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


class DimLeague(Base):
    """Dimension table for football leagues and tournaments."""
    __tablename__ = "dim_leagues"

    league_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    matches: Mapped[list["FactMatch"]] = relationship("FactMatch", back_populates="league")

    def __repr__(self) -> str:
        return f"<DimLeague(id={self.league_id}, name='{self.league_name}')>"


class DimTeam(Base):
    """Dimension table for football clubs and teams."""
    __tablename__ = "dim_teams"

    team_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    team_name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<DimTeam(id='{self.team_id}', name='{self.team_name}')>"


class FactMatch(Base):
    """Fact table for fixtures, match schedules, and completed results."""
    __tablename__ = "fact_matches"

    match_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("dim_leagues.league_id"), index=True, nullable=False)
    season: Mapped[str] = mapped_column(String(20), index=True, nullable=False)

    # Round & Stage Categorization
    round: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    round_name: Mapped[str] = mapped_column(String(100), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    # Schedules & Timestamps
    match_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    match_time: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    utc_time: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Participating Teams
    home_team_id: Mapped[str] = mapped_column(ForeignKey("dim_teams.team_id"), index=True, nullable=False)
    away_team_id: Mapped[str] = mapped_column(ForeignKey("dim_teams.team_id"), index=True, nullable=False)

    # Match Status & Scores
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    score: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    home_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    away_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    match_result: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)
    home_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    away_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    goal_difference: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Metadata
    match_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    league: Mapped["DimLeague"] = relationship("DimLeague", back_populates="matches")
    home_team: Mapped["DimTeam"] = relationship("DimTeam", foreign_keys=[home_team_id])
    away_team: Mapped["DimTeam"] = relationship("DimTeam", foreign_keys=[away_team_id])

    def __repr__(self) -> str:
        return f"<FactMatch(id='{self.match_id}', round='{self.round_name}', status='{self.status}')>"


class CrawlStateLog(Base):
    """Append-only log of crawl runs, one row per league crawl.
 
    The latest SUCCESS row of a (league_id, season) pair is the current crawl
    state used to decide when that league must be crawled again. All other
    rows form the crawl history.
    """
    __tablename__ = "crawl_state_log"
 
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("dim_leagues.league_id"), nullable=False)
    season: Mapped[str] = mapped_column(String(20), nullable=False)
 
    # When the crawl finished (timezone-aware, stored as UTC)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
 
    # SUCCESS | FAILED
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    fixtures_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
 
    # When this league must be crawled again: the end (max kickoff + buffer) of
    # the earliest pending match group. NULL if there are no pending groups.
    next_recrawl_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
 
    # Why this crawl ran: "manual", "never_crawled", "refresh_7d", "group_finished:<time>"
    trigger_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
 
    __table_args__ = (
        Index("ix_crawl_state_log_lookup", "league_id", "season", "status", "crawled_at"),
    )
 
    def __repr__(self) -> str:
        return (
            f"<CrawlStateLog(league_id={self.league_id}, season='{self.season}', "
            f"status='{self.status}', crawled_at='{self.crawled_at}')>"
        )