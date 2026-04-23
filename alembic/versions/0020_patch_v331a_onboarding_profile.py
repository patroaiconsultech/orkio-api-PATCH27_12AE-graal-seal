"""patch v3.3.1a strategic onboarding profile

Revision ID: 0020_patch_v331a_onboarding_profile
Revises: 0019_patch0100_28_3_idempotency
Create Date: 2026-03-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_patch_v331a_onboarding_profile"
down_revision = "0019"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("company", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("profile_role", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("user_type", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("intent", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE users SET onboarding_completed = FALSE WHERE onboarding_completed IS NULL")

def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("onboarding_completed")
        batch_op.drop_column("notes")
        batch_op.drop_column("intent")
        batch_op.drop_column("user_type")
        batch_op.drop_column("profile_role")
        batch_op.drop_column("company")
