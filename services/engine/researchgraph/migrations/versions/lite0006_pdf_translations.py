"""Add opt-in derived PDF translation records without rewriting source data."""

from typing import cast

from alembic import op
from researchgraph.translation_models import PDFTranslation, PDFTranslationSettings
from sqlalchemy import Table

revision = "lite0006"
down_revision = "lite0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cast(Table, PDFTranslationSettings.__table__).create(bind, checkfirst=True)
    cast(Table, PDFTranslation.__table__).create(bind, checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复 Lite 备份")
