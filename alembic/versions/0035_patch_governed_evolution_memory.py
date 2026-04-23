"""patch governed evolution memory

Revision ID: 0035_patch_governed_evolution_memory
Revises: 0034_patch_governed_evolution_core
Create Date: 2026-04-20

"""
from alembic import op
import sqlalchemy as sa

revision = "0035_patch_governed_evolution_memory"
down_revision = "0034_patch_governed_evolution_core"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("evolution_proposals") as batch:
        batch.add_column(sa.Column("domain_scope", sa.String(), nullable=True))
        batch.add_column(sa.Column("recurrence_window_count", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("blast_radius_accumulated", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("security_accumulated", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_priority_score", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_recommendation", sa.String(), nullable=True))
        batch.add_column(sa.Column("last_cadence_seconds", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "evolution_signal_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False, server_default="system"),
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("domain_scope", sa.String(), nullable=True),
        sa.Column("recurrence_window_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("blast_radius_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("security_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priority_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommendation", sa.String(), nullable=True),
        sa.Column("cadence_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("policy_version", sa.String(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_evolution_signal_snapshots_proposal_created", "evolution_signal_snapshots", ["proposal_id", "created_at"])
    op.create_index("ix_evolution_signal_snapshots_fingerprint_created", "evolution_signal_snapshots", ["fingerprint", "created_at"])

    op.create_table(
        "evolution_cycle_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False, server_default="system"),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("findings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("classified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposals_touched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposals_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposals_suppressed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_priority_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_priority_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_interval_suggested_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommendation_buckets_json", sa.Text(), nullable=True),
        sa.Column("domain_buckets_json", sa.Text(), nullable=True),
        sa.Column("top_queue_json", sa.Text(), nullable=True),
        sa.Column("policy_version", sa.String(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_evolution_cycle_logs_created", "evolution_cycle_logs", ["created_at"])


def downgrade():
    op.drop_index("ix_evolution_cycle_logs_created", table_name="evolution_cycle_logs")
    op.drop_table("evolution_cycle_logs")

    op.drop_index("ix_evolution_signal_snapshots_fingerprint_created", table_name="evolution_signal_snapshots")
    op.drop_index("ix_evolution_signal_snapshots_proposal_created", table_name="evolution_signal_snapshots")
    op.drop_table("evolution_signal_snapshots")

    with op.batch_alter_table("evolution_proposals") as batch:
        batch.drop_column("last_cadence_seconds")
        batch.drop_column("last_recommendation")
        batch.drop_column("last_priority_score")
        batch.drop_column("security_accumulated")
        batch.drop_column("blast_radius_accumulated")
        batch.drop_column("recurrence_window_count")
        batch.drop_column("domain_scope")
