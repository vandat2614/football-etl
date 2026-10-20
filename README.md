# Football Fixtures ETL Pipeline

An event-driven ETL pipeline that crawls football fixtures from FotMob,
streams data through Apache Kafka, and stores results in a database.

## Architecture

```
[Scheduler]          [Transform Service]       [Load Service]
    |                       |                       |
 Crawl FotMob  -->  raw-fixtures  -->  transformed-fixtures  -->  DB
 (Selenium)       (Kafka topic)    (Kafka topic)            (SQLite/PG)
```

- **Extract**: `scheduler.py` crawls fixtures using Selenium and publishes raw JSON to Kafka
- **Transform**: `transform/service.py` normalizes data (dates, scores, match status, stages)
- **Load**: `load/service.py` upserts teams and matches into the database via SQLAlchemy ORM

## Quick Start

### 1. Setup environment

```bash
cd experiment/
cp .env.example .env
# Edit .env with your Kafka credentials and database URL
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize database

```bash
python database/init_db.py
```

### 4. Start streaming services

```bash
# Start both Transform + Load services (runs until Ctrl+C)
python main.py --service all

# Or run them separately:
python main.py --service transform
python main.py --service load
```

### 5. Trigger a crawl

```bash
# Crawl all leagues for current season
python scheduler.py

# Crawl specific season
python scheduler.py --season 2024-2025

# Crawl single league
python scheduler.py --league 47

# Test crawl without publishing to Kafka
python scheduler.py --dry-run
```

## Running with Docker

### Start streaming services

```bash
# Build image (from project root)
docker-compose build

# Start transform + load services
docker-compose up -d transform-service load-service
```

### Initialize DB (one-time)

```bash
docker-compose run --rm db-init
```

### Trigger a crawl

```bash
docker-compose run --rm scheduler --season 2025-2026
```

## Automated Scheduling (GitHub Actions)

The pipeline includes a GitHub Actions workflow (`.github/workflows/crawl.yml`) that:

- **Runs automatically** every day at 22:00 UTC
- **Can be triggered manually** via GitHub UI with optional inputs (season, league, dry-run)
- Requires these GitHub Secrets:
  - `KAFKA_BOOTSTRAP_SERVERS`
  - `KAFKA_SECURITY_PROTOCOL`
  - `KAFKA_SSL_CA_LOCATION` *(for Aiven SSL)*
  - `KAFKA_SSL_CERT_LOCATION` *(for Aiven SSL)*
  - `KAFKA_SSL_KEY_LOCATION` *(for Aiven SSL)*

## Project Structure

```
experiment/
├── .env.example              # Environment variables template
├── .github/
│   └── workflows/
│       └── crawl.yml         # GitHub Actions scheduled crawl
├── config.py                 # Centralized configuration
├── logging_config.py         # Logging setup (console + rotating file)
├── scheduler.py              # ETL orchestrator (Extract phase)
├── main.py                   # Service runner (Transform + Load)
├── docker-compose.yml        # Container orchestration
├── Dockerfile                # Container image definition
├── requirements.txt          # Python dependencies
├── leagues.json              # League configuration
├── extract/
│   ├── crawler.py            # Fetches raw fixtures from FotMob
│   ├── fetcher.py            # Selenium HTTP fetcher
│   ├── parser.py             # HTML parser for fixture data
│   └── publisher.py         # Kafka producer for raw fixtures
├── transform/
│   ├── common.py             # Date, score, status helpers
│   ├── fixtures.py           # Core transformation logic
│   └── service.py            # Kafka consumer service
├── load/
│   ├── loader.py             # SQLAlchemy upsert logic
│   └── service.py            # Kafka consumer service
└── database/
    ├── models.py             # SQLAlchemy ORM models
    ├── connection.py         # Database engine + session factory
    ├── init_db.py            # Schema creation + seeding
    ├── repositories/
    │   └── fixtures.py       # FixtureRepository (CRUD operations)
    └── seeds/
        └── leagues.py        # League seed data
```

## Configuration

All settings are managed via environment variables. Copy `.env.example` to `.env`:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///football.db` | SQLAlchemy connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT` | `PLAINTEXT` or `SSL` |
| `SELENIUM_HEADLESS` | `true` | Run Chrome in headless mode |
| `DEFAULT_SEASON` | `2025-2026` | Season used when not specified |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Switching Database

This project uses SQLAlchemy ORM - switching database requires only changing `DATABASE_URL`:

```bash
# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/football_db

# MySQL
DATABASE_URL=mysql+pymysql://user:password@localhost/football_db
```

No code changes required.