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
from src.database import FixtureRepository, get_session
from src.services.transform import transform_fixtures
from src.utils.logging_config import setup_logging

logger = logging.getLogger("import_raw")

ALIASES = {"champon_league": "champions_league"}


def _stem_of(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def load_league_map() -> dict[str, int]:
    with open(LEAGUES_CONFIG_FILE, encoding="utf-8") as f:
        leagues = json.load(f)
    return {_stem_of(lg["name"]): int(lg["id"]) for lg in leagues}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="data/raw")
    args = parser.parse_args()
    setup_logging(log_level=LOG_LEVEL)

    league_map = load_league_map()
    root = Path(args.dir)
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
                logger.info("Loaded %d matches: %s / %s", n, season, file.stem)
                ok += 1
            except Exception as exc:
                logger.error("Failed %s: %s", file, exc)
                failed += 1

    logger.info("Done. files ok=%d, failed=%d", ok, failed)


if __name__ == "__main__":
    main()