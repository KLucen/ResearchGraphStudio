"""Persist source observations and guard concurrent source changes."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_sources", sa.Column("generation", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("paper_sources", sa.Column("last_check", sa.JSON(), nullable=True))


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复升级前备份")
