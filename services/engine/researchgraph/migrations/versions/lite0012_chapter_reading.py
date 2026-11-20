"""Add personal reading progress for model-derived major chapters."""

from typing import cast

from alembic import op
from sqlalchemy import Table

revision = "lite0012"
down_revision = "lite0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from researchgraph.chapter_reading_models import ModelChapterReadingState

    cast(Table, ModelChapterReadingState.__table__).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
