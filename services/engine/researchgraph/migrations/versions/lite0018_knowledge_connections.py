"""Persist bounded incremental knowledge connections and reports."""

from typing import cast

from alembic import op
from sqlalchemy import Table

revision = "lite0018"
down_revision = "lite0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from researchgraph.knowledge_connection_models import (
        KnowledgeAnalysisEvent,
        KnowledgeCollectionEvent,
        KnowledgeConnectionReport,
        KnowledgeConnectionRequest,
        KnowledgeConnectionRun,
        KnowledgePairCheckpoint,
        KnowledgeUsageTombstone,
    )

    for model in (
        KnowledgeConnectionRun,
        KnowledgeConnectionRequest,
        KnowledgeConnectionReport,
        KnowledgeAnalysisEvent,
        KnowledgeCollectionEvent,
        KnowledgePairCheckpoint,
        KnowledgeUsageTombstone,
    ):
        cast(Table, model.__table__).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
