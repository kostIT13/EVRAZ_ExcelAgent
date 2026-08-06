"""Alembic environment configuration for EVRAZ_AGENT.

Uses offline mode by default so that migrations can be generated
without a running PostgreSQL instance.
"""

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Загружаем .env перед импортом settings
load_dotenv()

from src.core.db.base import Base  # noqa: E402
from src.core.db.models import (  # noqa: E402
    Cell,
    ColumnMetadata,
    EntityDictionary,
    ExcelComment,
    FactPrice,
    File,
    GoldenDataset,
    QueryCache,
    QueryLog,
    Sheet,
)
from src.core.config import settings  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url from settings
# Используем psycopg2 (синхронный) для online-миграций
config.set_main_option(
    "sqlalchemy.url",
    f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}",
)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Не требует подключения к БД — подходит для генерации миграций локально.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Требует работающего PostgreSQL.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
