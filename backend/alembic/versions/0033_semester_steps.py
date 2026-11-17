"""Add semester name and step open/close toggles for F1

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("semesters", sa.Column("name", sa.String(80), server_default="Current Semester", nullable=False))
    op.add_column("semesters", sa.Column("form_group_open", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("semesters", sa.Column("pick_supervisor_open", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("semesters", sa.Column("p1_open", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("semesters", sa.Column("p2_open", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("semesters", sa.Column("p3_open", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("semesters", sa.Column("defense_open", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    op.drop_column("semesters", "defense_open")
    op.drop_column("semesters", "p3_open")
    op.drop_column("semesters", "p2_open")
    op.drop_column("semesters", "p1_open")
    op.drop_column("semesters", "pick_supervisor_open")
    op.drop_column("semesters", "form_group_open")
    op.drop_column("semesters", "name")