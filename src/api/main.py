import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from src.database import CrawlStateRepository, get_session
from src.database.models import DimLeague

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