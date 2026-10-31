"""Persist observed job stages and index stable project history ordering."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("stage", sa.String(24), nullable=True))
    op.create_index("ix_jobs_project_history", "jobs", ["project_id", "created_at", "id"])


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复升级前备份")
