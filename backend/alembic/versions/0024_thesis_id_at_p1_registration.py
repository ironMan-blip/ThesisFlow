"""Groups get their thesis ID at P1 registration: a new "formed" status for accepted groups not registered yet

Existing active groups that never registered become formed and lose their thesis ID: the student is still in P1, the
group is not registered this semester and it has no proposal (uploads need registration). Groups in later phases
registered in an earlier semester, so they stay active with their ID.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-16
"""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    # A new enum value can't be used in the transaction that adds it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE thesis_status ADD VALUE IF NOT EXISTS 'formed' BEFORE 'active'")
    op.execute(
        """
        UPDATE theses t SET status = 'formed', code = NULL
        FROM users u
        WHERE u.id = t.student_id AND u.phase = 'P1'
          AND t.status = 'active' AND NOT t.p1_registered
          AND NOT EXISTS (SELECT 1 FROM proposals p WHERE p.thesis_id = t.id)
        """
    )


def downgrade():
    # Postgres can't drop an enum value; formed groups go back to active (cleared IDs are not restored).
    op.execute("UPDATE theses SET status = 'active' WHERE status = 'formed'")
