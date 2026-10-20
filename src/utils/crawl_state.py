"""Pure logic (no I/O) that decides when a league must be crawled again.

Location: experiment/src/utils/crawl_state.py
Reading and writing the state is done by CrawlStateRepository, not here.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("crawl_state")

REFRESH = timedelta(days=7)     # periodic re-crawl of fixtures
BUFFER = timedelta(hours=3)     # wait for the last match to finish after its kickoff
GROUP_GAP = timedelta(hours=4)  # grouping rule

_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _aware(dt: datetime) -> datetime:
    """Normalize to timezone-aware UTC (the DB may return naive datetimes)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse(s: str) -> datetime:
    return _aware(datetime.fromisoformat(s.replace("Z", "+00:00")))


def _iso(dt: datetime) -> str:
    return _aware(dt).strftime(_FMT)


def _kickoff_if_scheduled(fx: Dict[str, Any]) -> Optional[datetime]:
    """Return the kickoff time (UTC) if the match has not been played yet, else None.

    None is returned for matches that are started, finished or cancelled.
    Supports two shapes: transformed data (status="SCHEDULED", utc_time) and
    raw FotMob data (status={"utcTime", "started", "finished", "cancelled"}).
    Adjust this function if the raw fixtures have a different shape.
    """
    status = fx.get("status")
    if isinstance(status, str):
        return _parse(fx["utc_time"]) if status == "SCHEDULED" else None
    if isinstance(status, dict):
        if status.get("started") or status.get("finished") or status.get("cancelled"):
            return None
        return _parse(status["utcTime"])
    raise ValueError("unrecognized fixture schema")


def scheduled_max_times(fixtures: List[Dict[str, Any]]) -> List[str]:
    """Group the upcoming matches and return the max kickoff time (UTC) of each group.

    Rules: same (UTC) day -> same group; different day but kickoff earlier than
    the group's max kickoff + 4 hours -> same group.
    """
    kickoffs, unrecognized = [], 0
    for fx in fixtures:
        try:
            dt = _kickoff_if_scheduled(fx)
        except (ValueError, KeyError, TypeError):
            unrecognized += 1
            continue
        if dt is not None:
            kickoffs.append(dt)

    if fixtures and unrecognized == len(fixtures):
        logger.warning(
            "Fixture schema not recognized - groups cannot be computed. "
            "Adjust _kickoff_if_scheduled()."
        )

    kickoffs.sort()
    groups = []  # each group: {"dates": set, "max": datetime}
    for dt in kickoffs:
        cur = groups[-1] if groups else None
        if cur and (dt.date() in cur["dates"] or dt < cur["max"] + GROUP_GAP):
            cur["dates"].add(dt.date())
            cur["max"] = max(cur["max"], dt)
        else:
            groups.append({"dates": {dt.date()}, "max": dt})
    return [_iso(g["max"]) for g in groups]


def pending_max_times(fixtures: List[Dict[str, Any]], now: datetime) -> List[str]:
    """Max kickoff times of the groups whose end (max + BUFFER) is still in the future."""
    return [t for t in scheduled_max_times(fixtures) if _parse(t) + BUFFER > now]


def due_reason(
    last_crawl_at: Optional[datetime],
    max_times: Optional[List[str]],
    now: datetime,
) -> Optional[str]:
    """Return why a league must be crawled now, or None if it is not due yet.

    last_crawl_at and max_times come from the latest SUCCESS row of crawl_state_log.
    """
    if last_crawl_at is None:
        return "never_crawled"
    last = _aware(last_crawl_at)
    if now - last >= REFRESH:
        return "refresh_7d"
    for t in max_times or []:
        # The group has finished and no crawl happened after that point
        if last < _parse(t) + BUFFER <= now:
            return f"group_finished:{t}"
    return None