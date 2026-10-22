"""
Fixture Transform Service Module.
Continuous stream consumer that listens to raw fixture events,
transforms them into clean records, and publishes to downstream topic.
"""

import logging
from typing import Any, Dict

import src.config as config
from src.kafka import BaseKafkaConsumer, BaseKafkaProducer
from .fixtures import transform_fixtures

logger = logging.getLogger("FixtureTransformService")


class FixtureTransformService:
    """
    Kafka Stream Consumer Service for transforming raw fixtures into clean records.
    """

    def __init__(self, bootstrap_servers: str = None):
        self.producer = BaseKafkaProducer(bootstrap_servers=bootstrap_servers)
        self.consumer = BaseKafkaConsumer(
            group_id=config.KAFKA_TRANSFORM_GROUP_ID,
            topics=[config.TOPIC_RAW_FIXTURES],
            bootstrap_servers=bootstrap_servers,
        )
        self.logger = logging.getLogger("FixtureTransformService")

    def process_raw_fixtures(self, key: str, payload: Dict[str, Any]) -> None:
        """Callback triggered whenever a raw-fixtures message arrives."""
        try:
            league_id = payload.get("league_id")
            season = payload.get("season", "unknown")
            
            raw_fixtures = payload.get("fixtures", [])
            trigger_reason = payload.get("trigger_reason")
            crawled_at = payload.get("crawled_at")

            self.logger.info(
                "Received %d raw matches for league_id=%s, season='%s'.",
                len(raw_fixtures), league_id, season,
            )

            cleaned_fixtures = transform_fixtures(raw_fixtures)

            forward_payload = {
                "league_id": league_id,
                "season": season,
                "fixtures": cleaned_fixtures,
                "count": len(cleaned_fixtures),
                "trigger_reason": trigger_reason,
                "crawled_at": crawled_at,
            }
            partition_key = str(key or league_id)

            self.producer.produce_message(
                topic=config.TOPIC_TRANSFORMED_FIXTURES,
                key=partition_key,
                value=forward_payload,
            )
            self.logger.info(
                "Transformed and published %d matches to '%s' (key=%s).",
                len(cleaned_fixtures), config.TOPIC_TRANSFORMED_FIXTURES, partition_key,
            )

        except Exception as exc:
            self.logger.error("Error processing raw fixtures: %s", exc)
            raise

    def start(self) -> None:
        """Start listening loop for raw fixtures."""
        self.logger.info(
            "Service started. Listening on topic: '%s'...", config.TOPIC_RAW_FIXTURES
        )
        try:
            self.consumer.consume_stream(self.process_raw_fixtures)
        finally:
            self.producer.flush()
            self.logger.info("Transform Service stopped.")

    def stop(self) -> None:
        """Stop consumer loop."""
        self.consumer.stop()
