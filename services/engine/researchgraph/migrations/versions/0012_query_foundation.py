"""Add local Query execution, immutable reading documents and rebuildable indexes."""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = [
        """CREATE TABLE query_runs (
            id TEXT PRIMARY KEY NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
            request JSON NOT NULL, snapshot JSON NOT NULL, input_hash TEXT NOT NULL,
            status TEXT NOT NULL, error TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
        "CREATE INDEX ix_query_runs_project_id ON query_runs(project_id)",
        """CREATE TABLE query_model_runs (
            id TEXT PRIMARY KEY NOT NULL, query_run_id TEXT NOT NULL REFERENCES query_runs(id),
            project_id TEXT NOT NULL REFERENCES projects(id), provider TEXT NOT NULL,
            model TEXT NOT NULL, prompt_name TEXT NOT NULL, prompt_hash TEXT NOT NULL,
            schema_version TEXT NOT NULL, input_hash TEXT NOT NULL, parameters JSON NOT NULL,
            manifest JSON NOT NULL, status TEXT NOT NULL, raw_output TEXT, error TEXT,
            created_at TEXT NOT NULL, finished_at TEXT)""",
        "CREATE INDEX ix_query_model_runs_query_run_id ON query_model_runs(query_run_id)",
        """CREATE TABLE query_answer_versions (
            id TEXT PRIMARY KEY NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
            query_run_id TEXT NOT NULL REFERENCES query_runs(id),
            model_run_id TEXT REFERENCES query_model_runs(id), revision INTEGER NOT NULL,
            state TEXT NOT NULL, data JSON NOT NULL, input_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(query_run_id,revision))""",
        "CREATE INDEX ix_query_answer_versions_project_id ON query_answer_versions(project_id)",
        "CREATE INDEX ix_query_answer_versions_query_run_id ON query_answer_versions(query_run_id)",
        """CREATE TABLE query_documents (
            id TEXT PRIMARY KEY NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
            kind TEXT NOT NULL, title TEXT NOT NULL, current_version_id TEXT,
            created_at TEXT NOT NULL)""",
        "CREATE INDEX ix_query_documents_project_id ON query_documents(project_id)",
        """CREATE TABLE query_document_versions (
            id TEXT PRIMARY KEY NOT NULL, document_id TEXT NOT NULL REFERENCES query_documents(id),
            revision INTEGER NOT NULL, state TEXT NOT NULL, sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(document_id,revision))""",
        "CREATE INDEX ix_query_document_versions_document_id "
        "ON query_document_versions(document_id)",
        """CREATE TABLE query_passages (
            id TEXT PRIMARY KEY NOT NULL,
            version_id TEXT NOT NULL REFERENCES query_document_versions(id),
            ordinal INTEGER NOT NULL, local_ref TEXT NOT NULL, text TEXT NOT NULL,
            sha256 TEXT NOT NULL, attribution TEXT NOT NULL, dependencies JSON NOT NULL,
            caveats JSON NOT NULL, UNIQUE(version_id,local_ref))""",
        "CREATE INDEX ix_query_passages_version_id ON query_passages(version_id)",
        """CREATE TABLE query_file_bindings (
            document_id TEXT PRIMARY KEY NOT NULL REFERENCES query_documents(id),
            root_id TEXT NOT NULL REFERENCES authorized_roots(id), relative_path TEXT NOT NULL,
            version_id TEXT NOT NULL REFERENCES query_document_versions(id), sha256 TEXT NOT NULL,
            conflict BOOLEAN NOT NULL)""",
        """CREATE TABLE note_use_grants (
            root_id TEXT PRIMARY KEY NOT NULL REFERENCES authorized_roots(id),
            allow_local BOOLEAN NOT NULL, allow_model BOOLEAN NOT NULL,
            revision INTEGER NOT NULL)""",
        """CREATE TABLE query_operations (
            key TEXT PRIMARY KEY NOT NULL, request_hash TEXT NOT NULL, response JSON NOT NULL)""",
        """CREATE TABLE query_index_entries (
            id TEXT PRIMARY KEY NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
            source_kind TEXT NOT NULL, object_id TEXT NOT NULL, text TEXT NOT NULL,
            aliases TEXT NOT NULL, data JSON NOT NULL, UNIQUE(project_id,source_kind,object_id))""",
        "CREATE INDEX ix_query_index_entries_project_id ON query_index_entries(project_id)",
        """CREATE VIRTUAL TABLE query_fts USING fts5(
            entry_id UNINDEXED,project_id UNINDEXED,text,aliases,tokenize='unicode61')""",
    ]
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    raise RuntimeError("Restore the verified pre-upgrade backup; preserve Query/document history")
