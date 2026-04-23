"""PATCH v6.7.0 — billing actuals for valuation

Revision ID: 0030_patch_billing_actuals_for_valuation
Revises: 0029_patch_valuation_dashboard
Create Date: 2026-04-17
"""

from alembic import op
from sqlalchemy import text as sa_text

revision = "0030_patch_billing_actuals_for_valuation"
down_revision = "0029_patch_valuation_dashboard"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS billing_transactions (
            id VARCHAR PRIMARY KEY,
            org_slug VARCHAR NOT NULL,
            user_id VARCHAR NULL,
            payer_email VARCHAR NULL,
            payer_name VARCHAR NULL,
            provider VARCHAR NOT NULL DEFAULT 'manual',
            external_ref VARCHAR NULL,
            subscription_key VARCHAR NULL,
            plan_code VARCHAR NULL,
            charge_kind VARCHAR NOT NULL DEFAULT 'recurring',
            currency VARCHAR NOT NULL DEFAULT 'USD',
            amount_original NUMERIC(12,2) NULL,
            amount_usd NUMERIC(12,2) NOT NULL DEFAULT 0,
            normalized_mrr_usd NUMERIC(12,2) NULL,
            status VARCHAR NOT NULL DEFAULT 'confirmed',
            occurred_at BIGINT NULL,
            confirmed_at BIGINT NULL,
            notes TEXT NULL,
            created_by VARCHAR NULL,
            created_at BIGINT NOT NULL
        )
    """))
    conn.execute(sa_text("CREATE INDEX IF NOT EXISTS ix_billing_transactions_org_status_confirmed ON billing_transactions (org_slug, status, confirmed_at)"))
    conn.execute(sa_text("CREATE INDEX IF NOT EXISTS ix_billing_transactions_org_subscription ON billing_transactions (org_slug, subscription_key)"))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa_text("DROP INDEX IF EXISTS ix_billing_transactions_org_subscription"))
    conn.execute(sa_text("DROP INDEX IF EXISTS ix_billing_transactions_org_status_confirmed"))
    conn.execute(sa_text("DROP TABLE IF EXISTS billing_transactions"))
