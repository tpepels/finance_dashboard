"""Attach immutable acquisition receipt references to ingestion jobs.

Revision ID: 20261105_06
Revises: 20261104_05

Existing ingestion/observation history remains unchanged. Historical
rows have NULL provenance fields rather than fabricated archives.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261105_06"
down_revision = "20261104_05"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ingestion_runs", sa.Column("evidence_kind", sa.String(length=32), nullable=True))
    op.add_column("ingestion_runs", sa.Column("evidence_scope", sa.String(length=64), nullable=True))
    op.add_column("ingestion_runs", sa.Column("evidence_bundle_digest", sa.String(length=64), nullable=True))
    op.add_column("ingestion_runs", sa.Column("evidence_receipt_name", sa.String(length=96), nullable=True))


def downgrade():
    op.drop_column("ingestion_runs", "evidence_receipt_name")
    op.drop_column("ingestion_runs", "evidence_bundle_digest")
    op.drop_column("ingestion_runs", "evidence_scope")
    op.drop_column("ingestion_runs", "evidence_kind")
