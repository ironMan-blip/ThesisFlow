"""Supervisors and the coordinator can schedule a version delete; students see rejected requests

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "proposal_versions",
        sa.Column(
            "delete_requested_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="proposal_versions_delete_requested_by_id_fkey"),
            nullable=True,
        ),
    )
    op.add_column("proposal_versions", sa.Column("delete_rejected_at", sa.DateTime(timezone=True), nullable=True))
    # Requests so far were all made by the version's student.
    op.execute(
        "UPDATE proposal_versions v SET delete_requested_by_id = t.student_id FROM proposals p JOIN theses t ON t.id = p.thesis_id "
        "WHERE v.proposal_id = p.id AND v.delete_requested_at IS NOT NULL"
    )


def downgrade():
    op.drop_column("proposal_versions", "delete_rejected_at")
    op.drop_column("proposal_versions", "delete_requested_by_id")
