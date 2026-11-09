"""Fresh Lite schema; no legacy business-data migration."""

from alembic import op
from researchgraph import lite_models, model_settings, paper_overview_models, structure_models
from researchgraph.models import Base

revision = "lite0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Imported models form this initial Lite snapshot. Subsequent changes must
    # use a new explicit migration instead of modifying this baseline.
    _ = (lite_models, model_settings, paper_overview_models, structure_models)
    Base.metadata.create_all(bind=op.get_bind())
    op.execute("""CREATE VIRTUAL TABLE chunk_fts USING fts5(
        chunk_id UNINDEXED, paper_id UNINDEXED, document_version_id UNINDEXED,
        section_id UNINDEXED, text, tokenize='unicode61'
    )""")


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复 Lite 备份")
