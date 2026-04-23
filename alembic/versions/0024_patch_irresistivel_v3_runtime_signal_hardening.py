"""Patch Irresistivel v3 runtime signal hardening

Revision ID: 0024_patch_irresistivel_v3_runtime_signal_hardening
Revises: 0023_patch_irresistivel_v2_planner_analytics
Create Date: 2026-04-02 01:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_patch_irresistivel_v3_runtime_signal_hardening"
down_revision = "0023_patch_irresistivel_v2_planner_analytics"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("trial_states") as batch_op:
        batch_op.add_column(sa.Column("last_activation_score", sa.Integer(), nullable=True))

def downgrade():
    with op.batch_alter_table("trial_states") as batch_op:
        batch_op.drop_column("last_activation_score")
