"""Display metadata, source structure and independent visual layouts. No old-row rewrite."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE knowledge_display (
        node_id VARCHAR(36) PRIMARY KEY NOT NULL REFERENCES knowledge_nodes(id),
        data JSON NOT NULL, model_run_id VARCHAR(36) NOT NULL REFERENCES model_runs(id),
        source_revision INTEGER NOT NULL)""")
    op.execute("""CREATE TABLE source_assertions (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
        source_id VARCHAR(36) NOT NULL REFERENCES knowledge_nodes(id),
        target_id VARCHAR(36) NOT NULL REFERENCES knowledge_nodes(id),
        relation VARCHAR(32) NOT NULL, evidence_ids JSON NOT NULL,
        model_run_id VARCHAR(36) NOT NULL REFERENCES model_runs(id))""")
    for column in ("project_id", "source_id", "target_id"):
        op.execute(f"CREATE INDEX ix_source_assertions_{column} ON source_assertions({column})")
    op.execute("""CREATE TABLE graph_layouts (
        project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
        view_id VARCHAR(60) NOT NULL, version INTEGER NOT NULL, data JSON NOT NULL,
        updated_at TEXT NOT NULL, PRIMARY KEY (project_id, view_id))""")


def downgrade() -> None:
    raise RuntimeError("Restore the verified pre-upgrade backup; preserve layouts and history")
