from datetime import datetime, timezone

from sqlalchemy import text

from src.database import get_session
from src.services.load.loader import load_fixtures
from src.services.transform.fixtures import transform_fixtures

SEASON = "2026-2027"
CRAWLED_AT = "2026-10-20T12:00:00+00:00"


def raw_match(match_id, finished, score="2 - 1", utc="2026-10-24T15:00:00Z"):
    status = {"utcTime": utc, "finished": finished, "started": finished, "cancelled": False}
    if finished:
        status["scoreStr"] = score
    return {
        "round": "1", "roundName": 1, "id": match_id,
        "pageUrl": f"/matches/a-vs-b/x#{match_id}",
        "home": {"name": "Arsenal", "id": "9825"},
        "away": {"name": "Chelsea", "id": "8455"},
        "status": status,
    }


def load(raw, **kwargs):
    return load_fixtures(
        fixtures=transform_fixtures(raw), league_id=47, season=SEASON, **kwargs
    )


def scalar(sql, **params):
    with get_session() as session:
        return session.execute(text(sql), params).scalar()


def last_log():
    with get_session() as session:
        return session.execute(text(
            "SELECT fixtures_count, trigger_reason, crawled_at, next_recrawl_at "
            "FROM crawl_state_log ORDER BY id DESC LIMIT 1"
        )).one()


def test_load_inserts_matches():
    load([raw_match("1", True), raw_match("2", False)])
    assert scalar("SELECT count(*) FROM fact_matches") == 2


def test_loading_the_same_data_twice_creates_no_duplicates():
    raw = [raw_match("1", True), raw_match("2", False)]
    load(raw)
    load(raw)
    assert scalar("SELECT count(*) FROM fact_matches") == 2


def test_scheduled_match_is_updated_when_it_finishes():
    load([raw_match("1", False)])
    load([raw_match("1", True, score="3 - 0")])
    row = None
    with get_session() as session:
        row = session.execute(text(
            "SELECT status, score, home_score, match_result FROM fact_matches WHERE match_id='1'"
        )).one()
    assert tuple(row) == ("FINISHED", "3 - 0", 3, "H")


def test_crawl_state_row_records_reason_time_and_next_crawl():
    load([raw_match("1", True), raw_match("2", False)],
         trigger_reason="manual", crawled_at=CRAWLED_AT)
    log = last_log()
    assert log.fixtures_count == 1
    assert log.trigger_reason == "manual"
    assert log.crawled_at == datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    assert log.next_recrawl_at is not None


def test_fixtures_count_only_counts_newly_finished_matches():
    raw = [raw_match("1", True), raw_match("2", True)]
    load(raw)
    assert last_log().fixtures_count == 2
    load(raw)
    assert last_log().fixtures_count == 0


def test_next_recrawl_is_null_when_no_match_is_scheduled():
    load([raw_match("1", True)], crawled_at=CRAWLED_AT)
    assert last_log().next_recrawl_at is None