"""Add explicit saved Query Synthesis/Insight without rewriting existing knowledge."""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE query_saved_knowledge (
        id TEXT PRIMARY KEY NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
        kind TEXT NOT NULL, title TEXT NOT NULL,
        source_query_id TEXT NOT NULL REFERENCES query_runs(id),
        answer_version_id TEXT NOT NULL REFERENCES query_answer_versions(id),
        document_id TEXT NOT NULL REFERENCES query_documents(id),
        document_version_id TEXT NOT NULL REFERENCES query_document_versions(id),
        fingerprint TEXT NOT NULL, input_hash TEXT NOT NULL,
        selected_passage_refs JSON NOT NULL, passage_ids JSON NOT NULL,
        manifest JSON NOT NULL, graph_revision INTEGER NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(project_id,fingerprint))""")
    op.execute(
        "CREATE INDEX ix_query_saved_knowledge_project_id ON query_saved_knowledge(project_id)"
    )
    op.execute(
        "CREATE INDEX ix_query_saved_knowledge_source_query_id "
        "ON query_saved_knowledge(source_query_id)"
    )


def downgrade() -> None:
    raise RuntimeError("Restore the verified pre-upgrade backup; preserve saved Query knowledge")
