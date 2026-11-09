"""Add the additive project experience mode used by ResearchGraph Lite."""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing projects must keep access to the complete historical product.
    # The API explicitly writes ``lite`` for new projects; using ``legacy`` as
    # the database default also keeps direct/older ORM inserts compatible.
    op.execute(
        "ALTER TABLE projects ADD COLUMN experience_mode VARCHAR(16) NOT NULL DEFAULT 'legacy'"
    )
    op.execute("UPDATE projects SET experience_mode='legacy' WHERE experience_mode IS NULL")


def downgrade() -> None:
    raise RuntimeError("Restore the verified pre-upgrade backup; preserve project modes")
