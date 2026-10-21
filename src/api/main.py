import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from src.database import CrawlStateRepository, get_session
from src.database.models import DimLeague
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from src.database.models import CrawlStateLog, DimLeague, FactMatch

app = FastAPI(title="Football ETL API")

API_TOKEN = os.environ.get("API_TOKEN", "")
if not API_TOKEN:
    raise RuntimeError("API_TOKEN is not set. Define it in .env or the environment.")

def verify_token(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {API_TOKEN}"
    if not API_TOKEN or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/crawl-state", dependencies=[Depends(verify_token)])
def get_crawl_state(season: str = Query(...)):
    """Latest SUCCESS crawl state of every league in a season."""
    with get_session() as session:
        rows = CrawlStateRepository(session).get_latest_success_by_league(season)
        return [
            {
                "league_id": league_id,
                "crawled_at": row.crawled_at.isoformat(),
                "next_recrawl_at": row.next_recrawl_at.isoformat() if row.next_recrawl_at else None,
            }
            for league_id, row in rows.items()
        ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in [os.environ.get("WEB_ORIGIN", "")] if o],
    allow_methods=["GET"],
)


@app.get("/public/crawl-state")
def public_crawl_state(season: str = Query(...)):
    """Public, read-only crawl status of every league (no sensitive data)."""
    with get_session() as session:
        rows = CrawlStateRepository(session).get_latest_success_by_league(season)
        names = {l.league_id: l.league_name for l in session.scalars(select(DimLeague)).all()}
        return [
            {
                "league": names.get(lid, str(lid)),
                "fixtures_count": row.fixtures_count,
                "crawled_at": row.crawled_at.isoformat(),
                "next_recrawl_at": row.next_recrawl_at.isoformat() if row.next_recrawl_at else None,
            }
            for lid, row in rows.items()
        ]

@app.get("/public/stats")
def public_stats():
    """Public, read-only summary numbers for the landing page."""
    since = datetime.now(timezone.utc) - timedelta(days=7)
    with get_session() as session:
        total_matches = session.scalar(select(func.count()).select_from(FactMatch))
        leagues = session.scalar(select(func.count()).select_from(DimLeague))
        last_crawled = session.scalar(
            select(func.max(CrawlStateLog.crawled_at))
            .where(CrawlStateLog.status == "SUCCESS")
        )
        runs, ok = session.execute(
            select(
                func.count(),
                func.count().filter(CrawlStateLog.status == "SUCCESS"),
            ).where(CrawlStateLog.crawled_at >= since)
        ).one()
        return {
            "total_matches": total_matches,
            "leagues_tracked": leagues,
            "last_crawled_at": last_crawled.isoformat() if last_crawled else None,
            "crawl_runs_7d": runs,
            "success_rate_7d": round(ok / runs * 100, 1) if runs else None,
        }
# ---------------------------------------------------------------------------
# Data Explorer & Match Center Endpoints
# ---------------------------------------------------------------------------
import json
from pathlib import Path
from typing import Optional
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import aliased
from src.database.models import DimTeam
from src.config import LEAGUES_CONFIG_FILE

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


@app.get("/public/leagues")
def public_leagues():
    """List of all tracked leagues with available match counts and seasons."""
    with get_session() as session:
        db_leagues = session.scalars(select(DimLeague).order_by(DimLeague.league_name)).all()
        
        # If DB is not populated yet, fallback to leagues.json config
        if not db_leagues and LEAGUES_CONFIG_FILE.exists():
            with open(LEAGUES_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg_leagues = json.load(f)
            return [
                {
                    "league_id": lg.get("id"),
                    "league_name": lg.get("name"),
                    "country_code": lg.get("country_code", "UNK"),
                    "matches_count": 0,
                    "seasons": [],
                }
                for lg in cfg_leagues
            ]

        results = []
        for lg in db_leagues:
            count = session.scalar(
                select(func.count()).select_from(FactMatch).where(FactMatch.league_id == lg.league_id)
            ) or 0
            seasons = session.scalars(
                select(FactMatch.season)
                .where(FactMatch.league_id == lg.league_id)
                .distinct()
                .order_by(FactMatch.season.desc())
            ).all()
            results.append({
                "league_id": lg.league_id,
                "league_name": lg.league_name,
                "country_code": lg.country_code,
                "matches_count": count,
                "seasons": list(seasons),
            })
        return results


@app.get("/public/seasons")
def public_seasons():
    """List all available seasons recorded in the database."""
    with get_session() as session:
        seasons = session.scalars(
            select(FactMatch.season).distinct().order_by(FactMatch.season.desc())
        ).all()
        res = list(seasons)
        if not res:
            res = ["2026-2027", "2025-2026", "2024-2025", "2023-2024", "2022-2023"]
        return res


@app.get("/public/rounds")
def public_rounds(league_id: int = Query(...), season: str = Query(...)):
    """List distinct match rounds for a league and season."""
    with get_session() as session:
        rounds = session.scalars(
            select(FactMatch.round)
            .where(FactMatch.league_id == league_id, FactMatch.season == season)
            .distinct()
        ).all()
        
        def _sort_key(r):
            try:
                return (0, int(r))
            except (ValueError, TypeError):
                return (1, str(r))
                
        return sorted(list(rounds), key=_sort_key)


@app.get("/public/matches")
def public_matches(
    league_id: Optional[int] = Query(None),
    season: Optional[str] = Query(None),
    round: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    team: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Query football matches with filtering by league, season, round, status, and team."""
    HomeTeam = aliased(DimTeam)
    AwayTeam = aliased(DimTeam)

    stmt = (
        select(
            FactMatch,
            DimLeague.league_name,
            HomeTeam.team_name.label("home_name"),
            AwayTeam.team_name.label("away_name"),
        )
        .outerjoin(DimLeague, FactMatch.league_id == DimLeague.league_id)
        .outerjoin(HomeTeam, FactMatch.home_team_id == HomeTeam.team_id)
        .outerjoin(AwayTeam, FactMatch.away_team_id == AwayTeam.team_id)
    )

    count_stmt = select(func.count()).select_from(FactMatch)

    if league_id:
        stmt = stmt.where(FactMatch.league_id == league_id)
        count_stmt = count_stmt.where(FactMatch.league_id == league_id)
    if season:
        stmt = stmt.where(FactMatch.season == season)
        count_stmt = count_stmt.where(FactMatch.season == season)
    if round:
        stmt = stmt.where(FactMatch.round == round)
        count_stmt = count_stmt.where(FactMatch.round == round)
    if status:
        stmt = stmt.where(FactMatch.status == status.upper())
        count_stmt = count_stmt.where(FactMatch.status == status.upper())
    if date:
        stmt = stmt.where(FactMatch.match_date == date)
        count_stmt = count_stmt.where(FactMatch.match_date == date)
    if team:
        pattern = f"%{team.strip()}%"
        team_cond = (HomeTeam.team_name.ilike(pattern)) | (AwayTeam.team_name.ilike(pattern))
        stmt = stmt.where(team_cond)
        count_stmt = (
            count_stmt.outerjoin(HomeTeam, FactMatch.home_team_id == HomeTeam.team_id)
            .outerjoin(AwayTeam, FactMatch.away_team_id == AwayTeam.team_id)
            .where(team_cond)
        )

    with get_session() as session:
        total = session.scalar(count_stmt) or 0
        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(
                FactMatch.match_date.desc().nullslast(),
                FactMatch.match_time.desc().nullslast(),
                FactMatch.match_id,
            )
            .offset(offset)
            .limit(page_size)
        )
        rows = session.execute(stmt).all()

        items = []
        for match, l_name, h_name, a_name in rows:
            items.append({
                "match_id": match.match_id,
                "league_id": match.league_id,
                "league_name": l_name or f"League {match.league_id}",
                "season": match.season,
                "round": match.round,
                "round_name": match.round_name,
                "stage": match.stage,
                "match_date": match.match_date.isoformat() if match.match_date else None,
                "match_time": match.match_time,
                "utc_time": match.utc_time,
                "home_team_id": match.home_team_id,
                "home_team": h_name or match.home_team_id,
                "away_team_id": match.away_team_id,
                "away_team": a_name or match.away_team_id,
                "status": match.status,
                "score": match.score,
                "home_score": match.home_score,
                "away_score": match.away_score,
                "match_result": match.match_result,
                "home_points": match.home_points,
                "away_points": match.away_points,
                "goal_difference": match.goal_difference,
                "match_url": match.match_url,
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
            "matches": items,
        }


@app.get("/public/standings")
def public_standings(league_id: int = Query(...), season: str = Query(...)):
    """Calculate and return league standings table from finished match results."""
    HomeTeam = aliased(DimTeam)
    AwayTeam = aliased(DimTeam)

    stmt = (
        select(
            FactMatch,
            HomeTeam.team_name.label("home_name"),
            AwayTeam.team_name.label("away_name"),
        )
        .outerjoin(HomeTeam, FactMatch.home_team_id == HomeTeam.team_id)
        .outerjoin(AwayTeam, FactMatch.away_team_id == AwayTeam.team_id)
        .where(
            FactMatch.league_id == league_id,
            FactMatch.season == season,
            FactMatch.status == "FINISHED",
        )
        .order_by(FactMatch.match_date.asc().nullslast(), FactMatch.match_time.asc().nullslast())
    )

    with get_session() as session:
        matches = session.execute(stmt).all()
        teams: dict[str, dict] = {}

        for m, h_name, a_name in matches:
            home_id = m.home_team_id
            away_id = m.away_team_id

            if home_id not in teams:
                teams[home_id] = {
                    "team_id": home_id,
                    "team_name": h_name or home_id,
                    "played": 0, "won": 0, "drawn": 0, "lost": 0,
                    "gf": 0, "ga": 0, "gd": 0, "points": 0,
                    "form": [],
                }
            if away_id not in teams:
                teams[away_id] = {
                    "team_id": away_id,
                    "team_name": a_name or away_id,
                    "played": 0, "won": 0, "drawn": 0, "lost": 0,
                    "gf": 0, "ga": 0, "gd": 0, "points": 0,
                    "form": [],
                }

            if m.home_score is None or m.away_score is None:
                continue

            h = teams[home_id]
            a = teams[away_id]

            h["played"] += 1
            a["played"] += 1
            h["gf"] += m.home_score
            h["ga"] += m.away_score
            a["gf"] += m.away_score
            a["ga"] += m.home_score

            if m.home_score > m.away_score:
                h["won"] += 1
                h["points"] += 3
                h["form"].append("W")
                a["lost"] += 1
                a["form"].append("L")
            elif m.home_score < m.away_score:
                a["won"] += 1
                a["points"] += 3
                a["form"].append("W")
                h["lost"] += 1
                h["form"].append("L")
            else:
                h["drawn"] += 1
                h["points"] += 1
                h["form"].append("D")
                a["drawn"] += 1
                a["form"].append("D")

        table = list(teams.values())
        for t in table:
            t["gd"] = t["gf"] - t["ga"]
            t["form"] = t["form"][-5:]

        table.sort(key=lambda x: (-x["points"], -x["gd"], -x["gf"], x["team_name"].lower()))
        for idx, t in enumerate(table, start=1):
            t["rank"] = idx

        return table


@app.get("/data", response_class=HTMLResponse)
@app.get("/explorer", response_class=HTMLResponse)
@app.get("/matches", response_class=HTMLResponse)
def serve_data_explorer():
    """Serve the interactive football data explorer web page."""
    html_file = WEB_DIR / "data.html"
    if html_file.exists():
        return FileResponse(html_file, media_type="text/html")
    return HTMLResponse("<h2>Data explorer interface not found</h2>", status_code=404)
