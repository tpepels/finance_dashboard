"""Market instruments, immutable daily price/action revisions and ECB FX revisions.

Revision ID: 20261102_02
Revises: 20261102_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20261102_02"
down_revision = "20261102_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "market_instruments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("exchange_mic", sa.String(12), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "market_ingestion_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instrument_id", sa.String(64), sa.ForeignKey("market_instruments.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_from", sa.Date()),
        sa.Column("observations_received", sa.Integer(), nullable=False),
        sa.Column("versions_added", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_market_ingestion_runs_instrument_id", "market_ingestion_runs", ["instrument_id"])
    op.create_table(
        "market_price_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instrument_id", sa.String(64), sa.ForeignKey("market_instruments.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("close", sa.Numeric(28, 12), nullable=False),
        sa.Column("adjusted_close", sa.Numeric(28, 12), nullable=False),
        sa.Column("volume", sa.Integer()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_run_id", sa.String(36), sa.ForeignKey("market_ingestion_runs.id"), nullable=False),
    )
    op.create_index("ix_market_price_versions_instrument_id", "market_price_versions", ["instrument_id"])
    op.create_index("ix_market_price_versions_day", "market_price_versions", ["day"])
    op.create_table(
        "market_action_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instrument_id", sa.String(64), sa.ForeignKey("market_instruments.id"), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("action_type", sa.String(16), nullable=False),
        sa.Column("value", sa.Numeric(28, 12), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_run_id", sa.String(36), sa.ForeignKey("market_ingestion_runs.id"), nullable=False),
    )
    op.create_index("ix_market_action_versions_instrument_id", "market_action_versions", ["instrument_id"])
    op.create_index("ix_market_action_versions_ex_date", "market_action_versions", ["ex_date"])
    op.create_table(
        "fx_ingestion_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("observations_received", sa.Integer(), nullable=False),
        sa.Column("versions_added", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_fx_ingestion_runs_currency", "fx_ingestion_runs", ["currency"])
    op.create_table(
        "fx_rate_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("foreign_per_eur", sa.Numeric(24, 12), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_run_id", sa.String(36), sa.ForeignKey("fx_ingestion_runs.id"), nullable=False),
    )
    op.create_index("ix_fx_rate_versions_currency", "fx_rate_versions", ["currency"])
    op.create_index("ix_fx_rate_versions_day", "fx_rate_versions", ["day"])


def downgrade():
    op.drop_index("ix_fx_rate_versions_day", "fx_rate_versions")
    op.drop_index("ix_fx_rate_versions_currency", "fx_rate_versions")
    op.drop_table("fx_rate_versions")
    op.drop_index("ix_fx_ingestion_runs_currency", "fx_ingestion_runs")
    op.drop_table("fx_ingestion_runs")
    op.drop_index("ix_market_action_versions_ex_date", "market_action_versions")
    op.drop_index("ix_market_action_versions_instrument_id", "market_action_versions")
    op.drop_table("market_action_versions")
    op.drop_index("ix_market_price_versions_day", "market_price_versions")
    op.drop_index("ix_market_price_versions_instrument_id", "market_price_versions")
    op.drop_table("market_price_versions")
    op.drop_index("ix_market_ingestion_runs_instrument_id", "market_ingestion_runs")
    op.drop_table("market_ingestion_runs")
    op.drop_table("market_instruments")
