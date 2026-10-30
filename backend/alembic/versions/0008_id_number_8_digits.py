"""user id number 8 digits

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "id_number", type_=sa.String(8))
    # Existing 6-digit IDs get two leading zeros; the coordinator is reset from ADMIN_ID_NUMBER on start.
    op.execute("UPDATE users SET id_number = lpad(id_number, 8, '0')")


def downgrade():
    # Lossy for IDs that do not start with "00".
    op.execute("UPDATE users SET id_number = right(id_number, 6)")
    op.alter_column("users", "id_number", type_=sa.String(6))
