"""Add versioned model-document batch checkpoints without changing history."""

from typing import cast

from alembic import op
from sqlalchemy import Table

revision = "lite0013"
down_revision = "lite0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from researchgraph.document_batch_models import LlmDocumentBatch, LlmDocumentBatchRun

    for model in (LlmDocumentBatchRun, LlmDocumentBatch):
        cast(Table, model.__table__).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
