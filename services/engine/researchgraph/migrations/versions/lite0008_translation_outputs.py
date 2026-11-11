"""Select PDF output modes and default future translations to bundled runtime."""

from alembic import op
from sqlalchemy import Boolean, Column, String, inspect, text, true

revision = "lite0008"
down_revision = "lite0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("pdf_translations")}
    if "output_mode" not in columns:
        op.add_column(
            "pdf_translations",
            Column("output_mode", String(16), nullable=False, server_default="both"),
        )
    # Historical task runtime snapshots are immutable. Only the settings for
    # future explicit tasks change; no service or model is started by migration.
    bind.execute(text("UPDATE pdf_translation_settings SET launch_mode='bundled', enabled=1"))
    with op.batch_alter_table("pdf_translation_settings") as batch:
        batch.alter_column("launch_mode", existing_type=String(16), server_default="bundled")
        batch.alter_column("enabled", existing_type=Boolean(), server_default=true())


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复 Lite 备份")
