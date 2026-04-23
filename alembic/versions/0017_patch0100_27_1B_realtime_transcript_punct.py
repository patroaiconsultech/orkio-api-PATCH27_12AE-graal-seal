"""PATCH0100_27.1B — Add transcript_punct to realtime_events

Revision ID: 0017
Revises: 0016
Create Date: 2026-02-28

This migration is intentionally minimal and safe:
  - Adds nullable TEXT column transcript_punct to realtime_events
"""

from alembic import op
import sqlalchemy as sa

revision = '0017_patch0100_27_1B_realtime_transcript_punct'
down_revision = '0016_patch0100_25S_realtime_audit'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('realtime_events', sa.Column('transcript_punct', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('realtime_events', 'transcript_punct')
