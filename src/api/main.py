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
from src.services.extract.publisher import publish_raw_fixtures
from typing import Any, Dict, List, Optional



app = FastAPI(title="Football ETL API")
@app.get("/public/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url="/public/openapi.json",
        title="Football ETL API - Swagger UI",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

@app.get("/public/openapi.json", include_in_schema=False)
async def get_public_openapi():
    from fastapi.responses import JSONResponse
    return JSONResponse(app.openapi())


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

if (WEB_DIR / "images").exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/images", StaticFiles(directory=str(WEB_DIR / "images")), name="images")


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
    """List all available seasons recorded in the database, covering 2010-2011 to 2026-2027."""
    with get_session() as session:
        db_seasons = list(session.scalars(
            select(FactMatch.season).distinct().order_by(FactMatch.season.desc())
        ).all())
        full_range = [f"{y}-{y+1}" for y in range(2026, 2009, -1)]
        # Merge all seasons and maintain descending order
        merged = sorted(set(db_seasons + full_range), reverse=True)
        return merged


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


@app.get("/", response_class=HTMLResponse)
@app.get("/data", response_class=HTMLResponse)
@app.get("/explorer", response_class=HTMLResponse)
@app.get("/matches", response_class=HTMLResponse)
def serve_data_explorer():
    """Serve the interactive football data explorer web page as main application."""
    html_file = WEB_DIR / "data.html"
    if not html_file.exists():
        html_file = WEB_DIR / "index.html"
    if html_file.exists():
        return FileResponse(html_file, media_type="text/html")
    return HTMLResponse("<h2>Data explorer interface not found</h2>", status_code=404)


@app.get("/architecture", response_class=HTMLResponse)
def serve_architecture():
    """Serve the architecture blueprint and event-driven pipeline visualizer."""
    html_file = WEB_DIR / "architecture.html"
    if not html_file.exists():
        html_file = WEB_DIR / "index.html"
    if html_file.exists():
        return FileResponse(html_file, media_type="text/html")
    return HTMLResponse("<h2>Architecture blueprint not found</h2>", status_code=404)


COMMON_H2H_ALIASES = {
    "barca": "Barcelona",
    "barcelona": "Barcelona",
    "mu": "Manchester United",
    "man utd": "Manchester United",
    "man united": "Manchester United",
    "man city": "Manchester City",
    "mc": "Manchester City",
    "chelsea": "Chelsea",
    "arsenal": "Arsenal",
    "liverpool": "Liverpool",
    "spurs": "Tottenham Hotspur",
    "tottenham": "Tottenham Hotspur",
    "psg": "Paris Saint-Germain",
    "dortmund": "Borussia Dortmund",
    "bvb": "Borussia Dortmund",
    "bayern": "Bayern München",
    "munich": "Bayern München",
    "inter": "Inter",
    "inter milan": "Inter",
    "milan": "AC Milan",
    "ac milan": "AC Milan",
    "juve": "Juventus",
    "juventus": "Juventus",
    "atletico": "Atlético Madrid",
    "real": "Real Madrid",
    "leverkusen": "Bayer Leverkusen",
    "al nassr": "Al Nassr FC",
    "al hilal": "Al Hilal",
    "inter miami": "Inter Miami CF",
}


@app.get("/public/teams")
def public_teams(
    query: Optional[str] = Query(None),
    league_id: Optional[int] = Query(None),
    limit: int = Query(5000, ge=1, le=10000),
):
    """List available clubs with optional search or league filter for H2H."""
    with get_session() as session:
        stmt = select(DimTeam)
        if league_id:
            stmt = stmt.where(
                (DimTeam.team_id.in_(
                    select(FactMatch.home_team_id)
                    .where(FactMatch.league_id == league_id)
                    .distinct()
                )) |
                (DimTeam.team_id.in_(
                    select(FactMatch.away_team_id)
                    .where(FactMatch.league_id == league_id)
                    .distinct()
                ))
            )
        if query:
            clean_q = query.strip()
            alias_target = COMMON_H2H_ALIASES.get(clean_q.lower(), clean_q)
            stmt = stmt.where(
                (DimTeam.team_name.ilike(f"%{clean_q}%")) |
                (DimTeam.team_name.ilike(f"%{alias_target}%"))
            )
        stmt = stmt.order_by(DimTeam.team_name.asc()).limit(limit)
        teams = session.scalars(stmt).all()
        return [{"team_id": t.team_id, "team_name": t.team_name} for t in teams]

@app.get("/public/h2h")
def public_h2h(
    team1: str = Query(..., description="First team ID or name"),
    team2: str = Query(..., description="Second team ID or name"),
):
    """
    Head-to-Head (H2H) comparison between two clubs across all seasons and leagues.
    Calculates aggregate records (wins, draws, goals) and returns chronological matches.
    """
    HomeTeam = aliased(DimTeam)
    AwayTeam = aliased(DimTeam)

    with get_session() as session:
        # Normalize alias or query string
        q1 = COMMON_H2H_ALIASES.get(team1.lower().strip(), team1.strip())
        q2 = COMMON_H2H_ALIASES.get(team2.lower().strip(), team2.strip())

        # Resolve team 1 (ID -> exact name -> substring match)
        t1 = session.scalar(
            select(DimTeam).where(
                (DimTeam.team_id == team1) | (DimTeam.team_name.ilike(q1))
            )
        )
        if not t1:
            t1 = session.scalar(
                select(DimTeam).where(DimTeam.team_name.ilike(chr(37) + q1 + chr(37)))
            )

        # Resolve team 2 (ID -> exact name -> substring match)
        t2 = session.scalar(
            select(DimTeam).where(
                (DimTeam.team_id == team2) | (DimTeam.team_name.ilike(q2))
            )
        )
        if not t2:
            t2 = session.scalar(
                select(DimTeam).where(DimTeam.team_name.ilike(chr(37) + q2 + chr(37)))
            )

        if not t1 or not t2:
            raise HTTPException(
                status_code=404,
                detail=f"One or both teams not found (team1: '{team1}', team2: '{team2}')",
            )

        t1_id, t2_id = t1.team_id, t2.team_id

        # Query all matches between t1 and t2
        stmt = (
            select(
                FactMatch,
                DimLeague.league_name,
                HomeTeam.team_name.label("home_name"),
                AwayTeam.team_name.label("away_name"),
            )
            .join(DimLeague, FactMatch.league_id == DimLeague.league_id)
            .join(HomeTeam, FactMatch.home_team_id == HomeTeam.team_id)
            .join(AwayTeam, FactMatch.away_team_id == AwayTeam.team_id)
            .where(
                ((FactMatch.home_team_id == t1_id) & (FactMatch.away_team_id == t2_id))
                | ((FactMatch.home_team_id == t2_id) & (FactMatch.away_team_id == t1_id))
            )
            .order_by(
                FactMatch.match_date.desc().nullslast(),
                FactMatch.match_time.desc().nullslast(),
            )
        )

        rows = session.execute(stmt).all()

        t1_wins = 0
        t2_wins = 0
        draws = 0
        t1_goals = 0
        t2_goals = 0
        matches_list = []

        for match, l_name, h_name, a_name in rows:
            is_finished = match.status == "FINISHED"
            is_t1_home = match.home_team_id == t1_id

            h_score = match.home_score if match.home_score is not None else 0
            a_score = match.away_score if match.away_score is not None else 0

            if is_finished:
                if is_t1_home:
                    t1_goals += h_score
                    t2_goals += a_score
                    if h_score > a_score:
                        t1_wins += 1
                        winner = t1_id
                    elif a_score > h_score:
                        t2_wins += 1
                        winner = t2_id
                    else:
                        draws += 1
                        winner = "DRAW"
                else:
                    t1_goals += a_score
                    t2_goals += h_score
                    if a_score > h_score:
                        t1_wins += 1
                        winner = t1_id
                    elif h_score > a_score:
                        t2_wins += 1
                        winner = t2_id
                    else:
                        draws += 1
                        winner = "DRAW"
            else:
                winner = None

            matches_list.append({
                "match_id": match.match_id,
                "league_id": match.league_id,
                "league_name": l_name,
                "season": match.season,
                "round": match.round,
                "round_name": match.round_name,
                "match_date": match.match_date.isoformat() if match.match_date else None,
                "match_time": match.match_time,
                "home_team_id": match.home_team_id,
                "home_team": h_name or match.home_team_id,
                "away_team_id": match.away_team_id,
                "away_team": a_name or match.away_team_id,
                "home_score": match.home_score,
                "away_score": match.away_score,
                "score": match.score,
                "status": match.status,
                "winner": winner,
            })

        total_played = t1_wins + t2_wins + draws

        return {
            "team1": {"team_id": t1.team_id, "team_name": t1.team_name},
            "team2": {"team_id": t2.team_id, "team_name": t2.team_name},
            "summary": {
                "total_matches": len(matches_list),
                "total_finished": total_played,
                "team1_wins": t1_wins,
                "team2_wins": t2_wins,
                "draws": draws,
                "team1_goals": t1_goals,
                "team2_goals": t2_goals,
            },
            "matches": matches_list,
        }

# ---------------------------------------------------------------------------
# Crawl Observability & Monitoring Endpoints
# ---------------------------------------------------------------------------

@app.get("/public/crawl-logs")
def public_crawl_logs(
    league_id: Optional[int] = Query(None),
    season: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    trigger: Optional[str] = Query(None),
):
    """Query crawl execution history and audit logs with pagination and filters."""
    stmt = (
        select(CrawlStateLog, DimLeague.league_name)
        .outerjoin(DimLeague, CrawlStateLog.league_id == DimLeague.league_id)
    )
    count_stmt = select(func.count()).select_from(CrawlStateLog)

    if league_id:
        stmt = stmt.where(CrawlStateLog.league_id == league_id)
        count_stmt = count_stmt.where(CrawlStateLog.league_id == league_id)
    if season:
        stmt = stmt.where(CrawlStateLog.season == season)
        count_stmt = count_stmt.where(CrawlStateLog.season == season)
    if status:
        stmt = stmt.where(CrawlStateLog.status == status.upper())
        count_stmt = count_stmt.where(CrawlStateLog.status == status.upper())
    if trigger:
        stmt = stmt.where(CrawlStateLog.trigger_reason.startswith(trigger))
        count_stmt = count_stmt.where(CrawlStateLog.trigger_reason.startswith(trigger))

    with get_session() as session:
        total = session.scalar(count_stmt) or 0
        offset = (page - 1) * page_size
        stmt = stmt.order_by(CrawlStateLog.crawled_at.desc(), CrawlStateLog.id.desc()).offset(offset).limit(page_size)
        rows = session.execute(stmt).all()

        items = []
        for log, l_name in rows:
            items.append({
                "id": log.id,
                "league_id": log.league_id,
                "league_name": l_name or f"League {log.league_id}",
                "season": log.season,
                "crawled_at": log.crawled_at.isoformat() if log.crawled_at else None,
                "status": log.status,
                "fixtures_count": log.fixtures_count,
                "next_recrawl_at": log.next_recrawl_at.isoformat() if log.next_recrawl_at else None,
                "error": log.error,
                "trigger": log.trigger_reason,
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
            "logs": items,
        }


@app.get("/public/crawl-overview")
def public_crawl_overview(season: Optional[str] = Query(None)):
    """Summary of all leagues' crawl state and upcoming scheduled runs."""
    from sqlalchemy import and_

    with get_session() as session:
        db_leagues = session.scalars(select(DimLeague).order_by(DimLeague.league_name)).all()
        league_map = {l.league_id: l.league_name for l in db_leagues}

        subq = (
            select(
                CrawlStateLog.league_id,
                func.max(CrawlStateLog.crawled_at).label("max_at")
            )
            .group_by(CrawlStateLog.league_id)
        )
        if season:
            subq = subq.where(CrawlStateLog.season == season)
        subq = subq.subquery()

        stmt = (
            select(CrawlStateLog, DimLeague.league_name)
            .join(subq, and_(CrawlStateLog.league_id == subq.c.league_id, CrawlStateLog.crawled_at == subq.c.max_at))
            .outerjoin(DimLeague, CrawlStateLog.league_id == DimLeague.league_id)
            .order_by(CrawlStateLog.crawled_at.desc())
        )
        latest_rows = session.execute(stmt).all()

        leagues_status = []
        for log, l_name in latest_rows:
            leagues_status.append({
                "league_id": log.league_id,
                "league_name": l_name or league_map.get(log.league_id, f"League {log.league_id}"),
                "season": log.season,
                "status": log.status,
                "crawled_at": log.crawled_at.isoformat() if log.crawled_at else None,
                "next_recrawl_at": log.next_recrawl_at.isoformat() if log.next_recrawl_at else None,
                "fixtures_count": log.fixtures_count or 0,
                "error": log.error,
                "trigger": log.trigger_reason,
            })

        total_runs = session.scalar(select(func.count()).select_from(CrawlStateLog)) or 0
        success_runs = session.scalar(
            select(func.count()).select_from(CrawlStateLog).where(CrawlStateLog.status == "SUCCESS")
        ) or 0
        failed_runs = session.scalar(
            select(func.count()).select_from(CrawlStateLog).where(CrawlStateLog.status == "FAILED")
        ) or 0

        now_utc = datetime.now(timezone.utc)
        upcoming = sorted(
            (
                x for x in leagues_status
                if x["next_recrawl_at"]
                and datetime.fromisoformat(x["next_recrawl_at"]) > now_utc
            ),
            key=lambda x: datetime.fromisoformat(x["next_recrawl_at"]),
        )
        next_run_info = None
        if upcoming:
            n = upcoming[0]
            next_run_info = {
                "league_id": n["league_id"],
                "league_name": n["league_name"],
                "next_recrawl_at": n["next_recrawl_at"],
            }

        return {
            "total_runs": total_runs,
            "success_runs": success_runs,
            "failed_runs": failed_runs,
            "success_rate": round(success_runs / total_runs * 100, 1) if total_runs > 0 else 100.0,
            "next_upcoming_run": next_run_info,
            "leagues_status": leagues_status,
        }
from pydantic import BaseModel

class IngestPayload(BaseModel):
    league_id: int
    season: str
    fixtures: List[Dict[str, Any]]
    trigger_reason: Optional[str] = None
    crawled_at: Optional[str] = None


@app.post("/ingest", dependencies=[Depends(verify_token)])
def ingest(payload: IngestPayload):
    """Receive crawled fixtures from the scheduler and publish them to Kafka."""
    publish_raw_fixtures(
        league_id=payload.league_id,
        season=payload.season,
        fixtures=payload.fixtures,
        trigger_reason=payload.trigger_reason,
        crawled_at=payload.crawled_at,
    )
    return {"status": "published", "count": len(payload.fixtures)}