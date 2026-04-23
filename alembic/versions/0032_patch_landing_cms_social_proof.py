"""PATCH v7.1.0 — landing cms and social proof

Revision ID: 0032_patch_landing_cms_social_proof
Revises: 0031_patch_provider_checkout_billing
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0032_patch_landing_cms_social_proof"
down_revision = "0031_patch_provider_checkout_billing"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "social_proof_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False),
        sa.Column("page_key", sa.String(), nullable=False, server_default="landing_home"),
        sa.Column("kind", sa.String(), nullable=False, server_default="testimonial"),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("subtitle", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("person_name", sa.String(), nullable=True),
        sa.Column("person_role", sa.String(), nullable=True),
        sa.Column("company_name", sa.String(), nullable=True),
        sa.Column("company_site", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("logo_url", sa.String(), nullable=True),
        sa.Column("href", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("market_segment", sa.String(), nullable=True),
        sa.Column("metrics_json", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("proof_code", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("starts_at", sa.BigInteger(), nullable=True),
        sa.Column("ends_at", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("published_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_social_proof_items_org_kind_status", "social_proof_items", ["org_slug", "kind", "status"])
    op.create_index("ix_social_proof_items_org_sort", "social_proof_items", ["org_slug", "sort_order", "created_at"])
    op.create_index("ix_social_proof_items_org_featured", "social_proof_items", ["org_slug", "featured", "created_at"])

    op.create_table(
        "landing_content_blocks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_slug", sa.String(), nullable=False),
        sa.Column("page_key", sa.String(), nullable=False, server_default="landing_home"),
        sa.Column("block_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("subtitle", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("cta_label", sa.String(), nullable=True),
        sa.Column("cta_href", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("starts_at", sa.BigInteger(), nullable=True),
        sa.Column("ends_at", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("published_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_landing_content_blocks_org_page_sort", "landing_content_blocks", ["org_slug", "page_key", "sort_order"])
    op.create_index("ix_landing_content_blocks_org_page_key", "landing_content_blocks", ["org_slug", "page_key", "block_key"], unique=True)


def downgrade():
    op.drop_index("ix_landing_content_blocks_org_page_key", table_name="landing_content_blocks")
    op.drop_index("ix_landing_content_blocks_org_page_sort", table_name="landing_content_blocks")
    op.drop_table("landing_content_blocks")

    op.drop_index("ix_social_proof_items_org_featured", table_name="social_proof_items")
    op.drop_index("ix_social_proof_items_org_sort", table_name="social_proof_items")
    op.drop_index("ix_social_proof_items_org_kind_status", table_name="social_proof_items")
    op.drop_table("social_proof_items")
