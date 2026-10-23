# Football ETL

A streaming ETL pipeline for football fixtures. It crawls match schedules and results from FotMob, passes them through Kafka, cleans them, stores them in PostgreSQL, and serves them through a FastAPI backend and a small web dashboard.

Live demo: https://football-etl.duckdns.org
Interactive architecture page: https://football-etl.duckdns.org/architecture
API docs: https://football-etl.duckdns.org/docs

## How it works

```mermaid
flowchart LR
    S[Scheduler<br/>GitHub Actions] -->|POST /ingest| A[FastAPI]
    A -->|publish| K1[(raw-fixtures)]
    K1 --> T[Transform consumer]
    T --> K2[(transformed-fixtures)]
    K2 --> L[Load consumer]
    L --> P[(PostgreSQL)]
    P --> A
    A -->|GET /crawl-state| S
    A --> W[Web dashboard]
```

1. **Scheduler** runs every hour on GitHub Actions. It asks the API which leagues are due for a crawl, fetches fixtures for those leagues, and sends them to the API.
2. **API** publishes the raw fixtures of each league to the `raw-fixtures` topic. The scheduler never talks to Kafka or the database directly, so neither has to be exposed to the internet.
3. **Transform** consumer standardises team names, rounds, UTC times, scores and points, drops duplicate match ids, and publishes to `transformed-fixtures`.
4. **Load** consumer upserts the matches into PostgreSQL and records the crawl in `crawl_state_log`, including when the league should be crawled again.
5. **API and web** read from PostgreSQL to show fixtures, standings, head-to-head records and the crawl history.

### When a league is crawled again

The scheduler runs with `--only-due` and decides per league, based on the latest successful crawl:

| Reason | Condition |
|---|---|
| `periodic_refresh` | The league was never crawled, or the last crawl is 7 or more days old |
| `match_group_finished:<time>` | A group of matches has finished since the last crawl (last kickoff in the group plus a 3 hour buffer) |
| `manual` | The scheduler was started by hand |

Matches are grouped by UTC day, and a match that kicks off less than 4 hours after the latest kickoff of the previous group joins that group. After each crawl, the load step stores the end of the earliest pending group in `next_recrawl_at`.

## Stack

Python 3.12, Apache Kafka, PostgreSQL 16, SQLAlchemy 2, FastAPI, Docker Compose, nginx. The crawler uses `requests` and BeautifulSoup. The dashboard is plain HTML and JavaScript.

## Database

| Table | Purpose |
|---|---|
| `dim_leagues` | League id, name and country code, seeded from `src/config/leagues.json` |
| `dim_teams` | Teams |
| `fact_matches` | One row per match: teams, UTC kickoff, status, score, result and points |
| `crawl_state_log` | One row per crawl: league, season, status, trigger reason, number of newly finished matches, crawl time, next crawl time |

`fixtures_count` in `crawl_state_log` counts matches that became `FINISHED` in that crawl, not the size of the season.

## Running it

### Requirements

Docker with Compose, and a Kafka broker that the containers can reach. The compose file expects the broker on an external Docker network named `kafka_default`.

### Configuration

Create a `.env` file next to `docker-compose.yml`:

```ini
# PostgreSQL
POSTGRES_USER=football
POSTGRES_PASSWORD=change_me
POSTGRES_DB=football_etl
DATABASE_URL=postgresql+psycopg2://football:change_me@postgres:5432/football_etl

# Kafka (address of the internal listener, as seen from the containers)
KAFKA_BOOTSTRAP_SERVERS=kafka:19092
KAFKA_SECURITY_PROTOCOL=PLAINTEXT

# API
API_TOKEN=a_long_random_string
API_URL=https://your-domain.example

# Optional
DEFAULT_SEASON=2025-2026
LOG_LEVEL=INFO
```

Special characters in the database password must be URL-encoded inside `DATABASE_URL`.

### Start the stack

```bash
docker compose up -d --build
docker compose ps
```

This starts PostgreSQL, the transform and load consumers, and the API on `127.0.0.1:8000`. Put a reverse proxy such as nginx in front of it for HTTPS and to serve the files in `web/`.

### Create the tables and load history

```bash
# Tables, league seed, then import data/raw
docker compose run --rm -v "$(pwd)/data:/app/data" load python -m src.database.setup_db

# Drop everything first (asks for confirmation, add --yes to skip)
docker compose run --rm -v "$(pwd)/data:/app/data" load python -m src.database.setup_db --reset

# Only tables and seed, no history import
docker compose run --rm load python -m src.database.setup_db --skip-import
```

Historical data is expected as `data/raw/<season>/<league>.json`, for example `data/raw/2010_2011/bundesliga.json`. The importer also writes one `crawl_state_log` row per file so the dashboard has history to show.

### Run the scheduler by hand

```bash
python scheduler.py --only-due                    # crawl leagues that are due
python scheduler.py --league 47 --season 2025-2026
python scheduler.py --dry-run                     # crawl without sending anything
```

The scheduler needs only `API_URL` and `API_TOKEN`. The workflow in `.github/workflows/scheduler.yml` runs it every hour and can also be started manually.

## API

Public endpoints used by the dashboard (full list and parameters at `/docs`):

| Endpoint | Description |
|---|---|
| `GET /public/matches` | Paginated fixtures, filterable by league, season, round, status and team |
| `GET /public/standings` | League table for a season |
| `GET /public/h2h` | Head-to-head record of two teams |
| `GET /public/teams` | Team search |
| `GET /public/crawl-logs` | Crawl history |
| `GET /public/crawl-overview` | Latest crawl state per league and the next scheduled crawl |

Two endpoints require the header `Authorization: Bearer <API_TOKEN>` and are meant for the scheduler:

| Endpoint | Description |
|---|---|
| `GET /crawl-state` | Latest successful crawl per league |
| `POST /ingest` | Receive crawled fixtures and publish them to Kafka |

## Project layout

```
.github/workflows/scheduler.yml   hourly scheduler
scheduler.py                      crawl entry point
src/
  api/main.py                     FastAPI app
  config/                         settings and leagues.json
  database/                       models, repositories, setup_db, import_history
  kafka/                          producer and consumer wrappers
  services/                       extract, transform, load
  utils/crawl_state.py            due-date logic
web/                              dashboard and architecture page
docker-compose.yml
Dockerfile
```

## Limitations

- Only successful crawls are written to `crawl_state_log`. A crawl that fails before reaching the load step leaves no row.
- The Kafka listener used by the scheduler and the containers is plaintext. The broker is not reachable from the internet, but traffic inside the VM is not encrypted.
- Match data comes from FotMob's public pages, so the crawler may break if the page structure changes.

## Data and credits

Fixture data comes from FotMob. Team and league logos belong to their respective owners. This project is for learning and demonstration.