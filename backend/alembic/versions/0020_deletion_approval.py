"""The 7-day delete wait starts when the coordinator approves, not when it is asked for

Requests pending now were never approved, so they stay as requests waiting for a decision.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("deletion_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("proposal_versions", sa.Column("delete_approved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("proposal_versions", "delete_approved_at")
    op.drop_column("users", "deletion_approved_at")
