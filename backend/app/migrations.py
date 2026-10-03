"""Serialize schema upgrades and check readiness without startup ALTER races."""

from pathlib import Path
from contextlib import contextmanager

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine


def migration_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.attributes["quiet"] = True
    return config


@contextmanager
def serialized_migration_connection(engine: Engine):
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            # Batch migrations rebuild tables. Disable FK checking outside the
            # transaction, serialize with BEGIN IMMEDIATE, and check before commit.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            connection.begin()
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(7162031002)")
        try:
            yield connection
            if engine.dialect.name == "sqlite":
                if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchone():
                    raise RuntimeError("Migration found invalid foreign key references")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()


def upgrade_schema(engine: Engine) -> None:
    config = migration_config()
    with serialized_migration_connection(engine) as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def require_current_schema(engine: Engine) -> None:
    config = migration_config()
    with engine.connect() as connection:
        heads = MigrationContext.configure(connection).get_current_heads()
    if set(heads) != set(ScriptDirectory.from_config(config).get_heads()):
        raise RuntimeError("Database schema is outdated; run python -m app.migrations")


if __name__ == "__main__":
    from .database import engine

    upgrade_schema(engine)
