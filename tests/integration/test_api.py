from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.database import STATUS_SUCCESS, CrawlStateRepository, get_session

AUTH = {"Authorization": "Bearer test-token"}
NOW = datetime.now(timezone.utc)


@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app)


def add_log(crawled_at, next_recrawl_at=None, reason="manual", count=3, season="2026-2027"):
    with get_session() as session:
        CrawlStateRepository(session).record_crawl(
            league_id=47, season=season, status=STATUS_SUCCESS,
            trigger_reason=reason, fixtures_count=count,
            next_recrawl_at=next_recrawl_at, crawled_at=crawled_at,
        )


# ---------- authentication ----------

@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "test-token"}])
def test_crawl_state_rejects_missing_or_wrong_token(client, headers):
    assert client.get("/crawl-state", params={"season": "2026-2027"}, headers=headers).status_code == 401


def test_crawl_state_returns_latest_success_per_league(client):
    add_log(NOW - timedelta(days=2), next_recrawl_at=NOW + timedelta(days=1))
    add_log(NOW - timedelta(hours=1), next_recrawl_at=None)
    r = client.get("/crawl-state", params={"season": "2026-2027"}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["league_id"] == 47
    assert body[0]["next_recrawl_at"] is None


def test_public_endpoints_need_no_token(client):
    assert client.get("/public/crawl-overview").status_code == 200


# ---------- /ingest ----------

def test_ingest_rejects_missing_token(client):
    assert client.post("/ingest", json={}).status_code == 401


def test_ingest_publishes_payload_to_kafka(client, monkeypatch):
    sent = {}
    monkeypatch.setattr("src.api.main.publish_raw_fixtures", lambda **kw: sent.update(kw))
    payload = {
        "league_id": 47, "season": "2026-2027",
        "fixtures": [{"id": "1"}, {"id": "2"}],
        "trigger_reason": "periodic_refresh",
        "crawled_at": "2026-10-20T12:00:00+00:00",
    }
    r = client.post("/ingest", json=payload, headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"status": "published", "count": 2}
    assert sent["league_id"] == 47
    assert sent["trigger_reason"] == "periodic_refresh"
    assert sent["crawled_at"] == "2026-10-20T12:00:00+00:00"
    assert len(sent["fixtures"]) == 2


def test_ingest_rejects_invalid_payload(client):
    r = client.post("/ingest", json={"league_id": "abc"}, headers=AUTH)
    assert r.status_code == 422


# ---------- /public/crawl-logs ----------

def test_crawl_logs_expose_trigger_reason(client):
    add_log(NOW, reason="manual")
    log = client.get("/public/crawl-logs").json()["logs"][0]
    assert log["trigger"] == "manual"
    assert log["league_name"] == "Premier League"


def test_crawl_logs_filter_by_trigger_prefix(client):
    add_log(NOW - timedelta(hours=3), reason="periodic_refresh")
    add_log(NOW - timedelta(hours=2), reason="match_group_finished:2026-10-20T10:00:00Z")
    add_log(NOW - timedelta(hours=1), reason="manual")
    body = client.get("/public/crawl-logs", params={"trigger": "match_group_finished"}).json()
    assert body["total"] == 1
    assert body["logs"][0]["trigger"].startswith("match_group_finished")


def test_crawl_logs_are_paginated(client):
    for i in range(5):
        add_log(NOW - timedelta(hours=i))
    body = client.get("/public/crawl-logs", params={"page_size": 2}).json()
    assert body["total"] == 5
    assert len(body["logs"]) == 2
    assert body["total_pages"] == 3


# ---------- /public/crawl-overview ----------

def test_overview_next_run_ignores_superseded_rows(client):
    add_log(NOW - timedelta(days=1), next_recrawl_at=NOW + timedelta(days=2))
    add_log(NOW - timedelta(hours=1), next_recrawl_at=None)
    assert client.get("/public/crawl-overview").json()["next_upcoming_run"] is None


def test_overview_reports_upcoming_run_of_latest_row(client):
    target = NOW + timedelta(hours=5)
    add_log(NOW - timedelta(hours=1), next_recrawl_at=target)
    run = client.get("/public/crawl-overview").json()["next_upcoming_run"]
    assert run["league_name"] == "Premier League"
    assert datetime.fromisoformat(run["next_recrawl_at"]) == target