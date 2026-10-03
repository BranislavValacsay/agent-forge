"""Alembic configuration shared by the CLI and controlled startup migrations."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.database import Base
from app.migrations import serialized_migration_connection
from app import models  # noqa: F401

config = context.config
if config.config_file_name and not config.attributes.get("quiet"):
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def configure(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Use online migrations: baseline adoption requires schema inspection")
elif config.attributes.get("connection") is not None:
    configure(config.attributes["connection"])
else:
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with serialized_migration_connection(connectable) as connection:
        configure(connection)
