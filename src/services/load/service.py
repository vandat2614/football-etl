"""
Fixture Load Service Module.
Continuous stream consumer that listens to transformed fixture events
and persists them into the database via load_fixtures.
"""

import logging
from typing import Any, Dict

import src.config as config
from src.kafka import BaseKafkaConsumer
from .loader import load_fixtures

logger = logging.getLogger("FixtureLoadService")


class FixtureLoadService:
    """
    Kafka Stream Consumer Service for loading transformed fixtures into the database.
    """

    def __init__(self, bootstrap_servers: str = None):
        self.consumer = BaseKafkaConsumer(
            group_id=config.KAFKA_LOAD_GROUP_ID,
            topics=[config.TOPIC_TRANSFORMED_FIXTURES],
            bootstrap_servers=bootstrap_servers,
        )
        self.logger = logging.getLogger("FixtureLoadService")

    def process_transformed_fixtures(self, key: str, payload: Dict[str, Any]) -> None:
        """Callback triggered whenever a transformed-fixtures message arrives."""
        try:
            league_id = payload.get("league_id")
            season = payload.get("season", "unknown")
            fixtures = payload.get("fixtures", [])

            self.logger.info(
                "Received %d transformed matches for league_id=%s, season='%s'.",
                len(fixtures), league_id, season,
            )

            result = load_fixtures(
                fixtures=fixtures,
                league_id=int(league_id) if league_id is not None else 0,
                season=season,
            )
            self.logger.info(
                "Successfully persisted %d matches to DB.", result.get("loaded_matches", 0)
            )

        except Exception as exc:
            self.logger.error("Error loading fixtures into database: %s", exc)
            raise

    def start(self) -> None:
        """Start listening loop for transformed fixtures."""
        self.logger.info(
            "Service started. Listening on topic: '%s'...", config.TOPIC_TRANSFORMED_FIXTURES
        )
        try:
            self.consumer.consume_stream(self.process_transformed_fixtures)
        finally:
            self.logger.info("Load Service stopped.")

    def stop(self) -> None:
        """Stop consumer loop."""
        self.consumer.stop()
