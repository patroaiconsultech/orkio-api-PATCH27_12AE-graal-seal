"""patch v3.4.0 thread meta for board/memory context

Revision ID: 0021_patch_v340_thread_meta
Revises: 0020_patch_v331a_onboarding_profile
Create Date: 2026-03-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_patch_v340_thread_meta"
down_revision = "0020_patch_v331a_onboarding_profile"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("threads") as batch_op:
        batch_op.add_column(sa.Column("meta", sa.Text(), nullable=True))

def downgrade():
    with op.batch_alter_table("threads") as batch_op:
        batch_op.drop_column("meta")
