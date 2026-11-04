"""Keep old source/evidence rows intact; add versioned layout/section/table artifacts."""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE document_parses (
        id TEXT PRIMARY KEY NOT NULL,
        document_version_id TEXT NOT NULL REFERENCES attachment_revisions(id),
        parser_version TEXT NOT NULL, source_sha256 TEXT NOT NULL,
        data JSON NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(document_version_id, parser_version))""")
    op.execute(
        "CREATE INDEX ix_document_parses_document_version_id "
        "ON document_parses(document_version_id)"
    )


def downgrade() -> None:
    raise RuntimeError("Restore the verified pre-upgrade backup; preserve parse history")
