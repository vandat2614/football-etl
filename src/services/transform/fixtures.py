"""
Fixtures Transformation Module.
Cleans and transforms raw fixture payloads into structured, relational-ready records.
"""

from typing import Any, Dict, List

try:
    from .common import (
        _clean_string,
        _determine_match_status,
        _normalize_team_name,
        _parse_iso_datetime,
        _parse_score,
        _calculate_match_result,
        _categorize_stage_and_round,
    )
except ImportError:
    from common import (
        _clean_string,
        _determine_match_status,
        _normalize_team_name,
        _parse_iso_datetime,
        _parse_score,
        _calculate_match_result,
        _categorize_stage_and_round,
    )


def _build_match_url(raw_match: Dict[str, Any], match_id: str) -> str:
    """Construct canonical match web URL."""
    page_url = raw_match.get("pageUrl", "")
    if page_url:
        return f"https://www.fotmob.com{page_url}"
    return f"https://www.fotmob.com/match/{match_id}"


def _transform_single_fixture(raw_match: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a single raw match dictionary into a standardized Silver schema.
    """
    match_id = str(raw_match.get("id", "")).strip()

    # Stage and Round normalization
    round_id, round_name, stage = _categorize_stage_and_round(
        raw_match.get("round"), raw_match.get("roundName")
    )

    # Teams
    home_obj = raw_match.get("home", {})
    away_obj = raw_match.get("away", {})
    home_team = _normalize_team_name(home_obj.get("name"))
    away_team = _normalize_team_name(away_obj.get("name"))
    home_team_id = str(home_obj.get("id", "")).strip() or None
    away_team_id = str(away_obj.get("id", "")).strip() or None

    # Status & Dates
    status_obj = raw_match.get("status", {})
    status = _determine_match_status(status_obj)
    dt_info = _parse_iso_datetime(status_obj.get("utcTime"))

    # Scores & Results (only populated if match is finished or has scores)
    score_str = status_obj.get("scoreStr") if status == "FINISHED" else None
    home_score, away_score = _parse_score(score_str)
    result, home_pts, away_pts, goal_diff = _calculate_match_result(home_score, away_score)

    return {
        "match_id": match_id,
        "round": round_id,
        "round_name": round_name,
        "stage": stage,
        "match_date": dt_info["match_date"],
        "match_time": dt_info["match_time"],
        "utc_time": dt_info["utc_time"],
        "home_team_id": home_team_id,
        "home_team": home_team,
        "away_team_id": away_team_id,
        "away_team": away_team,
        "status": status,
        "score": score_str,
        "home_score": home_score,
        "away_score": away_score,
        "match_result": result,
        "home_points": home_pts,
        "away_points": away_pts,
        "goal_difference": goal_diff,
        "match_url": _build_match_url(raw_match, match_id),
    }


def transform_fixtures(raw_fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform a collection of raw fixtures into clean, structured records.

    Args:
        raw_fixtures: List of raw match dictionaries from extract step.

    Returns:
        List of cleaned, standardized fixture dictionaries ready for database loading.
    """
    transformed: List[Dict[str, Any]] = []
    seen_ids = set()

    for raw_match in raw_fixtures:
        item = _transform_single_fixture(raw_match)
        match_id = item["match_id"]

        # Deduplicate matches by match_id
        if match_id and match_id in seen_ids:
            continue
        if match_id:
            seen_ids.add(match_id)

        transformed.append(item)

    return transformed
