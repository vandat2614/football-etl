from datetime import datetime, timedelta, timezone

from src.utils.crawl_state import (
    BUFFER,
    due_reason,
    next_recrawl_time,
    scheduled_max_times,
)

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def scheduled(utc_time: str) -> dict:
    return {"status": "SCHEDULED", "utc_time": utc_time}


def finished(utc_time: str) -> dict:
    return {"status": "FINISHED", "utc_time": utc_time}


# ---------- due_reason ----------

def test_never_crawled_league_is_due():
    assert due_reason(None, None, NOW) == "periodic_refresh"


def test_crawl_older_than_7_days_is_due():
    last = NOW - timedelta(days=7)
    assert due_reason(last, None, NOW) == "periodic_refresh"


def test_recent_crawl_with_future_recrawl_is_not_due():
    last = NOW - timedelta(days=1)
    assert due_reason(last, NOW + timedelta(hours=5), NOW) is None


def test_recent_crawl_without_pending_group_is_not_due():
    assert due_reason(NOW - timedelta(days=1), None, NOW) is None


def test_finished_group_triggers_recrawl_and_reports_last_kickoff():
    last = NOW - timedelta(days=1)
    next_at = NOW - timedelta(minutes=5)
    reason = due_reason(last, next_at, NOW)
    expected_kickoff = (next_at - BUFFER).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert reason == f"match_group_finished:{expected_kickoff}"


# ---------- scheduled_max_times (grouping) ----------

def test_matches_on_same_day_form_one_group_with_latest_kickoff():
    fixtures = [
        scheduled("2026-10-24T12:30:00Z"),
        scheduled("2026-10-24T15:00:00Z"),
        scheduled("2026-10-24T17:30:00Z"),
    ]
    assert scheduled_max_times(fixtures) == ["2026-10-24T17:30:00Z"]


def test_matches_on_distant_days_form_separate_groups():
    fixtures = [scheduled("2026-10-24T15:00:00Z"), scheduled("2026-10-31T15:00:00Z")]
    assert scheduled_max_times(fixtures) == [
        "2026-10-24T15:00:00Z",
        "2026-10-31T15:00:00Z",
    ]


def test_match_just_after_midnight_joins_previous_group():
    # 3 hours after the group's last kickoff, which is under the 4 hour gap
    fixtures = [scheduled("2026-10-24T22:00:00Z"), scheduled("2026-10-25T01:00:00Z")]
    assert scheduled_max_times(fixtures) == ["2026-10-25T01:00:00Z"]


def test_match_more_than_4_hours_after_midnight_starts_new_group():
    fixtures = [scheduled("2026-10-24T20:00:00Z"), scheduled("2026-10-25T01:00:00Z")]
    assert len(scheduled_max_times(fixtures)) == 2


def test_finished_matches_are_ignored():
    fixtures = [finished("2026-10-01T15:00:00Z"), scheduled("2026-10-24T15:00:00Z")]
    assert scheduled_max_times(fixtures) == ["2026-10-24T15:00:00Z"]


def test_no_scheduled_matches_gives_no_groups():
    assert scheduled_max_times([finished("2026-05-01T15:00:00Z")]) == []


# ---------- next_recrawl_time ----------

def test_next_recrawl_is_last_kickoff_of_earliest_group_plus_buffer():
    fixtures = [scheduled("2026-10-24T14:00:00Z"), scheduled("2026-10-31T14:00:00Z")]
    assert next_recrawl_time(fixtures, NOW) == datetime(
        2026, 10, 24, 14, 0, tzinfo=timezone.utc
    ) + BUFFER


def test_next_recrawl_skips_groups_that_already_ended():
    fixtures = [scheduled("2026-10-24T14:00:00Z"), scheduled("2026-10-31T14:00:00Z")]
    after_first_group = datetime(2026, 10, 25, tzinfo=timezone.utc)
    assert next_recrawl_time(fixtures, after_first_group) == datetime(
        2026, 10, 31, 14, 0, tzinfo=timezone.utc
    ) + BUFFER


def test_next_recrawl_is_none_when_season_is_over():
    assert next_recrawl_time([finished("2026-05-01T15:00:00Z")], NOW) is None