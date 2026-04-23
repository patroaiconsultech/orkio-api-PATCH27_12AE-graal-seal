"""PATCH v6.9.0 — provider checkout billing

Revision ID: 0031_patch_provider_checkout_billing
Revises: 0030_patch_billing_actuals_for_valuation
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0031_patch_provider_checkout_billing"
down_revision = "0030_patch_billing_actuals_for_valuation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_checkouts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("plan_code", sa.String(), nullable=False),
        sa.Column("plan_name", sa.String(), nullable=False),
        sa.Column("amount_brl", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(), nullable=False, server_default="BRL"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("access_source", sa.String(), nullable=False, server_default="payment"),
        sa.Column("provider", sa.String(), nullable=False, server_default="asaas"),
        sa.Column("provider_checkout_id", sa.String(), nullable=True),
        sa.Column("provider_payment_id", sa.String(), nullable=True),
        sa.Column("provider_url", sa.String(), nullable=True),
        sa.Column("callback_success_url", sa.String(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("confirmed_at", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_billing_checkouts_org_email", "billing_checkouts", ["org_slug", "email"])
    op.create_index("ix_billing_checkouts_provider_checkout", "billing_checkouts", ["provider", "provider_checkout_id"])

    op.create_table(
        "billing_webhook_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False, server_default="asaas"),
        sa.Column("provider_event_key", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processed_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_billing_webhooks_provider_event", "billing_webhook_events", ["provider", "provider_event_key"], unique=True)

    op.create_table(
        "billing_entitlements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("plan_code", sa.String(), nullable=False),
        sa.Column("plan_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("access_source", sa.String(), nullable=False, server_default="payment"),
        sa.Column("checkout_id", sa.String(), nullable=True),
        sa.Column("provider_customer_id", sa.String(), nullable=True),
        sa.Column("provider_subscription_id", sa.String(), nullable=True),
        sa.Column("starts_at", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.BigInteger(), nullable=True),
        sa.Column("last_payment_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_billing_entitlements_org_email", "billing_entitlements", ["org_slug", "email"], unique=True)


def downgrade():
    op.drop_index("ix_billing_entitlements_org_email", table_name="billing_entitlements")
    op.drop_table("billing_entitlements")
    op.drop_index("ix_billing_webhooks_provider_event", table_name="billing_webhook_events")
    op.drop_table("billing_webhook_events")
    op.drop_index("ix_billing_checkouts_provider_checkout", table_name="billing_checkouts")
    op.drop_index("ix_billing_checkouts_org_email", table_name="billing_checkouts")
    op.drop_table("billing_checkouts")
