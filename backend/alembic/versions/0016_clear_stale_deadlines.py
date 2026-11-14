"""Clear deadlines left over from before the current semester

0013 started the first semester without clearing deadlines set before it, so an old, closed
deadline could block uploads. A deadline that closed before the current semester started can't
belong to it (the rollover clears deadlines, and a new one must close in the future), so drop it.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-14
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "DELETE FROM milestone_templates "
        "WHERE due_at + grace_days * interval '1 day' < (SELECT max(started_at) FROM semesters)"
    )


def downgrade():
    pass  # the removed deadlines were stale; nothing to restore
