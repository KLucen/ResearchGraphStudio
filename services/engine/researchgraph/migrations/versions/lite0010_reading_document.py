"""Add source-mapped reading projections and explicit whole-paper notes."""

from typing import cast

from alembic import op
from researchgraph.paper_reading_models import PaperReadingResult
from researchgraph.reading_document_models import ReadingDocumentProjection
from sqlalchemy import Table

revision = "lite0010"
down_revision = "lite0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for model in (ReadingDocumentProjection, PaperReadingResult):
        cast(Table, model.__table__).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
