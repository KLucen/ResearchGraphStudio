"""Persist library papers, immutable knowledge snapshots and user collections."""

from typing import cast

from alembic import op
from sqlalchemy import Table

revision = "lite0016"
down_revision = "lite0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from researchgraph.knowledge_library_models import (
        KnowledgeCollection,
        KnowledgeCollectionMember,
        KnowledgeLibrary,
        KnowledgeLibraryView,
        LibraryPaper,
        LibraryPaperSourceLink,
        PaperKnowledgeVersion,
    )

    for model in (
        KnowledgeLibrary,
        LibraryPaper,
        LibraryPaperSourceLink,
        PaperKnowledgeVersion,
        KnowledgeCollection,
        KnowledgeCollectionMember,
        KnowledgeLibraryView,
    ):
        cast(Table, model.__table__).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
