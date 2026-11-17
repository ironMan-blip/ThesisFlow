"""student groups, invitations and teammate profiles (F6)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

invitation_status = postgresql.ENUM("pending", "accepted", "declined", "cancelled", name="invitation_status")


def upgrade():
    invitation_status.create(op.get_bind())
    op.create_table(
        "student_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("leader_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("student_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "group_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("student_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invitee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", postgresql.ENUM(name="invitation_status", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_group_invitations_invitee_id", "group_invitations", ["invitee_id"])
    op.create_table(
        "student_profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("interests", sa.Text(), server_default="", nullable=False),
        sa.Column("skills", sa.Text(), server_default="", nullable=False),
        sa.Column("bio", sa.String(500), server_default="", nullable=False),
        sa.Column("open_to_invites", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade():
    op.drop_table("student_profiles")
    op.drop_index("ix_group_invitations_invitee_id", table_name="group_invitations")
    op.drop_table("group_invitations")
    op.drop_table("group_members")
    op.drop_table("student_groups")
    invitation_status.drop(op.get_bind())
