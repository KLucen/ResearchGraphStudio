"""Persist Lint phase/timing telemetry and index reverse support/source lookups."""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE lint_runs ADD COLUMN phase VARCHAR(32) NOT NULL DEFAULT 'scanning'")
    op.execute("ALTER TABLE lint_runs ADD COLUMN timings JSON NOT NULL DEFAULT '{}'")
    op.execute("UPDATE lint_runs SET phase='finished' WHERE status NOT IN ('queued','running')")
    op.execute("CREATE INDEX ix_paper_sources_revision_id ON paper_sources(revision_id)")
    op.execute("CREATE INDEX ix_reading_members_node ON reading_members(node_id)")
    op.execute("""CREATE INDEX ix_reading_units_root_version
        ON reading_units(root_claim_id, document_version_id)""")


def downgrade() -> None:
    raise RuntimeError("Restore the verified pre-upgrade backup; preserve Lint phase history")
