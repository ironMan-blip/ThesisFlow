"""Thesis ID: stored "T" + 8 random digits instead of TH-<id>

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-14
"""
import secrets

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("theses", sa.Column("code", sa.String(9), nullable=True))
    conn = op.get_bind()
    # Every thesis past pending already had an ID; give each a new random one.
    ids = conn.execute(sa.text("SELECT id FROM theses WHERE status <> 'pending'")).scalars().all()
    used = set()
    for thesis_id in ids:
        while (code := f"T{secrets.randbelow(10**8):08d}") in used:
            pass
        used.add(code)
        conn.execute(sa.text("UPDATE theses SET code = :c WHERE id = :i"), {"c": code, "i": thesis_id})
    op.create_unique_constraint("theses_code_key", "theses", ["code"])


def downgrade():
    op.drop_constraint("theses_code_key", "theses", type_="unique")
    op.drop_column("theses", "code")
