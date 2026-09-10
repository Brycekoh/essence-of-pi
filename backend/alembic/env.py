"""Alembic environment.

`target_metadata` is the table definitions in app/services/sql_store.py, so
`alembic revision --autogenerate` diffs against the code the app actually runs.
tests/test_migrations.py asserts that diff is empty after `upgrade head`.
"""

from logging.config import fileConfig

from alembic import context

from app.config import Settings
from app.services.sql_store import make_engine, metadata

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False, or running migrations inside pytest
    # silently switches off every logger the test session had configured.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = metadata


def _url() -> str:
    # An explicit URL on the config wins -- the migration tests use that.
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    url = Settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set, so there is no database to migrate.")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Batch mode lets future ALTERs work on SQLite too. Harmless on
            # Postgres, where it simply emits normal ALTER statements.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
