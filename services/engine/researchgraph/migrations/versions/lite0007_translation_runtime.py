"""Add explicitly configured managed translation runtime; old settings stay manual."""

from alembic import op
from sqlalchemy import JSON, Column, String, Text, inspect

revision = "lite0007"
down_revision = "lite0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # lite0001 and lite0006 use shared model metadata, so a fresh database may
    # already contain these columns. Existing 0006 databases need additive DDL.
    bind = op.get_bind()
    settings = {column["name"] for column in inspect(bind).get_columns("pdf_translation_settings")}
    for column in (
        Column("launch_mode", String(16), nullable=False, server_default="manual"),
        Column("python_path", Text, nullable=True),
        Column("server_path", Text, nullable=True),
    ):
        if column.name not in settings:
            op.add_column("pdf_translation_settings", column)
    records = {column["name"] for column in inspect(bind).get_columns("pdf_translations")}
    if "runtime_snapshot" not in records:
        op.add_column(
            "pdf_translations",
            Column("runtime_snapshot", JSON, nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复 Lite 备份")
