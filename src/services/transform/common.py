"""
Common transformation and normalization utilities.
Provides helper functions for datetime parsing, team name cleanup, number conversion,
score calculation, and stage/round categorization.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple


def _to_int(val: Any) -> Optional[int]:
    """Safely convert value to integer, returning None if invalid."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _clean_string(val: Any) -> Optional[str]:
    """Strip whitespace and return cleaned string or None if empty."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _parse_iso_datetime(iso_str: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Parse ISO UTC datetime string into date, time, and normalized UTC string.
    Example: '2025-08-15T19:00:00Z' -> {'match_date': '2025-08-15', 'match_time': '19:00:00'}
    """
    if not iso_str:
        return {"match_date": None, "match_time": None, "utc_time": None}

    cleaned = iso_str.strip()
    try:
        dt_str = cleaned.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str)
        return {
            "match_date": dt.strftime("%Y-%m-%d"),
            "match_time": dt.strftime("%H:%M:%S"),
            "utc_time": cleaned,
        }
    except (ValueError, TypeError):
        date_part = cleaned[:10] if len(cleaned) >= 10 else None
        time_part = cleaned[11:19] if len(cleaned) >= 19 else None
        return {"match_date": date_part, "match_time": time_part, "utc_time": cleaned}


def _normalize_team_name(name: Optional[str]) -> str:
    """Normalize team name by stripping excessive whitespaces."""
    if not name:
        return "Unknown"
    return " ".join(name.strip().split())


def _parse_score(score_str: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract home and away scores from a score string.
    Example: '4 - 2' -> (4, 2); None or 'VS' -> (None, None)
    """
    if not score_str or "-" not in score_str:
        return None, None

    parts = score_str.split("-")
    if len(parts) != 2:
        return None, None

    home_score = _to_int(parts[0].strip())
    away_score = _to_int(parts[1].strip())
    return home_score, away_score


def _determine_match_status(status_obj: Dict[str, Any]) -> str:
    """
    Normalize status flags into a canonical status code:
    FINISHED, CANCELLED, LIVE, POSTPONED, or SCHEDULED.
    """
    if not status_obj:
        return "SCHEDULED"

    if status_obj.get("cancelled", False):
        return "CANCELLED"
    if status_obj.get("finished", False):
        return "FINISHED"
    if status_obj.get("started", False):
        return "LIVE"

    reason = status_obj.get("reason", {})
    if isinstance(reason, dict) and reason.get("short") == "Postp.":
        return "POSTPONED"

    return "SCHEDULED"


def _calculate_match_result(
    home_score: Optional[int], away_score: Optional[int]
) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    """
    Compute match outcome and points.
    Returns:
        (result: 'H'|'D'|'A', home_points: 3|1|0, away_points: 3|1|0, goal_diff: int)
    """
    if home_score is None or away_score is None:
        return None, None, None, None

    goal_diff = home_score - away_score
    if home_score > away_score:
        return "H", 3, 0, goal_diff
    elif home_score < away_score:
        return "A", 0, 3, goal_diff
    else:
        return "D", 1, 1, 0


def _categorize_stage_and_round(
    raw_round: Any, raw_round_name: Any
) -> Tuple[str, str, str]:
    """
    Determine standardized round, round_name, and tournament stage.
    Handles league rounds, playoff ties, and knockout rounds (Champions League).

    Returns:
        Tuple of (round, round_name, stage):
        - round: '1', 'playoff', '1/8', '1/4', '1/2', 'final'
        - round_name: 'Round 1', 'Play-offs', 'Round of 16', 'Quarter-Finals', 'Semi-Finals', 'Final'
        - stage: 'LEAGUE_STAGE', 'PLAYOFF', or 'KNOCKOUT'
    """
    r_str = str(raw_round or "").strip()
    rn_str = str(raw_round_name or "").strip()
    r_lower = r_str.lower()
    rn_lower = rn_str.lower()

    if r_lower == "playoff" or rn_lower == "playoff":
        return "playoff", "Play-offs", "PLAYOFF"

    if r_lower == "1/8" or rn_lower == "round of 16":
        return "1/8", "Round of 16", "KNOCKOUT"

    if r_lower == "1/4" or "quarter" in rn_lower:
        return "1/4", "Quarter-Finals", "KNOCKOUT"

    if r_lower == "1/2" or "semi" in rn_lower:
        return "1/2", "Semi-Finals", "KNOCKOUT"

    if r_lower == "final" or rn_lower == "final":
        return "final", "Final", "KNOCKOUT"

    # Numeric regular league rounds (e.g. 1, 2, ... 38)
    if r_str.isdigit():
        return r_str, f"Round {r_str}", "LEAGUE_STAGE"

    # Default fallback
    name_display = rn_str if rn_str else r_str
    return r_str, name_display, "LEAGUE_STAGE"
