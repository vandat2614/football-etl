"""
Centralized Configuration Module.
Loads settings from environment variables (or .env file) with sensible defaults.
All project modules can import configuration values directly from src.config.
"""

import os
from pathlib import Path

# Base Paths
CONFIG_DIR = Path(__file__).resolve().parent
SRC_DIR = CONFIG_DIR.parent
EXPERIMENT_DIR = SRC_DIR.parent

# Attempt to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv

    _env_file = EXPERIMENT_DIR / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass

# Database
DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

# Kafka
KAFKA_BOOTSTRAP_SERVERS: str = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "")
KAFKA_SECURITY_PROTOCOL: str = os.environ.get("KAFKA_SECURITY_PROTOCOL", "")

# SSL certificates (required when KAFKA_SECURITY_PROTOCOL = "SSL")
KAFKA_SSL_CA_LOCATION: str = os.environ.get("KAFKA_SSL_CA_LOCATION", "")
KAFKA_SSL_CERT_LOCATION: str = os.environ.get("KAFKA_SSL_CERT_LOCATION", "")
KAFKA_SSL_KEY_LOCATION: str = os.environ.get("KAFKA_SSL_KEY_LOCATION", "")

# Topic names
TOPIC_RAW_FIXTURES: str = os.environ.get("TOPIC_RAW_FIXTURES", "raw-fixtures")
TOPIC_TRANSFORMED_FIXTURES: str = os.environ.get("TOPIC_TRANSFORMED_FIXTURES", "transformed-fixtures")

# Consumer group IDs
KAFKA_TRANSFORM_GROUP_ID: str = os.environ.get("KAFKA_TRANSFORM_GROUP_ID", "fixtures-transformer-group")
KAFKA_LOAD_GROUP_ID: str = os.environ.get("KAFKA_LOAD_GROUP_ID", "fixtures-loader-group")

# Logging
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FILE: str = os.environ.get("LOG_FILE", str(EXPERIMENT_DIR / "logs" / "etl.log"))

# Leagues Config (stored in src/config/leagues.json)
LEAGUES_CONFIG_FILE: Path = CONFIG_DIR / "leagues.json"
DEFAULT_SEASON: str = os.environ.get("DEFAULT_SEASON", "2025-2026")

# Crawl state API (used by the scheduler instead of a direct DB connection)
API_URL: str = os.environ.get("API_URL", "")
API_TOKEN: str = os.environ.get("API_TOKEN", "")