"""The migrations must build exactly the schema the code uses.

There are two descriptions of the schema: the tables in sql_store.py, which
the app queries, and the migration, which creates them. Two descriptions drift.
This runs `alembic upgrade head` on an empty database and asks Alembic's own
autogenerate to diff the result against sql_store.py -- an empty diff is the
only passing answer.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.services.sql_store import make_engine, metadata

from .test_store_contract import PG_URL, POSTGRES

BACKEND = Path(__file__).resolve().parents[1]


def _config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    # configparser treats % as interpolation, so escape it in the URL.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _reset_postgres() -> None:
    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _not_version_table(name, type_, parent_names) -> bool:
    return not (type_ == "table" and name == "alembic_version")


@pytest.fixture(params=["sqlite", "postgres"])
def db_url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"
        return
    if not POSTGRES:
        pytest.skip("needs Postgres on TEST_DATABASE_URL")
    _reset_postgres()
    yield PG_URL
    _reset_postgres()


def test_migrations_build_exactly_the_schema_the_code_uses(db_url):
    command.upgrade(_config(db_url), "head")

    engine = make_engine(db_url)
    with engine.connect() as conn:
        context = MigrationContext.configure(
            conn,
            opts={
                # SQLite's type affinity makes type comparison noise; Postgres
                # is where a VARCHAR(64)-vs-TEXT mismatch actually means something.
                "compare_type": engine.dialect.name == "postgresql",
                "include_name": _not_version_table,
            },
        )
        diff = compare_metadata(context, metadata)
    engine.dispose()

    assert diff == [], f"the migration and sql_store.py disagree: {diff}"


def test_migrations_downgrade_cleanly_and_come_back(db_url):
    cfg = _config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = make_engine(db_url)
    left = set(inspect(engine).get_table_names()) - {"alembic_version"}
    engine.dispose()
    assert left == set(), f"downgrade left tables behind: {left}"

    command.upgrade(cfg, "head")  # and up again, from a downgraded database
