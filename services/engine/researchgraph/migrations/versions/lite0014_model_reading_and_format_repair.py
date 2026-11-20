"""Add model overview layouts and private, bounded document-format recovery."""

from typing import cast

from alembic import op
from sqlalchemy import Table

revision = "lite0014"
down_revision = "lite0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from researchgraph.document_batch_models import LlmDocumentBatchFailure
    from researchgraph.model_document_overview_models import (
        ModelOverviewGraphLayout,
        ModelOverviewGraphViewport,
    )

    for model in (LlmDocumentBatchFailure, ModelOverviewGraphLayout, ModelOverviewGraphViewport):
        cast(Table, model.__table__).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
