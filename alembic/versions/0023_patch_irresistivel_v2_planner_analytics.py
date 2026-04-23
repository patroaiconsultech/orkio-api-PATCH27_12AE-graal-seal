"""Patch Irresistivel v2 planner analytics

Revision ID: 0023_patch_irresistivel_v2_planner_analytics
Revises: 0022_patch_irresistivel_v1_runtime_memory
Create Date: 2026-04-02 00:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_patch_irresistivel_v2_planner_analytics"
down_revision = "0022_patch_irresistivel_v1_runtime_memory"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "trial_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("event_name", sa.String(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_trial_events_org_user_created", "trial_events", ["org_slug", "user_id", "created_at"], unique=False)

def downgrade():
    op.drop_index("ix_trial_events_org_user_created", table_name="trial_events")
    op.drop_table("trial_events")
