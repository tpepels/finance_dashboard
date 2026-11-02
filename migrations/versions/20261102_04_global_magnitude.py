"""Preserve large world-wide financial totals without Numeric overflow.

Revision ID: 20261102_04
Revises: 20261102_03

WDI worldwide listed-company capitalization exceeds 14 integral digits.
Numeric(24, 10) had only 14 integral places. Numeric(32, 10) preserves
all existing precision and allows up to 22 integral places. Use Alembic's
batch API for compatible SQLite and PostgreSQL migrations.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261102_04"
down_revision = "20261102_03"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("observation_versions") as batch:
        batch.alter_column(
            "value", existing_type=sa.Numeric(24, 10),
            type_=sa.Numeric(32, 10), existing_nullable=False,
        )


def downgrade():
    # This may fail if 15+ integral digit world totals have already been
    # ingested; never silently truncate those values on downgrade.
    with op.batch_alter_table("observation_versions") as batch:
        batch.alter_column(
            "value", existing_type=sa.Numeric(32, 10),
            type_=sa.Numeric(24, 10), existing_nullable=False,
        )
