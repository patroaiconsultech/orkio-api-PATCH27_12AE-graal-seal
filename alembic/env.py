from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.db import Base
from app import models  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _clean_env_value(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().strip('"').strip("'")


def _db_url() -> str:
    """
    Resolve a database URL compatible with Railway / SQLAlchemy / Alembic.

    Priority:
    1. DATABASE_PUBLIC_URL
    2. DATABASE_URL_PUBLIC
    3. DATABASE_URL
    """
    url = (
        _clean_env_value(os.getenv("DATABASE_PUBLIC_URL"))
        or _clean_env_value(os.getenv("DATABASE_URL_PUBLIC"))
        or _clean_env_value(os.getenv("DATABASE_URL"))
    )

    if not url:
        raise RuntimeError(
            "Alembic could not resolve a database URL. "
            "Set DATABASE_PUBLIC_URL, DATABASE_URL_PUBLIC, or DATABASE_URL."
        )

    # Normalize Railway internal hostname casing
    url = url.replace("Postgres.railway.internal", "postgres.railway.internal")

    # Normalize SQLAlchemy driver prefix
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    return url


def run_migrations_offline() -> None:
    url = _db_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _db_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Recovery de produção:
        # Se o schema já existe (ex.: tabela users),
        # e a tabela alembic_version existe mas está vazia,
        # grava a revisão correta para impedir replay do 0001_init.
        try:
            has_users = connection.execute(
                text("select to_regclass('public.users')")
            ).scalar()

            has_alembic = connection.execute(
                text("select to_regclass('public.alembic_version')")
            ).scalar()

            if has_users and has_alembic:
                count = connection.execute(
                    text("select count(*) from alembic_version")
                ).scalar()

                if count == 0:
                    connection.execute(
                        text(
                            "insert into alembic_version (version_num) "
                            "values ('0026_patch_v64_realtime_schema_reconcile')"
                        )
                    )
                    connection.commit()
        except Exception:
            # Nunca derrubar migrations por causa do recovery defensivo
            pass

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
