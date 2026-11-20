"""Persist knowledge extraction source snapshots and single dispatch slots."""

from typing import cast

from alembic import op
from sqlalchemy import Table

revision = "lite0017"
down_revision = "lite0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun

    cast(Table, KnowledgeExtractionRun.__table__).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
