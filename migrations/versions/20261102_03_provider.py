"""Allow future provider identifiers without truncating audit metadata.

Revision ID: 20261102_03
Revises: 20261102_02
"""
from alembic import op
import sqlalchemy as sa

revision = "20261102_03"
down_revision = "20261102_02"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("series") as batch:
        batch.alter_column(
            "provider",
            existing_type=sa.String(length=24), type_=sa.String(length=64),
            existing_nullable=False,
        )

def downgrade():
    with op.batch_alter_table("series") as batch:
        batch.alter_column(
            "provider",
            existing_type=sa.String(length=64), type_=sa.String(length=24),
            existing_nullable=False,
        )
