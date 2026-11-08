"""Extend the shared document registry with stable Wiki sections and a publication ledger."""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE wiki_pages (
        document_id TEXT PRIMARY KEY NOT NULL REFERENCES query_documents(id),
        head_version_id TEXT NOT NULL REFERENCES query_document_versions(id),
        created_at TEXT NOT NULL)""")
    op.execute("""CREATE TABLE wiki_versions (
        version_id TEXT PRIMARY KEY NOT NULL REFERENCES query_document_versions(id),
        title TEXT NOT NULL, content_hash TEXT NOT NULL, markdown TEXT NOT NULL,
        "references" JSON NOT NULL, provenance JSON NOT NULL, base_version_id TEXT)""")
    op.execute("""CREATE TABLE wiki_sections (
        passage_id TEXT PRIMARY KEY NOT NULL REFERENCES query_passages(id),
        version_id TEXT NOT NULL REFERENCES query_document_versions(id), section_id TEXT NOT NULL,
        heading TEXT NOT NULL, conditions JSON NOT NULL, links JSON NOT NULL, stale_reason TEXT,
        UNIQUE(version_id, section_id))""")
    op.execute("CREATE INDEX ix_wiki_sections_version_id ON wiki_sections(version_id)")
    op.execute("CREATE INDEX ix_wiki_sections_section_id ON wiki_sections(section_id)")
    op.execute("""CREATE TABLE wiki_write_roots (
        id TEXT PRIMARY KEY NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
        path TEXT NOT NULL, device TEXT NOT NULL, inode TEXT NOT NULL, active BOOLEAN NOT NULL,
        revision INTEGER NOT NULL, created_at TEXT NOT NULL, UNIQUE(project_id,path))""")
    op.execute("CREATE INDEX ix_wiki_write_roots_project_id ON wiki_write_roots(project_id)")
    op.execute("""CREATE TABLE wiki_file_bindings (
        document_id TEXT PRIMARY KEY NOT NULL REFERENCES query_documents(id),
        root_id TEXT NOT NULL REFERENCES wiki_write_roots(id), relative_path TEXT NOT NULL,
        version_id TEXT NOT NULL REFERENCES query_document_versions(id), sha256 TEXT NOT NULL,
        device TEXT NOT NULL, inode TEXT NOT NULL,
        updated_at TEXT NOT NULL, UNIQUE(root_id,relative_path))""")
    op.execute("""CREATE TABLE wiki_publications (
        id TEXT PRIMARY KEY NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
        document_id TEXT NOT NULL REFERENCES query_documents(id),
        version_id TEXT NOT NULL REFERENCES query_document_versions(id),
        root_id TEXT NOT NULL REFERENCES wiki_write_roots(id), root_revision INTEGER NOT NULL,
        key TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL, relative_path TEXT NOT NULL,
        base_hash TEXT, target_hash TEXT NOT NULL, stage_identity JSON,
        state TEXT NOT NULL, error TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    op.execute("CREATE INDEX ix_wiki_publications_project_id ON wiki_publications(project_id)")
    op.execute("CREATE INDEX ix_wiki_publications_document_id ON wiki_publications(document_id)")
    op.execute("""CREATE TABLE wiki_file_observations (
        id TEXT PRIMARY KEY NOT NULL, document_id TEXT NOT NULL REFERENCES query_documents(id),
        root_id TEXT NOT NULL REFERENCES wiki_write_roots(id), sha256 TEXT NOT NULL,
        text TEXT NOT NULL, created_at TEXT NOT NULL)""")
    op.execute(
        "CREATE INDEX ix_wiki_file_observations_document_id ON wiki_file_observations(document_id)"
    )


def downgrade() -> None:
    raise RuntimeError("Restore the pre-upgrade backup; preserve Wiki versions and publications")
