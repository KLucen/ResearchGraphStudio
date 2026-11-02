"""Add reading metadata/snapshots only; preserve every existing table and column."""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE candidate_metadata (
        node_id TEXT PRIMARY KEY NOT NULL REFERENCES knowledge_nodes(id),
        quality JSON NOT NULL, validation_status TEXT NOT NULL,
        canonical_id TEXT REFERENCES knowledge_nodes(id), policy_version TEXT NOT NULL)""")
    op.execute("""CREATE TABLE reading_units (
        id TEXT PRIMARY KEY NOT NULL,
        document_version_id TEXT NOT NULL REFERENCES attachment_revisions(id),
        root_claim_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
        snapshot_hash TEXT NOT NULL, model_run_id TEXT REFERENCES model_runs(id),
        rationale TEXT NOT NULL)""")
    op.execute("""CREATE TABLE reading_members (
        unit_id TEXT NOT NULL REFERENCES reading_units(id),
        node_id TEXT NOT NULL REFERENCES knowledge_nodes(id), association_ids JSON NOT NULL,
        PRIMARY KEY(unit_id, node_id))""")
    op.execute("""CREATE TABLE reading_selections (
        id TEXT PRIMARY KEY NOT NULL, paper_id TEXT NOT NULL REFERENCES papers(id),
        document_version_id TEXT NOT NULL REFERENCES attachment_revisions(id),
        revision INTEGER NOT NULL, snapshot_hash TEXT NOT NULL, data JSON NOT NULL,
        created_at TEXT NOT NULL, UNIQUE(paper_id, revision))""")
    op.execute("CREATE INDEX ix_reading_selections_paper_id ON reading_selections(paper_id)")
    op.execute("""CREATE TABLE reading_heads (
        paper_id TEXT PRIMARY KEY NOT NULL REFERENCES papers(id),
        selection_id TEXT NOT NULL REFERENCES reading_selections(id), revision INTEGER NOT NULL)""")
    op.execute("""CREATE TABLE reading_preferences (
        node_id TEXT PRIMARY KEY NOT NULL REFERENCES knowledge_nodes(id),
        action TEXT NOT NULL, reason TEXT NOT NULL)""")
    op.execute("""CREATE TABLE reading_checkpoints (
        key TEXT PRIMARY KEY NOT NULL,
        document_version_id TEXT NOT NULL REFERENCES attachment_revisions(id),
        stage TEXT NOT NULL, input_hash TEXT NOT NULL, response JSON NOT NULL)""")


def downgrade() -> None:
    raise RuntimeError("Restore the verified pre-upgrade backup; never discard reading history")
