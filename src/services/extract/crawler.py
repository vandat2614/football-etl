"""
Main Crawler Module.
Coordinates fetching and parsing to extract raw league fixtures from source.
"""

from typing import Any, Dict, List, Union

try:
    from .fetcher import fetch_page
    from .parser import parse_items
except ImportError:
    from fetcher import fetch_page
    from parser import parse_items


def _resolve_league_info(league: Union[Dict[str, Any], int, str]) -> tuple[int, str]:
    """
    Resolve league identifier and slug from league config dict or raw identifier.

    Args:
        league: League dictionary or integer ID or string slug.

    Returns:
        Tuple of (league_id, league_slug).
    """
    if isinstance(league, dict):
        league_id = league.get("id") or league.get("fotmob_id")
        name = league.get("name", "league").lower().replace(" ", "_")
        slug = league.get("slug", name)
        return int(league_id), slug

    return int(league), f"league_{league}"


def extract_fixtures(
    league: Union[Dict[str, Any], int, str], 
    season: str = "2025-2026"
) -> List[Dict[str, Any]]:
    """
    Extract raw fixture records for a given league and season without transforming data.

    Args:
        league: League config dict (containing 'id' and 'name'/'slug') or league ID.
        season: Target season formatted as 'YYYY-YYYY' (e.g. '2025-2026').

    Returns:
        List of raw match records directly from the provider.
    """
    league_id, league_slug = _resolve_league_info(league)
    season_fmt = season.replace("/", "-").strip()

    url = (
        f"https://www.fotmob.com/leagues/{league_id}/fixtures/{league_slug}"
        f"?season={season_fmt}&group=by-date"
    )

    html = fetch_page(url)
    fixtures = parse_items(html)
    return fixtures
