"""Per-person session counter, so logging out ends every session

Tokens now carry a stamp of the password hash and this counter, so tokens issued before this
migration stop working once: everyone logs in again.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("users", "session_epoch")
