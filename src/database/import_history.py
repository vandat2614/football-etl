"""
Import historical raw fixtures (data/raw/<season>/<league>.json) into the database.

Usage:
    python -m src.database.import_raw --dir data/raw
"""

import argparse
import json
import logging
from pathlib import Path

from src.config import LEAGUES_CONFIG_FILE, LOG_LEVEL
from src.services.transform import transform_fixtures
from src.utils.logging_config import setup_logging

from datetime import datetime, timedelta, timezone

from src.database import (
    STATUS_SUCCESS,
    CrawlStateRepository,
    FixtureRepository,
    get_session,
)

logger = logging.getLogger("import_raw")

ALIASES = {"champon_league": "champions_league"}


def _stem_of(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def load_league_map() -> dict[str, int]:
    with open(LEAGUES_CONFIG_FILE, encoding="utf-8") as f:
        leagues = json.load(f)
    return {_stem_of(lg["name"]): int(lg["id"]) for lg in leagues}


def import_history(root: Path) -> tuple[int, int]:
    """Import every <season>/<league>.json under root. Returns (files_ok, files_failed)."""
    league_map = load_league_map()
    ok = failed = 0

    for season_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        season = season_dir.name.replace("_", "-")  # 2010_2011 -> 2010-2011
        for file in sorted(season_dir.glob("*.json")):
            stem = ALIASES.get(file.stem, file.stem)
            league_id = league_map.get(stem)
            if league_id is None:
                logger.warning("Skip %s: no league matches '%s'", file, file.stem)
                continue
            try:
                raw = json.loads(file.read_text(encoding="utf-8"))
                fixtures = transform_fixtures(raw)
                with get_session() as session:
                    n = FixtureRepository(session).upsert_fixtures(
                        fixtures=fixtures, league_id=league_id, season=season
                    )

                    finished = [
                        f["utc_time"] for f in fixtures
                        if f["status"] == "FINISHED" and f.get("utc_time")
                    ]
                    if finished:
                        last_kickoff = datetime.fromisoformat(max(finished).replace("Z", "+00:00"))
                        crawled_at = min(last_kickoff + timedelta(days=1), datetime.now(timezone.utc))
                        CrawlStateRepository(session).record_crawl(
                            league_id=league_id,
                            season=season,
                            status=STATUS_SUCCESS,
                            trigger_reason="periodic_refresh",
                            fixtures_count=len(finished),
                            next_recrawl_at=None,
                            crawled_at=crawled_at,
                        )

                logger.info("Loaded %d matches: %s / %s", n, season, file.stem)
                ok += 1
            except Exception as exc:
                logger.error("Failed %s: %s", file, exc)
                failed += 1

    logger.info("Done. files ok=%d, failed=%d", ok, failed)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="data/raw")
    args = parser.parse_args()
    setup_logging(log_level=LOG_LEVEL)
    ok, failed = import_history(Path(args.dir))
    logger.info("Done. files ok=%d, failed=%d", ok, failed)

if __name__ == "__main__":
    main()