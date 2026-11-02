"""P3 proposals, immutable reasoning attempts and transactional lexical index."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE reasoning_attempts (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
        source_id VARCHAR(36) NOT NULL REFERENCES knowledge_nodes(id),
        target_id VARCHAR(36) NOT NULL REFERENCES knowledge_nodes(id),
        mode VARCHAR(24) NOT NULL, comparison JSON, output JSON NOT NULL,
        snapshot JSON NOT NULL, snapshot_hash VARCHAR(64) NOT NULL,
        model_run_ids JSON NOT NULL, created_at VARCHAR(40) NOT NULL)""")
    op.execute("CREATE INDEX ix_reasoning_project ON reasoning_attempts(project_id, created_at)")
    op.execute("CREATE INDEX ix_reasoning_source ON reasoning_attempts(source_id)")
    for table in ("relation_assertions", "entity_alignments"):
        op.execute(f"""CREATE TABLE {table} (
            id VARCHAR(36) PRIMARY KEY NOT NULL,
            attempt_id VARCHAR(36) NOT NULL UNIQUE REFERENCES reasoning_attempts(id),
            project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
            source_id VARCHAR(36) NOT NULL REFERENCES knowledge_nodes(id),
            target_id VARCHAR(36) NOT NULL REFERENCES knowledge_nodes(id),
            relation_type VARCHAR(24) NOT NULL, rationale TEXT NOT NULL, evidence_ids JSON NOT NULL,
            review_status VARCHAR(24) NOT NULL, revision INTEGER NOT NULL,
            created_at VARCHAR(40) NOT NULL)""")
        op.execute(f"CREATE INDEX ix_{table}_project ON {table}(project_id, review_status)")
        op.execute(f"CREATE INDEX ix_{table}_pair ON {table}(source_id, target_id)")
    op.execute("""CREATE TABLE semantic_reviews (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        relation_id VARCHAR(36) REFERENCES relation_assertions(id),
        alignment_id VARCHAR(36) REFERENCES entity_alignments(id),
        action VARCHAR(24) NOT NULL, reason TEXT NOT NULL, before JSON NOT NULL,
        after JSON NOT NULL, created_at VARCHAR(40) NOT NULL,
        CHECK ((relation_id IS NULL) != (alignment_id IS NULL)))""")
    op.execute("CREATE VIRTUAL TABLE knowledge_fts USING fts5(node_id UNINDEXED, content)")
    op.execute("INSERT INTO knowledge_fts(node_id, content) SELECT id, text FROM knowledge_nodes")
    op.execute("""CREATE TRIGGER knowledge_fts_insert AFTER INSERT ON knowledge_nodes BEGIN
        INSERT INTO knowledge_fts(node_id, content) VALUES (new.id, new.text); END""")
    op.execute("""CREATE TRIGGER knowledge_fts_update AFTER UPDATE OF text ON knowledge_nodes BEGIN
        DELETE FROM knowledge_fts WHERE node_id=old.id;
        INSERT INTO knowledge_fts(node_id, content) VALUES (new.id, new.text); END""")
    op.execute("""CREATE TRIGGER knowledge_fts_delete AFTER DELETE ON knowledge_nodes BEGIN
        DELETE FROM knowledge_fts WHERE node_id=old.id; END""")


def downgrade() -> None:
    raise RuntimeError("Restore the verified pre-upgrade backup to preserve scientific history")
