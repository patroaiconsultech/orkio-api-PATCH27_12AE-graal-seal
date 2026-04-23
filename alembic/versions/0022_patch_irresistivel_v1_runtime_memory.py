"""Patch Irresistivel v1 runtime persistence

Revision ID: 0022_patch_irresistivel_v1_runtime_memory
Revises: 0021_patch_v340_thread_meta
Create Date: 2026-04-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_patch_irresistivel_v1_runtime_memory"
down_revision = "0021_patch_v340_thread_meta"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "runtime_memories",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("memory_key", sa.String(), nullable=False),
        sa.Column("memory_value", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("confidence", sa.Numeric(4,2), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_runtime_memories_org_user_key", "runtime_memories", ["org_slug", "user_id", "memory_key"], unique=False)
    op.create_table(
        "trial_states",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("trial_started_at", sa.BigInteger(), nullable=False),
        sa.Column("last_seen_at", sa.BigInteger(), nullable=False),
        sa.Column("activation_level", sa.String(), nullable=True),
        sa.Column("conversion_readiness", sa.String(), nullable=True),
        sa.Column("recommended_next_action", sa.String(), nullable=True),
        sa.Column("numerology_invited_at", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_trial_states_org_user", "trial_states", ["org_slug", "user_id"], unique=True)
    op.create_table(
        "numerology_profiles",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("preferred_name", sa.String(), nullable=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("birth_date", sa.String(), nullable=False),
        sa.Column("context", sa.String(), nullable=True),
        sa.Column("profile_json", sa.Text(), nullable=False),
        sa.Column("consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confirmed_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_numerology_profiles_org_user", "numerology_profiles", ["org_slug", "user_id"], unique=False)

def downgrade():
    op.drop_index("ix_numerology_profiles_org_user", table_name="numerology_profiles")
    op.drop_table("numerology_profiles")
    op.drop_index("ix_trial_states_org_user", table_name="trial_states")
    op.drop_table("trial_states")
    op.drop_index("ix_runtime_memories_org_user_key", table_name="runtime_memories")
    op.drop_table("runtime_memories")
