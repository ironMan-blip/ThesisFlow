"""SRS F11/F12 models: proposals, milestone templates, group milestones and deliverables

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

phase = postgresql.ENUM(name="phase", create_type=False)


def upgrade():
    # F11: one proposal per thesis owns the versions.
    op.create_table(
        "proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thesis_id", sa.Integer(), sa.ForeignKey("theses.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        "INSERT INTO proposals (thesis_id, created_at) "
        "SELECT thesis_id, min(created_at) FROM proposal_versions GROUP BY thesis_id"
    )
    op.add_column("proposal_versions", sa.Column("proposal_id", sa.Integer()))
    op.execute("UPDATE proposal_versions v SET proposal_id = p.id FROM proposals p WHERE p.thesis_id = v.thesis_id")
    op.alter_column("proposal_versions", "proposal_id", nullable=False)
    op.drop_constraint("proposal_versions_thesis_id_version_no_key", "proposal_versions", type_="unique")
    op.drop_constraint("proposal_versions_thesis_id_fkey", "proposal_versions", type_="foreignkey")
    op.create_foreign_key(
        "proposal_versions_proposal_id_fkey", "proposal_versions", "proposals", ["proposal_id"], ["id"], ondelete="CASCADE"
    )
    op.create_unique_constraint("proposal_versions_proposal_id_version_no_key", "proposal_versions", ["proposal_id", "version_no"])

    # F12: the coordinator's deadlines are templates; each group gets its own milestone with its deliverables.
    op.rename_table("milestones", "milestone_templates")
    op.execute("ALTER INDEX milestones_pkey RENAME TO milestone_templates_pkey")
    op.create_table(
        "group_milestones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thesis_id", sa.Integer(), sa.ForeignKey("theses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("semester_id", sa.Integer(), sa.ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase", phase, nullable=False),
        sa.Column("extended_due_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("thesis_id", "semester_id", "phase"),
    )
    op.create_table(
        "deliverables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_milestone_id",
            sa.Integer(),
            sa.ForeignKey("group_milestones.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "proposal_version_id",
            sa.Integer(),
            sa.ForeignKey("proposal_versions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
    )
    # Each group's latest upload that counts this semester (current phase, after it started) is its deliverable.
    join = "FROM proposal_versions v JOIN proposals p ON p.id = v.proposal_id JOIN users u ON u.thesis_id = p.thesis_id"
    counted = "v.phase = u.phase AND v.created_at >= u.phase_started_at"
    op.execute(
        "INSERT INTO group_milestones (thesis_id, semester_id, phase, submitted_at) "
        f"SELECT p.thesis_id, (SELECT max(id) FROM semesters), v.phase, max(v.created_at) {join} WHERE {counted} "
        "GROUP BY p.thesis_id, v.phase"
    )
    # group_milestones only holds this semester's rows so far, so thesis and phase pick the right one.
    op.execute(
        "INSERT INTO deliverables (group_milestone_id, proposal_version_id) "
        f"SELECT DISTINCT ON (g.id) g.id, v.id {join} "
        "JOIN group_milestones g ON g.thesis_id = p.thesis_id AND g.phase = v.phase "
        f"WHERE {counted} ORDER BY g.id, v.created_at DESC"
    )
    op.drop_column("proposal_versions", "thesis_id")


def downgrade():
    op.add_column("proposal_versions", sa.Column("thesis_id", sa.Integer()))
    op.execute("UPDATE proposal_versions v SET thesis_id = p.thesis_id FROM proposals p WHERE p.id = v.proposal_id")
    op.alter_column("proposal_versions", "thesis_id", nullable=False)
    op.drop_table("deliverables")
    op.drop_table("group_milestones")
    op.execute("ALTER INDEX milestone_templates_pkey RENAME TO milestones_pkey")
    op.rename_table("milestone_templates", "milestones")
    op.drop_constraint("proposal_versions_proposal_id_version_no_key", "proposal_versions", type_="unique")
    op.drop_constraint("proposal_versions_proposal_id_fkey", "proposal_versions", type_="foreignkey")
    op.drop_column("proposal_versions", "proposal_id")
    op.create_foreign_key(
        "proposal_versions_thesis_id_fkey", "proposal_versions", "theses", ["thesis_id"], ["id"], ondelete="CASCADE"
    )
    op.create_unique_constraint("proposal_versions_thesis_id_version_no_key", "proposal_versions", ["thesis_id", "version_no"])
    op.drop_table("proposals")
