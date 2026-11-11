"""Add Lite D01 grounded QA records."""

from typing import cast

from alembic import op
from researchgraph.qa_models import LiteQARecord
from sqlalchemy import Table

revision = "lite0003"
down_revision = "lite0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = cast(Table, LiteQARecord.__table__)
    table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    table = cast(Table, LiteQARecord.__table__)
    table.drop(op.get_bind(), checkfirst=True)
