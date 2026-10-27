import atexit
import os

import pytest
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

_pg = PostgresContainer("postgres:16-alpine")
_pg.start()
atexit.register(_pg.stop)

os.environ["DATABASE_URL"] = _pg.get_connection_url()
os.environ.setdefault("API_TOKEN", "test-token")


@pytest.fixture(autouse=True)
def database():
    """Fresh schema and one seeded league before every test."""
    from src.database.connection import engine, get_session
    from src.database.models import Base

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_session() as session:
        session.execute(text(
            "INSERT INTO dim_leagues (league_id, league_name, country_code) "
            "VALUES (47, 'Premier League', 'ENG')"
        ))
    yield