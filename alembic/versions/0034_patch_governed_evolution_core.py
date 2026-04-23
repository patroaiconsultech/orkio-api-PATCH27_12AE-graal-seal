"""PATCH v7.3.0 — governed evolution core

Revision ID: 0034_patch_governed_evolution_core
Revises: 0033_patch_hybrid_wallet_billing
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_patch_governed_evolution_core"
down_revision = "0033_patch_hybrid_wallet_billing"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evolution_proposals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False, server_default="system"),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="awaiting_master_approval"),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("finding_json", sa.Text(), nullable=True),
        sa.Column("issue_json", sa.Text(), nullable=True),
        sa.Column("decision_json", sa.Text(), nullable=True),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("rejection_note", sa.Text(), nullable=True),
        sa.Column("first_detected_at", sa.BigInteger(), nullable=False),
        sa.Column("last_detected_at", sa.BigInteger(), nullable=False),
        sa.Column("detected_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("approved_at", sa.BigInteger(), nullable=True),
        sa.Column("rejected_by", sa.String(), nullable=True),
        sa.Column("rejected_at", sa.BigInteger(), nullable=True),
        sa.Column("last_trace_id", sa.String(), nullable=True),
        sa.Column("last_execution_status", sa.String(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_evolution_proposals_org_status", "evolution_proposals", ["org_slug", "status"])
    op.create_index("ix_evolution_proposals_status_updated", "evolution_proposals", ["status", "updated_at"])
    op.create_index("ux_evolution_proposals_fingerprint", "evolution_proposals", ["fingerprint"], unique=True)

    op.create_table(
        "evolution_executions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False, server_default="system"),
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False, server_default="manual"),
        sa.Column("actor_ref", sa.String(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("started_at", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_evolution_executions_proposal_created", "evolution_executions", ["proposal_id", "created_at"])
    op.create_index("ix_evolution_executions_status_created", "evolution_executions", ["status", "created_at"])


def downgrade():
    op.drop_index("ix_evolution_executions_status_created", table_name="evolution_executions")
    op.drop_index("ix_evolution_executions_proposal_created", table_name="evolution_executions")
    op.drop_table("evolution_executions")

    op.drop_index("ux_evolution_proposals_fingerprint", table_name="evolution_proposals")
    op.drop_index("ix_evolution_proposals_status_updated", table_name="evolution_proposals")
    op.drop_index("ix_evolution_proposals_org_status", table_name="evolution_proposals")
    op.drop_table("evolution_proposals")
