"""PATCH v6.6.0 — valuation dashboard

Revision ID: 0029_patch_valuation_dashboard
Revises: 0028_patch_trademark_center_intel
Create Date: 2026-04-17
"""

from alembic import op
from sqlalchemy import text as sa_text

revision = "0029_patch_valuation_dashboard"
down_revision = "0028_patch_trademark_center_intel"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS valuation_configs (
            id VARCHAR PRIMARY KEY,
            org_slug VARCHAR NOT NULL,
            paid_users_override INTEGER NULL,
            individual_price_usd NUMERIC(12,2) NOT NULL DEFAULT 20,
            pro_price_usd NUMERIC(12,2) NOT NULL DEFAULT 49,
            team_base_price_usd NUMERIC(12,2) NOT NULL DEFAULT 99,
            team_seat_price_usd NUMERIC(12,2) NOT NULL DEFAULT 20,
            individual_share_pct NUMERIC(8,2) NOT NULL DEFAULT 50,
            pro_share_pct NUMERIC(8,2) NOT NULL DEFAULT 30,
            team_share_pct NUMERIC(8,2) NOT NULL DEFAULT 20,
            avg_team_size NUMERIC(8,2) NOT NULL DEFAULT 5,
            monthly_setup_revenue_usd NUMERIC(12,2) NOT NULL DEFAULT 0,
            monthly_enterprise_mrr_usd NUMERIC(12,2) NOT NULL DEFAULT 0,
            low_arr_multiple NUMERIC(8,2) NOT NULL DEFAULT 8,
            base_arr_multiple NUMERIC(8,2) NOT NULL DEFAULT 12,
            high_arr_multiple NUMERIC(8,2) NOT NULL DEFAULT 18,
            notes TEXT NULL,
            updated_by VARCHAR NULL,
            updated_at BIGINT NOT NULL
        )
    """))
    conn.execute(sa_text("CREATE UNIQUE INDEX IF NOT EXISTS ix_valuation_configs_org_unique ON valuation_configs (org_slug)"))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa_text("DROP INDEX IF EXISTS ix_valuation_configs_org_unique"))
    conn.execute(sa_text("DROP TABLE IF EXISTS valuation_configs"))
