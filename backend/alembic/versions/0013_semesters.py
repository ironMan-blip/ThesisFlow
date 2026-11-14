"""semesters and P1 registration, for the one-week P1 registration window

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "semesters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("theses", sa.Column("p1_registered", sa.Boolean(), server_default=sa.false(), nullable=False))
    # The current semester starts now, so P1 registration is open for the first week.
    op.execute("INSERT INTO semesters (started_at) VALUES (now())")


def downgrade():
    op.drop_column("theses", "p1_registered")
    op.drop_table("semesters")
