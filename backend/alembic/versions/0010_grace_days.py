"""grace period in days instead of minutes

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-30
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("milestones", "grace_minutes", new_column_name="grace_days")
    # Round up so no existing grace period gets shorter.
    op.execute("UPDATE milestones SET grace_days = (grace_days + 1439) / 1440")


def downgrade():
    op.execute("UPDATE milestones SET grace_days = grace_days * 1440")
    op.alter_column("milestones", "grace_days", new_column_name="grace_minutes")
