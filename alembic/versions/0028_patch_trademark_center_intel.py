"""PATCH v6.5.0 — trademark center intel

Revision ID: 0028_patch_trademark_center_intel
Revises: 0027_patch_v643_files_thread_id_reconcile
Create Date: 2026-04-17
"""

from alembic import op
from sqlalchemy import text as sa_text

revision = "0028_patch_trademark_center_intel"
down_revision = "0027_patch_v643_files_thread_id_reconcile"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS trademark_matters (
            id VARCHAR PRIMARY KEY,
            org_slug VARCHAR NOT NULL,
            mark_name VARCHAR NOT NULL,
            normalized_mark VARCHAR NOT NULL,
            applicant_name VARCHAR NULL,
            applicant_country VARCHAR NULL,
            contact_email VARCHAR NULL,
            requested_by_user_id VARCHAR NULL,
            status VARCHAR NOT NULL DEFAULT 'draft',
            approval_status VARCHAR NOT NULL DEFAULT 'pending',
            approval_by_user_id VARCHAR NULL,
            approval_at BIGINT NULL,
            filing_mode VARCHAR NOT NULL DEFAULT 'assisted',
            source VARCHAR NULL,
            jurisdictions_json TEXT NULL,
            nice_classes_json TEXT NULL,
            goods_services_text TEXT NULL,
            risk_score INTEGER NULL,
            risk_level VARCHAR NULL,
            internal_conflicts_json TEXT NULL,
            external_screening_json TEXT NULL,
            dossier_json TEXT NULL,
            notes TEXT NULL,
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL
        )
    """))
    conn.execute(sa_text("CREATE INDEX IF NOT EXISTS ix_trademark_matters_org_created ON trademark_matters (org_slug, created_at)"))
    conn.execute(sa_text("CREATE INDEX IF NOT EXISTS ix_trademark_matters_org_status ON trademark_matters (org_slug, status)"))
    conn.execute(sa_text("CREATE INDEX IF NOT EXISTS ix_trademark_matters_org_mark ON trademark_matters (org_slug, normalized_mark)"))

    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS trademark_events (
            id VARCHAR PRIMARY KEY,
            org_slug VARCHAR NOT NULL,
            matter_id VARCHAR NOT NULL,
            event_type VARCHAR NOT NULL,
            actor_user_id VARCHAR NULL,
            payload_json TEXT NULL,
            created_at BIGINT NOT NULL
        )
    """))
    conn.execute(sa_text("CREATE INDEX IF NOT EXISTS ix_trademark_events_org_created ON trademark_events (org_slug, created_at)"))
    conn.execute(sa_text("CREATE INDEX IF NOT EXISTS ix_trademark_events_matter ON trademark_events (matter_id, created_at)"))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa_text("DROP INDEX IF EXISTS ix_trademark_events_matter"))
    conn.execute(sa_text("DROP INDEX IF EXISTS ix_trademark_events_org_created"))
    conn.execute(sa_text("DROP TABLE IF EXISTS trademark_events"))
    conn.execute(sa_text("DROP INDEX IF EXISTS ix_trademark_matters_org_mark"))
    conn.execute(sa_text("DROP INDEX IF EXISTS ix_trademark_matters_org_status"))
    conn.execute(sa_text("DROP INDEX IF EXISTS ix_trademark_matters_org_created"))
    conn.execute(sa_text("DROP TABLE IF EXISTS trademark_matters"))
