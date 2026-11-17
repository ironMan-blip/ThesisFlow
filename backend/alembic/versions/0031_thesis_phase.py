"""Phase belongs to the thesis group, not to each student: move phase, phase_started_at and frozen_at to theses

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

PHASE = postgresql.ENUM("P1", "P2", "P3", name="phase", create_type=False)  # the type already exists


def upgrade():
    op.add_column("theses", sa.Column("phase", PHASE, server_default="P1", nullable=False))
    op.add_column("theses", sa.Column("phase_started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column("theses", sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True))
    # Members shared a thesis, so they share these; take the furthest phase and the latest start and freeze.
    op.execute(
        """
        UPDATE theses t SET
            phase = COALESCE(m.phase, CASE WHEN t.status = 'completed' THEN 'P3'::phase ELSE 'P1'::phase END),
            phase_started_at = COALESCE(m.started, t.created_at),
            frozen_at = m.frozen
        FROM (
            SELECT thesis_id, MAX(phase) AS phase, MAX(phase_started_at) AS started, MAX(frozen_at) AS frozen
            FROM users WHERE thesis_id IS NOT NULL GROUP BY thesis_id
        ) m
        WHERE m.thesis_id = t.id
        """
    )
    op.execute("UPDATE theses SET phase = 'P3' WHERE status = 'completed'")
    op.drop_column("users", "frozen_at")
    op.drop_column("users", "phase_started_at")
    op.drop_column("users", "phase")


def downgrade():
    op.add_column("users", sa.Column("phase", PHASE, nullable=True))
    op.add_column("users", sa.Column("phase_started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column("users", sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE users u SET phase = t.phase, phase_started_at = t.phase_started_at, frozen_at = t.frozen_at
        FROM theses t WHERE u.thesis_id = t.id
        """
    )
    op.execute("UPDATE users SET phase = 'P1' WHERE role = 'student' AND thesis_id IS NULL")
    op.drop_column("theses", "frozen_at")
    op.drop_column("theses", "phase_started_at")
    op.drop_column("theses", "phase")
