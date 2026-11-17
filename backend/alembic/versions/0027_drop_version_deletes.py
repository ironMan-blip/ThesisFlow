"""Proposal versions are never deleted (SRS F11): drop the delete request / schedule columns

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

COLUMNS = ("delete_requested_at", "delete_reason", "delete_approved_at", "delete_rejected_at")


def upgrade():
    # Dropping the column drops its foreign key too. Pending requests are discarded: the versions themselves stay.
    op.drop_column("proposal_versions", "delete_requested_by_id")
    for name in COLUMNS:
        op.drop_column("proposal_versions", name)


def downgrade():
    for name in ("delete_requested_at", "delete_approved_at", "delete_rejected_at"):
        op.add_column("proposal_versions", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column("proposal_versions", sa.Column("delete_reason", sa.Text(), nullable=True))
    op.add_column(
        "proposal_versions",
        sa.Column(
            "delete_requested_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="proposal_versions_delete_requested_by_id_fkey"),
            nullable=True,
        ),
    )
