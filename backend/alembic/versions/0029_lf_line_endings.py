"""Store titles and abstracts with LF line endings, as proposal_service._clean now does, so uploads match them

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-17
"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("theses", "title_changes", "proposal_versions"):
        for col in ("title", "abstract"):
            op.execute(f"UPDATE {table} SET {col} = replace(replace({col}, E'\\r\\n', E'\\n'), E'\\r', E'\\n') WHERE {col} ~ E'\\r'")


def downgrade():
    pass  # CRLF and LF text read the same; nothing to undo
