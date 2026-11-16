"""Thesis IDs are issued at P1 registration: clear the ID of active groups that never registered

A group never registered when its student is still in P1, it is not registered this semester, and it has no proposal
(uploads need registration). Groups in later phases registered in an earlier semester, so they keep their ID.

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
    op.execute(
        """
        UPDATE theses t SET code = NULL
        FROM users u
        WHERE u.id = t.student_id AND u.phase = 'P1'
          AND t.status = 'active' AND NOT t.p1_registered AND t.code IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM proposals p WHERE p.thesis_id = t.id)
        """
    )


def downgrade():
    pass  # cleared IDs are not restored; register_p1 issues a new one
