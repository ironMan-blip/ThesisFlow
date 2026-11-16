"""A group is formed only when the supervisor and, if named, the co-supervisor have both accepted

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("theses", sa.Column("supervisor_accepted", sa.Boolean(), server_default=sa.false(), nullable=False))
    # Every formed group (active or archived) was accepted by its supervisor under the old rule.
    op.execute("UPDATE theses SET supervisor_accepted = true WHERE status <> 'pending'")


def downgrade():
    op.drop_column("theses", "supervisor_accepted")
