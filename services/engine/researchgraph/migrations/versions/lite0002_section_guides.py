"""Add Lite A01 section guide results."""

from typing import cast

from alembic import op
from researchgraph.section_guide_models import SectionGuideResult
from sqlalchemy import Table

revision = "lite0002"
down_revision = "lite0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = cast(Table, SectionGuideResult.__table__)
    table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    table = cast(Table, SectionGuideResult.__table__)
    table.drop(op.get_bind(), checkfirst=True)
