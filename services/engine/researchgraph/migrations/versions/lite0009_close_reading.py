"""Add local bilingual reading analyses, understanding checks and reader state."""

from typing import cast

from alembic import op
from researchgraph.close_reading_models import SectionCloseReadingResult, UnderstandingCheckResult
from researchgraph.reading_state_models import ConceptUnderstanding, ReadingState
from sqlalchemy import Table

revision = "lite0009"
down_revision = "lite0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for model in (
        SectionCloseReadingResult,
        UnderstandingCheckResult,
        ReadingState,
        ConceptUnderstanding,
    ):
        cast(Table, model.__table__).create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
