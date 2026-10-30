"""approval flag for faculty sign-ups

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    # Existing accounts were created by the coordinator or seed, so they stay usable.
    op.add_column("users", sa.Column("approved", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade():
    op.drop_column("users", "approved")
