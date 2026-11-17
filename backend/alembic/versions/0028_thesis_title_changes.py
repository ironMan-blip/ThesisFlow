"""Thesis title and abstract, set by the first upload; changing them needs one supervisor-approved request

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("theses", sa.Column("title", sa.String(255), nullable=True))
    op.add_column("theses", sa.Column("abstract", sa.Text(), nullable=True))
    # Existing theses keep the title and abstract of their latest upload.
    op.execute(
        """
        UPDATE theses t SET title = v.title, abstract = v.abstract
        FROM (
            SELECT DISTINCT ON (p.thesis_id) p.thesis_id, pv.title, pv.abstract
            FROM proposals p JOIN proposal_versions pv ON pv.proposal_id = p.id
            ORDER BY p.thesis_id, pv.created_at DESC, pv.id DESC
        ) v
        WHERE v.thesis_id = t.id
        """
    )
    op.create_table(
        "title_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thesis_id", sa.Integer(), sa.ForeignKey("theses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index("ix_title_changes_thesis_id", "title_changes", ["thesis_id"])


def downgrade():
    op.drop_index("ix_title_changes_thesis_id", "title_changes")
    op.drop_table("title_changes")
    op.drop_column("theses", "abstract")
    op.drop_column("theses", "title")
