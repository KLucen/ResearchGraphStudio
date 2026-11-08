"""Independent external Markdown origins; existing document and scientific rows stay intact."""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE external_document_versions (
        version_id VARCHAR(36) PRIMARY KEY REFERENCES query_document_versions(id),
        root_id VARCHAR(36) NOT NULL REFERENCES authorized_roots(id),
        relative_path TEXT NOT NULL, sha256 VARCHAR(64) NOT NULL,
        title TEXT NOT NULL, attribution VARCHAR(32) NOT NULL)""")
    op.execute(
        "CREATE INDEX ix_external_document_versions_root_id ON external_document_versions(root_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE external_document_versions")
