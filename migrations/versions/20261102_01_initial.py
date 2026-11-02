"""Initial append-only observations and ingestion audit.

Revision ID: 20261102_01
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20261102_01"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "series",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("source_key", sa.String(length=160), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("series_id", sa.String(length=128), sa.ForeignKey("series.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_from", sa.Date()),
        sa.Column("request_url", sa.Text()),
        sa.Column("response_prepared_at", sa.DateTime(timezone=True)),
        sa.Column("observations_received", sa.Integer(), nullable=False),
        sa.Column("versions_added", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_ingestion_runs_series_id", "ingestion_runs", ["series_id"])
    op.create_table(
        "observation_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("series_id", sa.String(length=128), sa.ForeignKey("series.id"), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(24, 10), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=36), sa.ForeignKey("ingestion_runs.id"), nullable=False),
    )
    op.create_index("ix_observation_versions_series_id", "observation_versions", ["series_id"])
    op.create_index("ix_observation_versions_period", "observation_versions", ["period"])

def downgrade():
    op.drop_index("ix_observation_versions_period", "observation_versions")
    op.drop_index("ix_observation_versions_series_id", "observation_versions")
    op.drop_table("observation_versions")
    op.drop_index("ix_ingestion_runs_series_id", "ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("series")
