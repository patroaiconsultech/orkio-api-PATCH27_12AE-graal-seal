"""PATCH v6.4.3 — files.thread_id reconcile

Revision ID: 0027_patch_v643_files_thread_id_reconcile
Revises: 0026_patch_v64_realtime_schema_reconcile
Create Date: 2026-04-06
"""

from alembic import op
from sqlalchemy import text as sa_text

revision = "0027_patch_v643_files_thread_id_reconcile"
down_revision = "0026_patch_v64_realtime_schema_reconcile"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    conn.execute(sa_text("""
        ALTER TABLE files
        ADD COLUMN IF NOT EXISTS thread_id UUID NULL
    """))

    conn.execute(sa_text("""
        CREATE INDEX IF NOT EXISTS ix_files_thread_id
        ON files (thread_id)
    """))


def downgrade():
    conn = op.get_bind()

    conn.execute(sa_text("""
        DROP INDEX IF EXISTS ix_files_thread_id
    """))

    conn.execute(sa_text("""
        ALTER TABLE files
        DROP COLUMN IF EXISTS thread_id
    """))
