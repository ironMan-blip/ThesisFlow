"""One deadline per phase and semester, and each thesis group's deadline semester

A semester's deadlines fall in week 2 of the next one, so last semester's P1 groups and the new P1 groups each need
their own P1 deadline at the same time.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE milestone_templates SET semester_id = (SELECT max(id) FROM semesters) WHERE semester_id IS NULL")
    op.drop_constraint("milestone_templates_semester_id_fkey", "milestone_templates", type_="foreignkey")
    op.drop_constraint("milestone_templates_pkey", "milestone_templates", type_="primary")
    op.alter_column("milestone_templates", "semester_id", nullable=False)
    op.create_primary_key("milestone_templates_pkey", "milestone_templates", ["phase", "semester_id"])
    op.create_foreign_key(
        "milestone_templates_semester_id_fkey", "milestone_templates", "semesters", ["semester_id"], ["id"],
        ondelete="CASCADE",
    )
    # Left null: null means the current semester, which is where every existing group stands.
    op.add_column(
        "theses",
        sa.Column("deadline_semester_id", sa.Integer(), sa.ForeignKey("semesters.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade():
    op.drop_column("theses", "deadline_semester_id")
    # Back to one deadline per phase: keep each phase's newest semester.
    op.execute(
        "DELETE FROM milestone_templates m USING milestone_templates n "
        "WHERE m.phase = n.phase AND m.semester_id < n.semester_id"
    )
    op.drop_constraint("milestone_templates_semester_id_fkey", "milestone_templates", type_="foreignkey")
    op.drop_constraint("milestone_templates_pkey", "milestone_templates", type_="primary")
    op.alter_column("milestone_templates", "semester_id", nullable=True)
    op.create_primary_key("milestone_templates_pkey", "milestone_templates", ["phase"])
    op.create_foreign_key(
        "milestone_templates_semester_id_fkey", "milestone_templates", "semesters", ["semester_id"], ["id"],
        ondelete="SET NULL",
    )
