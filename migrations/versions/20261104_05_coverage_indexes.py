"""Cover source-coverage aggregation without reading version table payloads.

Revision ID: 20261104_05
Revises: 20261102_04

Nonunique source/date indexes retain every append-only revision and leave
the existing single-column indexes available for other access patterns.
"""
from alembic import op

revision = "20261104_05"
down_revision = "20261102_04"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_observation_versions_series_period",
                    "observation_versions", ["series_id", "period"], unique=False)
    op.create_index("ix_market_price_versions_instrument_day",
                    "market_price_versions", ["instrument_id", "day"], unique=False)
    op.create_index("ix_fx_rate_versions_currency_day",
                    "fx_rate_versions", ["currency", "day"], unique=False)


def downgrade():
    op.drop_index("ix_fx_rate_versions_currency_day", table_name="fx_rate_versions")
    op.drop_index("ix_market_price_versions_instrument_day",
                  table_name="market_price_versions")
    op.drop_index("ix_observation_versions_series_period",
                  table_name="observation_versions")
