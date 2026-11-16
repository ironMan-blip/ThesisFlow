"""Co-supervisors are added to a formed group and join once they and the supervisor both agree

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
    op.add_column("theses", sa.Column("co_supervisor_approved", sa.Boolean(), server_default=sa.false(), nullable=False))
    # Co-supervisors named so far were named when the group was requested, which the supervisor accepted.
    op.execute("UPDATE theses SET co_supervisor_approved = true WHERE co_supervisor_id IS NOT NULL")


def downgrade():
    op.drop_column("theses", "co_supervisor_approved")
