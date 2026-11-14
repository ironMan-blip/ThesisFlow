"""approved restarts wait for the semester rollover

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("restart_approved", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    op.drop_column("users", "restart_approved")
