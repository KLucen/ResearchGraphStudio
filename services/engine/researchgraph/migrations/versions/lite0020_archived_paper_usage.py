"""Retain content-free paper usage after permanent paper removal."""

import sqlalchemy as sa
from alembic import op

revision = "lite0020"
down_revision = "lite0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Table(
        "archived_paper_usage",
        sa.MetaData(),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), index=True, nullable=False),
        sa.Column("by_kind", sa.JSON(), nullable=False),
    ).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复升级前备份")
