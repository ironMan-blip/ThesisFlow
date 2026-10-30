"""sha256 of each proposal PDF, to detect re-uploads

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("proposal_versions", sa.Column("sha256", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("proposal_versions", "sha256")
