"""Independent comment purpose grants and explicit-import annotation currentness."""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE p5_annotation_use_grants (
        annotation_id VARCHAR(36) PRIMARY KEY REFERENCES annotations(id),
        allow_local BOOLEAN NOT NULL DEFAULT 1,
        allow_model BOOLEAN NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0)""")
    op.execute("""CREATE TABLE p5_annotation_heads (
        link_id VARCHAR(36) NOT NULL REFERENCES zotero_links(id),
        annotation_key VARCHAR(8) NOT NULL,
        annotation_id VARCHAR(36) NOT NULL REFERENCES annotations(id),
        removed BOOLEAN NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(link_id,annotation_key))""")
    # Existing imports are a last-known local baseline, never a claim about live Zotero state.
    op.execute("""INSERT INTO p5_annotation_heads
        (link_id,annotation_key,annotation_id,removed,revision)
        SELECT a.link_id,a.annotation_key,a.id,0,0 FROM annotations a WHERE NOT EXISTS
        (SELECT 1 FROM annotations b WHERE b.link_id=a.link_id AND b.annotation_key=a.annotation_key
        AND (b.created_at>a.created_at OR (b.created_at=a.created_at AND b.id>a.id)))""")


def downgrade() -> None:
    op.execute("DROP TABLE p5_annotation_heads")
    op.execute("DROP TABLE p5_annotation_use_grants")
