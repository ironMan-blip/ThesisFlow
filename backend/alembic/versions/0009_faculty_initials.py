"""faculty initials

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable: students and the coordinator have none; existing faculty can be filled in later.
    op.add_column("users", sa.Column("initials", sa.String(10), nullable=True))
    op.create_unique_constraint("uq_users_initials", "users", ["initials"])


def downgrade():
    op.drop_constraint("uq_users_initials", "users", type_="unique")
    op.drop_column("users", "initials")
