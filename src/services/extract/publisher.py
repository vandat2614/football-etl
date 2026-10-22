"""
Fixture Kafka Publisher Module.
Provides helper to publish raw extracted fixtures to the 'raw-fixtures' Kafka topic.
"""

import logging
from typing import Any, Dict, List, Optional

import src.config as config
from src.kafka import BaseKafkaProducer

logger = logging.getLogger("FixturePublisher")

_producer: Optional[BaseKafkaProducer] = None


def get_producer(bootstrap_servers: str = None) -> BaseKafkaProducer:
    """Singleton getter for BaseKafkaProducer."""
    global _producer
    if _producer is None:
        _producer = BaseKafkaProducer(bootstrap_servers=bootstrap_servers)
    return _producer


def publish_raw_fixtures(
    league_id: int,
    season: str,
    fixtures: List[Dict[str, Any]],
    bootstrap_servers: str = None,
    trigger_reason: Optional[str] = None,
    crawled_at: Optional[str] = None,
) -> None:
    """
    Publish raw crawled fixtures to Kafka topic 'raw-fixtures'.

    Args:
        league_id: Identifier of the tournament.
        season: Target season (e.g. '2025-2026').
        fixtures: Raw list of match records returned by extract_fixtures().
        bootstrap_servers: Optional custom broker address.
    """
    p = get_producer(bootstrap_servers=bootstrap_servers)

    payload = {
        "league_id": league_id,
        "season": season,
        "fixtures": fixtures,
        "count": len(fixtures),
        "trigger_reason": trigger_reason,
        "crawled_at": crawled_at,
    }
    key = str(league_id)

    p.produce_message(
        topic=config.TOPIC_RAW_FIXTURES,
        key=key,
        value=payload,
    )
    p.flush()
    logger.info(
        "Published %d raw matches for league %d to '%s'.",
        len(fixtures), league_id, config.TOPIC_RAW_FIXTURES,
    )
