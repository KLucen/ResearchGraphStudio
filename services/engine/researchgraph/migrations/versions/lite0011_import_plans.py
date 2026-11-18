"""Add model-first import sessions and per-item planning records."""

from typing import cast

from alembic import op
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from sqlalchemy import Table

revision = "lite0011"
down_revision = "lite0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Import only when this revision runs. Importing these models at module
    # load time would add their tables to Base.metadata before lite0001's
    # create_all and cause duplicate-index creation during a fresh migration.
    from researchgraph.model_document_models import (
        LlmDocumentOutput,
        LlmDocumentParse,
        LlmDocumentSegment,
    )

    # The document layer depends on import_sessions, so create the planning
    # tables first and the model-derived parse tables second.
    for model in (
        ImportSession,
        ImportPlanItem,
        LlmDocumentParse,
        LlmDocumentSegment,
        LlmDocumentOutput,
    ):
        cast(Table, model.__table__).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
