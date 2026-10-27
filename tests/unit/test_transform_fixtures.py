import pytest

from src.services.transform.common import (
    _calculate_match_result,
    _categorize_stage_and_round,
    _clean_string,
    _determine_match_status,
    _normalize_team_name,
    _parse_iso_datetime,
    _parse_score,
    _to_int,
)


@pytest.mark.parametrize("value, expected", [
    ("5", 5), (7, 7), (3.7, 3), (None, None), ("x", None), ("3.7", None), ("", None),
])
def test_to_int(value, expected):
    assert _to_int(value) == expected


@pytest.mark.parametrize("value, expected", [
    (None, None), ("   ", None), ("  abc ", "abc"), (123, "123"),
])
def test_clean_string(value, expected):
    assert _clean_string(value) == expected


@pytest.mark.parametrize("score, expected", [
    ("4 - 2", (4, 2)),
    ("0-0", (0, 0)),
    ("  3 -  1 ", (3, 1)),
    (None, (None, None)),
    ("", (None, None)),
    ("VS", (None, None)),
    ("1-2-3", (None, None)),
    ("a - b", (None, None)),
])
def test_parse_score(score, expected):
    assert _parse_score(score) == expected


@pytest.mark.parametrize("status, expected", [
    (None, "SCHEDULED"),
    ({}, "SCHEDULED"),
    ({"started": False, "finished": False, "cancelled": False}, "SCHEDULED"),
    ({"started": True, "finished": True}, "FINISHED"),
    ({"started": True}, "LIVE"),
    ({"cancelled": True, "finished": True}, "CANCELLED"),
    ({"reason": {"short": "Postp."}}, "POSTPONED"),
    ({"reason": "Postp."}, "SCHEDULED"),
])
def test_determine_match_status(status, expected):
    assert _determine_match_status(status) == expected


@pytest.mark.parametrize("home, away, expected", [
    (2, 1, ("H", 3, 0, 1)),
    (0, 3, ("A", 0, 3, -3)),
    (2, 2, ("D", 1, 1, 0)),
    (0, 0, ("D", 1, 1, 0)),
    (None, 1, (None, None, None, None)),
    (1, None, (None, None, None, None)),
])
def test_calculate_match_result(home, away, expected):
    assert _calculate_match_result(home, away) == expected


def test_parse_iso_datetime_splits_date_and_time():
    assert _parse_iso_datetime("2025-08-15T19:00:00Z") == {
        "match_date": "2025-08-15",
        "match_time": "19:00:00",
        "utc_time": "2025-08-15T19:00:00Z",
    }


def test_parse_iso_datetime_strips_whitespace():
    assert _parse_iso_datetime("  2025-08-15T19:00:00Z ")["utc_time"] == "2025-08-15T19:00:00Z"


@pytest.mark.parametrize("value", [None, ""])
def test_parse_iso_datetime_empty(value):
    assert _parse_iso_datetime(value) == {
        "match_date": None, "match_time": None, "utc_time": None,
    }


def test_parse_iso_datetime_falls_back_to_date_prefix():
    assert _parse_iso_datetime("2025-08-15Tnot-a-time")["match_date"] == "2025-08-15"


@pytest.mark.parametrize("name, expected", [
    (None, "Unknown"),
    ("", "Unknown"),
    ("  Real   Madrid ", "Real Madrid"),
    ("Bayern München", "Bayern München"),
])
def test_normalize_team_name(name, expected):
    assert _normalize_team_name(name) == expected


@pytest.mark.xfail(reason="whitespace-only name returns an empty string instead of 'Unknown'")
def test_normalize_team_name_whitespace_only():
    assert _normalize_team_name("   ") == "Unknown"


@pytest.mark.parametrize("raw_round, raw_name, expected", [
    ("playoff", "Playoff", ("playoff", "Play-offs", "PLAYOFF")),
    ("", "playoff", ("playoff", "Play-offs", "PLAYOFF")),
    ("1/8", "", ("1/8", "Round of 16", "KNOCKOUT")),
    ("", "Round of 16", ("1/8", "Round of 16", "KNOCKOUT")),
    ("1/4", "", ("1/4", "Quarter-Finals", "KNOCKOUT")),
    ("", "Quarter-finals", ("1/4", "Quarter-Finals", "KNOCKOUT")),
    ("1/2", "", ("1/2", "Semi-Finals", "KNOCKOUT")),
    ("", "Semi-finals", ("1/2", "Semi-Finals", "KNOCKOUT")),
    ("final", "", ("final", "Final", "KNOCKOUT")),
    ("", "Final", ("final", "Final", "KNOCKOUT")),
    ("5", 5, ("5", "Round 5", "LEAGUE_STAGE")),
    (38, "38", ("38", "Round 38", "LEAGUE_STAGE")),
    ("League Stage - Round 3", "League Stage - Round 3",
     ("League Stage - Round 3", "League Stage - Round 3", "LEAGUE_STAGE")),
    (None, None, ("", "", "LEAGUE_STAGE")),
])
def test_categorize_stage_and_round(raw_round, raw_name, expected):
    assert _categorize_stage_and_round(raw_round, raw_name) == expected