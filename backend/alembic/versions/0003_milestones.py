"""phase deadlines and the phase of each proposal version

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

phase = sa.Enum("P1", "P2", "P3", name="phase")


def upgrade():
    # create_table also creates the phase enum type.
    op.create_table(
        "milestones",
        sa.Column("phase", phase, primary_key=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grace_minutes", sa.Integer(), nullable=False),
        sa.Column("penalty_per_day", sa.Integer(), nullable=False),
    )
    # Existing uploads were proposals, so they count as P1.
    op.add_column("proposal_versions", sa.Column("phase", phase, server_default="P1", nullable=False))


def downgrade():
    op.drop_column("proposal_versions", "phase")
    op.drop_table("milestones")
    phase.drop(op.get_bind())
