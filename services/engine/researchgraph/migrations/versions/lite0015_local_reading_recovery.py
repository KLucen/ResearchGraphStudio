"""Persist explicit local recovery for partially valid model reading output."""

from typing import cast

from alembic import op
from sqlalchemy import Table

revision = "lite0015"
down_revision = "lite0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from researchgraph.model_document_models import LlmDocumentOutputLocalRecovery

    cast(Table, LlmDocumentOutputLocalRecovery.__table__).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
