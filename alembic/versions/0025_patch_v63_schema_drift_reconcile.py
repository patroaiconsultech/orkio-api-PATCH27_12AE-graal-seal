"""PATCH v6.3 — schema drift reconcile for production Railway

Revision ID: 0025_patch_v63_schema_drift_reconcile
Revises: None
Create Date: 2026-04-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text as sa_text


revision = "0025_patch_v63_schema_drift_reconcile"
down_revision = "0024_patch_irresistivel_v3_runtime_signal_hardening"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
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
    return result is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    result = conn.execute(
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
    return result is not None


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(
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
    return result is not None


def _add_column_if_missing(conn, table_name: str, column: sa.Column) -> None:
    if not _table_exists(conn, table_name):
        return
    if _column_exists(conn, table_name, column.name):
        return
    op.add_column(table_name, column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    conn = op.get_bind()
    if not _table_exists(conn, table_name):
        return
    if _index_exists(conn, index_name):
        return
    op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    conn = op.get_bind()

    # files table reconciliation
    _add_column_if_missing(conn, "files", sa.Column("original_filename", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "files", sa.Column("origin", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "files", sa.Column("scope_thread_id", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "files", sa.Column("scope_agent_id", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "files", sa.Column("uploader_id", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "files", sa.Column("uploader_name", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "files", sa.Column("uploader_email", sa.Text(), nullable=True))
    _add_column_if_missing(
        conn,
        "files",
        sa.Column("is_institutional", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    if _table_exists(conn, "files") and _column_exists(conn, "files", "origin"):
        op.execute("UPDATE files SET origin = 'unknown' WHERE origin IS NULL")
        op.execute("ALTER TABLE files ALTER COLUMN origin SET DEFAULT 'unknown'")

    if _table_exists(conn, "files") and _column_exists(conn, "files", "is_institutional"):
        op.execute("UPDATE files SET is_institutional = FALSE WHERE is_institutional IS NULL")
        op.execute("ALTER TABLE files ALTER COLUMN is_institutional SET DEFAULT FALSE")

    _create_index_if_missing("ix_files_origin", "files", ["origin"])
    _create_index_if_missing("ix_files_scope_thread", "files", ["scope_thread_id"])
    _create_index_if_missing("ix_files_scope_agent", "files", ["scope_agent_id"])

    # messages table reconciliation
    _add_column_if_missing(conn, "messages", sa.Column("agent_id", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "messages", sa.Column("agent_name", sa.Text(), nullable=True))
    _create_index_if_missing("ix_messages_agent_id", "messages", ["agent_id"])

    # users table reconciliation
    _add_column_if_missing(conn, "users", sa.Column("approved_at", sa.BigInteger(), nullable=True))
    _add_column_if_missing(conn, "users", sa.Column("signup_code_label", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "users", sa.Column("signup_source", sa.Text(), nullable=True))
    _add_column_if_missing(
        conn,
        "users",
        sa.Column("usage_tier", sa.Text(), nullable=True, server_default="summit_standard"),
    )
    _add_column_if_missing(conn, "users", sa.Column("terms_accepted_at", sa.BigInteger(), nullable=True))
    _add_column_if_missing(conn, "users", sa.Column("terms_version", sa.Text(), nullable=True))
    _add_column_if_missing(
        conn,
        "users",
        sa.Column("marketing_consent", sa.Boolean(), nullable=True, server_default=sa.text("false")),
    )
    _add_column_if_missing(conn, "users", sa.Column("company", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "users", sa.Column("profile_role", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "users", sa.Column("user_type", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "users", sa.Column("intent", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "users", sa.Column("notes", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "users", sa.Column("country", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "users", sa.Column("language", sa.Text(), nullable=True))
    _add_column_if_missing(conn, "users", sa.Column("whatsapp", sa.Text(), nullable=True))
    _add_column_if_missing(
        conn,
        "users",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    if _table_exists(conn, "users") and _column_exists(conn, "users", "onboarding_completed"):
        op.execute("UPDATE users SET onboarding_completed = FALSE WHERE onboarding_completed IS NULL")
        op.execute("ALTER TABLE users ALTER COLUMN onboarding_completed SET DEFAULT FALSE")

    if _table_exists(conn, "users") and _column_exists(conn, "users", "marketing_consent"):
        op.execute("UPDATE users SET marketing_consent = FALSE WHERE marketing_consent IS NULL")
        op.execute("ALTER TABLE users ALTER COLUMN marketing_consent SET DEFAULT FALSE")

    if _table_exists(conn, "users") and _column_exists(conn, "users", "usage_tier"):
        op.execute("UPDATE users SET usage_tier = 'summit_standard' WHERE usage_tier IS NULL")
        op.execute("ALTER TABLE users ALTER COLUMN usage_tier SET DEFAULT 'summit_standard'")


def downgrade() -> None:
    pass
