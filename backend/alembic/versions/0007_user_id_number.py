"""user 6-digit id number

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("id_number", sa.String(6), nullable=True))
    # Existing accounts get their zero-padded row id; the coordinator is reset from ADMIN_ID_NUMBER on start.
    op.execute("UPDATE users SET id_number = lpad(id::text, 6, '0')")
    op.alter_column("users", "id_number", nullable=False)
    op.create_index("ix_users_id_number", "users", ["id_number"], unique=True)


def downgrade():
    op.drop_index("ix_users_id_number", table_name="users")
    op.drop_column("users", "id_number")
