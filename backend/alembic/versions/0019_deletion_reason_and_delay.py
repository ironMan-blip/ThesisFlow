"""Deletes need a reason and run 7 days after they are asked for

Pending requests from before this were made without a reason, under the old "the coordinator approves" rule.
They are cleared rather than turned into deletions nobody agreed to; people ask again with a reason.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("deletion_reason", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "deletion_requested_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="users_deletion_requested_by_id_fkey"),
            nullable=True,
        ),
    )
    op.add_column("proposal_versions", sa.Column("delete_reason", sa.Text(), nullable=True))
    op.execute("UPDATE users SET deletion_requested_at = NULL")
    op.execute("UPDATE proposal_versions SET delete_requested_at = NULL")


def downgrade():
    op.drop_column("proposal_versions", "delete_reason")
    op.drop_column("users", "deletion_requested_by_id")
    op.drop_column("users", "deletion_reason")
