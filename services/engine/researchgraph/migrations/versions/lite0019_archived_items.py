"""Add the shared archive and register library papers already archived."""

import sqlalchemy as sa
from alembic import op
from researchgraph.core import stable_id

revision = "lite0019"
down_revision = "lite0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    archive = sa.Table(
        "archived_items",
        sa.MetaData(),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("archived_at", sa.String(40), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("restore_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("kind", "target_id", name="uq_archive_target"),
        sa.Index("ix_archive_status_time", "status", "archived_at", "id"),
    )
    # The original Lite initializer may already include registered empty tables.
    archive.create(bind, checkfirst=True)
    existing = (
        bind.execute(
            sa.text("SELECT id, title, updated_at FROM knowledge_library_papers WHERE archived = 1")
        )
        .mappings()
        .all()
    )
    if existing:
        op.bulk_insert(
            archive,
            [
                {
                    "id": stable_id("archive-library-paper", row["id"]),
                    "kind": "knowledge_paper",
                    "target_id": row["id"],
                    "title": row["title"],
                    "project_id": None,
                    "archived_at": row["updated_at"],
                    "status": "archived",
                    "restore_json": {},
                }
                for row in existing
            ],
        )


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复迁移前自动备份的 Lite 数据库")
