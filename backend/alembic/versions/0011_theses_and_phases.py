"""thesis groups replace proposals; student phase, freeze and restart

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

thesis_status = postgresql.ENUM("pending", "active", "completed", "dropped", name="thesis_status")
phase = postgresql.ENUM("P1", "P2", "P3", name="phase", create_type=False)


def upgrade():
    thesis_status.create(op.get_bind())
    op.create_table(
        "theses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("supervisor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("co_supervisor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("co_supervisor_accepted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="thesis_status", create_type=False), nullable=False),
        sa.Column("deferrals", sa.Integer(), server_default="0", nullable=False),
        sa.Column("defer_pending", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Existing proposals have no supervisor: keep them, versions included, as archived theses with the same ids.
    op.execute(
        "INSERT INTO theses (id, student_id, status, created_at) SELECT id, owner_id, 'dropped', created_at FROM proposals"
    )
    op.execute("SELECT setval(pg_get_serial_sequence('theses', 'id'), COALESCE(MAX(id), 0) + 1, false) FROM theses")

    op.drop_constraint("proposal_versions_proposal_id_version_no_key", "proposal_versions", type_="unique")
    op.drop_constraint("proposal_versions_proposal_id_fkey", "proposal_versions", type_="foreignkey")
    op.alter_column("proposal_versions", "proposal_id", new_column_name="thesis_id")
    op.create_foreign_key(
        "proposal_versions_thesis_id_fkey", "proposal_versions", "theses", ["thesis_id"], ["id"], ondelete="CASCADE"
    )
    op.create_unique_constraint("proposal_versions_thesis_id_version_no_key", "proposal_versions", ["thesis_id", "version_no"])
    # Deleting an account keeps its uploads.
    op.drop_constraint("proposal_versions_uploaded_by_id_fkey", "proposal_versions", type_="foreignkey")
    op.alter_column("proposal_versions", "uploaded_by_id", nullable=True)
    op.create_foreign_key(
        "proposal_versions_uploaded_by_id_fkey", "proposal_versions", "users", ["uploaded_by_id"], ["id"], ondelete="SET NULL"
    )
    op.drop_table("proposals")

    op.add_column("users", sa.Column("thesis_id", sa.Integer(), sa.ForeignKey("theses.id", ondelete="SET NULL")))
    op.add_column("users", sa.Column("phase", phase))
    op.add_column(
        "users", sa.Column("phase_started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    )
    op.add_column("users", sa.Column("frozen_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("restart_requested_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE users SET phase = 'P1' WHERE role = 'student'")


def downgrade():
    # Lossy: a proposal belonged to one student, so only each student's newest thesis comes back;
    # versions of other theses (and of theses whose student was deleted) are dropped.
    op.drop_column("users", "restart_requested_at")
    op.drop_column("users", "frozen_at")
    op.drop_column("users", "phase_started_at")
    op.drop_column("users", "phase")
    op.drop_column("users", "thesis_id")

    op.create_table(
        "proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        "INSERT INTO proposals (id, owner_id, created_at) SELECT DISTINCT ON (student_id) id, student_id, created_at "
        "FROM theses WHERE student_id IS NOT NULL ORDER BY student_id, id DESC"
    )
    op.execute("SELECT setval(pg_get_serial_sequence('proposals', 'id'), COALESCE(MAX(id), 0) + 1, false) FROM proposals")
    op.execute("DELETE FROM proposal_versions WHERE thesis_id NOT IN (SELECT id FROM proposals) OR uploaded_by_id IS NULL")

    op.drop_constraint("proposal_versions_uploaded_by_id_fkey", "proposal_versions", type_="foreignkey")
    op.alter_column("proposal_versions", "uploaded_by_id", nullable=False)
    op.create_foreign_key("proposal_versions_uploaded_by_id_fkey", "proposal_versions", "users", ["uploaded_by_id"], ["id"])
    op.drop_constraint("proposal_versions_thesis_id_version_no_key", "proposal_versions", type_="unique")
    op.drop_constraint("proposal_versions_thesis_id_fkey", "proposal_versions", type_="foreignkey")
    op.alter_column("proposal_versions", "thesis_id", new_column_name="proposal_id")
    op.create_foreign_key(
        "proposal_versions_proposal_id_fkey", "proposal_versions", "proposals", ["proposal_id"], ["id"], ondelete="CASCADE"
    )
    op.create_unique_constraint(
        "proposal_versions_proposal_id_version_no_key", "proposal_versions", ["proposal_id", "version_no"]
    )
    op.drop_table("theses")
    thesis_status.drop(op.get_bind())
