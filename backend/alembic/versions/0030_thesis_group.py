"""A thesis belongs to a student group: every member shares it

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("theses", sa.Column("group_id", sa.Integer(), nullable=True))
    op.create_foreign_key("theses_group_id_fkey", "theses", "student_groups", ["group_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_theses_group_id", "theses", ["group_id"])
    # Existing theses belong to their requesting student's current group, if they have one.
    op.execute(
        """
        UPDATE theses t SET group_id = gm.group_id
        FROM group_members gm
        WHERE gm.user_id = t.student_id AND t.status IN ('pending', 'formed', 'active')
        """
    )


def downgrade():
    op.drop_index("ix_theses_group_id", "theses")
    op.drop_constraint("theses_group_id_fkey", "theses", type_="foreignkey")
    op.drop_column("theses", "group_id")
