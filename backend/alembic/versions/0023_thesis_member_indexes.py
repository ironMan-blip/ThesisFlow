"""Index the thesis member columns that every faculty and student lookup filters on

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-16
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

COLUMNS = ("student_id", "supervisor_id", "co_supervisor_id")


def upgrade():
    for column in COLUMNS:
        op.create_index(f"ix_theses_{column}", "theses", [column])


def downgrade():
    for column in COLUMNS:
        op.drop_index(f"ix_theses_{column}", "theses")
