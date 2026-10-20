"""
Seed script for populating dim_leagues table using SQLAlchemy ORM.
Loads configuration from src/config/leagues.json and performs idempotent upserts via session.merge().
"""

import json
from pathlib import Path
from sqlalchemy.orm import Session

from src.database.models import DimLeague
from src.config import LEAGUES_CONFIG_FILE


def seed_leagues(session: Session, config_path: Path = LEAGUES_CONFIG_FILE) -> int:
    """
    Load leagues from JSON config and upsert into dim_leagues using SQLAlchemy merge.

    Args:
        session: Active SQLAlchemy Session.
        config_path: Path to leagues.json file.

    Returns:
        Number of seeded league entities.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Leagues configuration not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        leagues_data = json.load(f)

    count = 0
    for item in leagues_data:
        league_obj = DimLeague(
            league_id=int(item["id"]),
            league_name=item["name"].strip(),
            country_code=item.get("country_code", "UNK").strip(),
        )
        session.merge(league_obj)
        count += 1

    session.flush()
    print(f"[Seed] Successfully seeded {count} leagues into 'dim_leagues' via SQLAlchemy.")
    return count
