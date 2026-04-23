"""PATCH v6.4 — reconcile realtime schema with current ORM

Revision ID: 0026_patch_v64_realtime_schema_reconcile
Revises: 0025_patch_v63_schema_drift_reconcile
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text as sa_text


revision = "0026_patch_v64_realtime_schema_reconcile"
down_revision = "0025_patch_v63_schema_drift_reconcile"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        sa_text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            LIMIT 1
            """
        ),
        {"table_name": table_name},
    ).fetchone()
    return row is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        sa_text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).fetchone()
    return row is not None


def _index_exists(conn, index_name: str) -> bool:
    row = conn.execute(
        sa_text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND indexname = :index_name
            LIMIT 1
            """
        ),
        {"index_name": index_name},
    ).fetchone()
    return row is not None


def _add_column_if_missing(conn, table_name: str, column: sa.Column) -> None:
    if not _table_exists(conn, table_name):
        return
    if _column_exists(conn, table_name, column.name):
        return
    op.add_column(table_name, column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    conn = op.get_bind()
    if not _table_exists(conn, table_name):
        return
    if _index_exists(conn, index_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    conn = op.get_bind()

    # -----------------------------------------------------------------
    # realtime_sessions
    # ORM expects:
    # id, org_slug, thread_id, agent_id, agent_name, user_id, user_name,
    # model, voice, started_at, ended_at, meta
    # -----------------------------------------------------------------
    if _table_exists(conn, "realtime_sessions"):
        _add_column_if_missing(conn, "realtime_sessions", sa.Column("agent_id", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_sessions", sa.Column("agent_name", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_sessions", sa.Column("user_id", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_sessions", sa.Column("user_name", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_sessions", sa.Column("model", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_sessions", sa.Column("voice", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_sessions", sa.Column("meta", sa.Text(), nullable=True))

        _create_index_if_missing("ix_realtime_sessions_org_slug", "realtime_sessions", ["org_slug"])
        _create_index_if_missing("ix_realtime_sessions_thread_id", "realtime_sessions", ["thread_id"])
        _create_index_if_missing("ix_realtime_sessions_agent_id", "realtime_sessions", ["agent_id"])
        _create_index_if_missing("ix_realtime_sessions_user_id", "realtime_sessions", ["user_id"])

    # -----------------------------------------------------------------
    # realtime_events
    # ORM expects:
    # id, org_slug, session_id, thread_id, role, agent_id, agent_name,
    # event_type, content, transcript_punct, created_at, client_event_id, meta
    # -----------------------------------------------------------------
    if _table_exists(conn, "realtime_events"):
        _add_column_if_missing(conn, "realtime_events", sa.Column("org_slug", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_events", sa.Column("thread_id", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_events", sa.Column("role", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_events", sa.Column("agent_id", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_events", sa.Column("agent_name", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_events", sa.Column("content", sa.Text(), nullable=True))
        _add_column_if_missing(conn, "realtime_events", sa.Column("transcript_punct", sa.Text(), nullable=True))
        _add_column_if_missing(conn, "realtime_events", sa.Column("client_event_id", sa.String(), nullable=True))
        _add_column_if_missing(conn, "realtime_events", sa.Column("meta", sa.Text(), nullable=True))

        _create_index_if_missing("ix_realtime_events_session_id", "realtime_events", ["session_id"])
        _create_index_if_missing("ix_realtime_events_created_at", "realtime_events", ["created_at"])
        _create_index_if_missing("ix_realtime_events_event_type", "realtime_events", ["event_type"])
        _create_index_if_missing("ix_realtime_events_org_slug", "realtime_events", ["org_slug"])
        _create_index_if_missing("ix_realtime_events_thread_id", "realtime_events", ["thread_id"])
        _create_index_if_missing(
            "ux_realtime_events_org_sess_client_eid",
            "realtime_events",
            ["org_slug", "session_id", "client_event_id"],
            unique=True,
        )


def downgrade() -> None:
    # Deliberately no-op.
    # Production reconcile migration; safe rollback should be data-aware.
    pass
