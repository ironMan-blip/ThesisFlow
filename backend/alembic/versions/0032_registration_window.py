"""The coordinator sets the P1 registration start and end on the semester; unset keeps one week from its start

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("semesters", sa.Column("registration_opens_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("semesters", sa.Column("registration_closes_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("semesters", "registration_closes_at")
    op.drop_column("semesters", "registration_opens_at")
