"""Versioned PDF sources and immutable extracted blocks."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite ADD COLUMN cannot add a foreign key without recreating the table.
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("project_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("payload", sa.JSON(), nullable=True))
        batch.create_foreign_key("fk_jobs_project", "projects", ["project_id"], ["id"])
    op.create_table(
        "papers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_papers_project_id", "papers", ["project_id"])
    op.create_table(
        "attachment_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("paper_id", "sha256"),
    )
    op.create_index("ix_attachment_revisions_paper_id", "attachment_revisions", ["paper_id"])
    op.create_table(
        "paper_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id"), nullable=False),
        sa.Column(
            "revision_id", sa.String(36), sa.ForeignKey("attachment_revisions.id"), nullable=False
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("managed_path", sa.Text(), nullable=True),
        sa.UniqueConstraint("paper_id", "path", "mode"),
    )
    op.create_index("ix_paper_sources_paper_id", "paper_sources", ["paper_id"])
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id", sa.String(36), sa.ForeignKey("attachment_revisions.id"), nullable=False
        ),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("page_label", sa.Text(), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=False),
        sa.UniqueConstraint("revision_id", "page_index", "block_index"),
    )
    op.create_index("ix_chunks_revision_id", "chunks", ["revision_id"])


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复升级前备份")
