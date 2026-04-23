"""PATCH v7.2.0 — hybrid wallet billing

Revision ID: 0033_patch_hybrid_wallet_billing
Revises: 0032_patch_landing_cms_social_proof
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0033_patch_hybrid_wallet_billing"
down_revision = "0032_patch_landing_cms_social_proof"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_wallets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("balance_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("lifetime_credited_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("lifetime_debited_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("auto_recharge_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_recharge_pack_code", sa.String(), nullable=True),
        sa.Column("auto_recharge_threshold_usd", sa.Numeric(12, 4), nullable=True),
        sa.Column("low_balance_threshold_usd", sa.Numeric(12, 4), nullable=True, server_default="3"),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_billing_wallets_org_email", "billing_wallets", ["org_slug", "email"], unique=True)

    op.create_table(
        "billing_wallet_ledger",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False),
        sa.Column("wallet_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False, server_default="credit"),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("action_key", sa.String(), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=True),
        sa.Column("unit_price_usd", sa.Numeric(12, 4), nullable=True),
        sa.Column("amount_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("balance_after_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("external_ref", sa.String(), nullable=True),
        sa.Column("related_checkout_id", sa.String(), nullable=True),
        sa.Column("related_tx_id", sa.String(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_billing_wallet_ledger_wallet_created", "billing_wallet_ledger", ["wallet_id", "created_at"])
    op.create_index("ix_billing_wallet_ledger_org_email_created", "billing_wallet_ledger", ["org_slug", "email", "created_at"])
    op.create_index("ix_billing_wallet_ledger_external_ref", "billing_wallet_ledger", ["org_slug", "external_ref"])


def downgrade():
    op.drop_index("ix_billing_wallet_ledger_external_ref", table_name="billing_wallet_ledger")
    op.drop_index("ix_billing_wallet_ledger_org_email_created", table_name="billing_wallet_ledger")
    op.drop_index("ix_billing_wallet_ledger_wallet_created", table_name="billing_wallet_ledger")
    op.drop_table("billing_wallet_ledger")
    op.drop_index("ix_billing_wallets_org_email", table_name="billing_wallets")
    op.drop_table("billing_wallets")
