"""Add Lite D02 optional keyword expansion records."""

from typing import cast

from alembic import op
from researchgraph.keyword_models import LiteKeywordRecord
from sqlalchemy import Table

revision = "lite0004"
down_revision = "lite0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = cast(Table, LiteKeywordRecord.__table__)
    table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    table = cast(Table, LiteKeywordRecord.__table__)
    table.drop(op.get_bind(), checkfirst=True)
