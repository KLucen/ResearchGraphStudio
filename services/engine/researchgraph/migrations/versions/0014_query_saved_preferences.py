"""Keep saved-reading annotations/removal separate from immutable answer/source history."""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE query_saved_preferences (
        saved_id TEXT PRIMARY KEY NOT NULL REFERENCES query_saved_knowledge(id),
        annotation TEXT NOT NULL, revision INTEGER NOT NULL,
        removed_at TEXT, updated_at TEXT NOT NULL)""")


def downgrade() -> None:
    raise RuntimeError("Restore the verified pre-upgrade backup; preserve reading annotations")
