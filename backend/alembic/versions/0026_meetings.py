"""Meeting log (F16): meetings between a supervisor and a thesis group, and the tasks set in them

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thesis_id", sa.Integer(), sa.ForeignKey("theses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("supervisor_attended", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("student_attended", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("co_supervisor_attended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recorded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("thesis_id", "held_at"),
    )
    op.create_table(
        "meeting_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_meeting_tasks_meeting_id", "meeting_tasks", ["meeting_id"])


def downgrade():
    op.drop_index("ix_meeting_tasks_meeting_id", table_name="meeting_tasks")
    op.drop_table("meeting_tasks")
    op.drop_table("meetings")