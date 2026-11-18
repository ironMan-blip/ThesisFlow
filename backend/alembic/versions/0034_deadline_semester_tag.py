"""Tag each phase deadline with the semester it is for; existing deadlines get the current semester

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "milestone_templates",
        sa.Column("semester_id", sa.Integer(), sa.ForeignKey("semesters.id", ondelete="SET NULL"), nullable=True),
    )
    op.execute("UPDATE milestone_templates SET semester_id = (SELECT max(id) FROM semesters)")


def downgrade():
    op.drop_column("milestone_templates", "semester_id")
