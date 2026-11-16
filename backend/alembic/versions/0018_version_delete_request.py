"""Students ask the coordinator to delete a proposal version

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("proposal_versions", sa.Column("delete_requested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("proposal_versions", "delete_requested_at")
