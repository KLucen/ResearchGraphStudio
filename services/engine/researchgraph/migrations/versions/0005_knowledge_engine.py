"""Additive knowledge engine schema; restore pre-upgrade backup to roll back."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE knowledge_operations (
        "key" VARCHAR(200) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        response JSON NOT NULL,
        PRIMARY KEY ("key")
    )
    """)
    op.execute("""
    CREATE TABLE authorized_roots (
        id VARCHAR(36) NOT NULL,
        project_id VARCHAR(36) NOT NULL,
        path TEXT NOT NULL,
        active BOOLEAN NOT NULL,
        created_at VARCHAR(40) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (project_id, path),
        FOREIGN KEY(project_id) REFERENCES projects (id)
    )
    """)
    op.execute("""
    CREATE TABLE graph_revisions (
        project_id VARCHAR(36) NOT NULL,
        revision INTEGER NOT NULL,
        PRIMARY KEY (project_id),
        FOREIGN KEY(project_id) REFERENCES projects (id)
    )
    """)
    op.execute("""
    CREATE TABLE note_snapshots (
        id VARCHAR(36) NOT NULL,
        root_id VARCHAR(36) NOT NULL,
        relative_path TEXT NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        text TEXT NOT NULL,
        created_at VARCHAR(40) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (root_id, relative_path, sha256),
        FOREIGN KEY(root_id) REFERENCES authorized_roots (id)
    )
    """)
    op.execute("CREATE INDEX ix_note_snapshots_root_id ON note_snapshots (root_id)")
    op.execute("""
    CREATE TABLE model_runs (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        document_version_id VARCHAR(36) NOT NULL,
        provider VARCHAR(40) NOT NULL,
        model TEXT NOT NULL,
        prompt_name VARCHAR(80) NOT NULL,
        prompt_hash VARCHAR(64) NOT NULL,
        schema_version VARCHAR(24) NOT NULL,
        input_hash VARCHAR(64) NOT NULL,
        parameters JSON NOT NULL,
        status VARCHAR(32) NOT NULL,
        raw_output TEXT,
        error TEXT,
        created_at VARCHAR(40) NOT NULL,
        finished_at VARCHAR(40),
        PRIMARY KEY (id),
        FOREIGN KEY(job_id) REFERENCES jobs (id),
        FOREIGN KEY(document_version_id) REFERENCES attachment_revisions (id)
    )
    """)
    op.execute("CREATE INDEX ix_model_runs_job_id ON model_runs (job_id)")
    op.execute("""
    CREATE TABLE sections (
        id VARCHAR(36) NOT NULL,
        document_version_id VARCHAR(36) NOT NULL,
        title TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        role VARCHAR(24) NOT NULL,
        parser VARCHAR(40) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(document_version_id) REFERENCES attachment_revisions (id)
    )
    """)
    op.execute("CREATE INDEX ix_sections_document_version_id ON sections (document_version_id)")
    op.execute("""
    CREATE TABLE zotero_links (
        id VARCHAR(36) NOT NULL,
        paper_id VARCHAR(36) NOT NULL,
        document_version_id VARCHAR(36) NOT NULL,
        library_id VARCHAR(80) NOT NULL,
        item_key VARCHAR(8) NOT NULL,
        attachment_key VARCHAR(8) NOT NULL,
        metadata_snapshot JSON NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (paper_id, library_id, item_key, attachment_key),
        FOREIGN KEY(paper_id) REFERENCES papers (id),
        FOREIGN KEY(document_version_id) REFERENCES attachment_revisions (id)
    )
    """)
    op.execute("CREATE INDEX ix_zotero_links_paper_id ON zotero_links (paper_id)")
    op.execute("""
    CREATE TABLE evidence_spans (
        id VARCHAR(36) NOT NULL,
        document_version_id VARCHAR(36) NOT NULL,
        section_id VARCHAR(36) NOT NULL,
        paragraph_id VARCHAR(36) NOT NULL,
        page_index INTEGER NOT NULL,
        start_offset INTEGER NOT NULL,
        end_offset INTEGER NOT NULL,
        quote TEXT NOT NULL,
        text_sha256 VARCHAR(64) NOT NULL,
        normalization VARCHAR(40) NOT NULL,
        bbox_list JSON NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (paragraph_id, start_offset, end_offset),
        FOREIGN KEY(document_version_id)
            REFERENCES attachment_revisions (id),
        FOREIGN KEY(section_id) REFERENCES sections (id),
        FOREIGN KEY(paragraph_id) REFERENCES chunks (id)
    )
    """)
    op.execute(
        "CREATE INDEX ix_evidence_spans_document_version_id ON evidence_spans (document_version_id)"
    )
    op.execute("""
    CREATE TABLE knowledge_nodes (
        id VARCHAR(36) NOT NULL,
        paper_id VARCHAR(36) NOT NULL,
        document_version_id VARCHAR(36) NOT NULL,
        kind VARCHAR(24) NOT NULL,
        text TEXT NOT NULL,
        payload JSON NOT NULL,
        origin VARCHAR(40) NOT NULL,
        authorship VARCHAR(24) NOT NULL,
        source_status VARCHAR(24) NOT NULL,
        review_status VARCHAR(24) NOT NULL,
        issues JSON NOT NULL,
        dimension VARCHAR(100),
        known_state VARCHAR(24),
        value TEXT,
        unit TEXT,
        fingerprint VARCHAR(64) NOT NULL,
        model_run_id VARCHAR(36),
        revision INTEGER NOT NULL,
        created_at VARCHAR(40) NOT NULL,
        updated_at VARCHAR(40) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (document_version_id, fingerprint),
        FOREIGN KEY(paper_id) REFERENCES papers (id),
        FOREIGN KEY(document_version_id)
            REFERENCES attachment_revisions (id),
        FOREIGN KEY(model_run_id) REFERENCES model_runs (id)
    )
    """)
    op.execute("CREATE INDEX ix_knowledge_nodes_dimension ON knowledge_nodes (dimension)")
    op.execute(
        "CREATE INDEX ix_knowledge_nodes_document_version_id "
        "ON knowledge_nodes (document_version_id)"
    )
    op.execute("CREATE INDEX ix_knowledge_nodes_kind ON knowledge_nodes (kind)")
    op.execute("CREATE INDEX ix_knowledge_nodes_paper_id ON knowledge_nodes (paper_id)")
    op.execute("CREATE INDEX ix_knowledge_nodes_review_status ON knowledge_nodes (review_status)")
    op.execute("CREATE INDEX ix_knowledge_nodes_source_status ON knowledge_nodes (source_status)")
    op.execute("""
    CREATE TABLE annotations (
        id VARCHAR(36) NOT NULL,
        link_id VARCHAR(36) NOT NULL,
        document_version_id VARCHAR(36) NOT NULL,
        annotation_key VARCHAR(8) NOT NULL,
        annotation_type VARCHAR(40) NOT NULL,
        text TEXT NOT NULL,
        comment TEXT NOT NULL,
        source_position JSON NOT NULL,
        source_hash VARCHAR(64) NOT NULL,
        anchor_status VARCHAR(24) NOT NULL,
        evidence_id VARCHAR(36),
        created_at VARCHAR(40) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (link_id, annotation_key, source_hash),
        FOREIGN KEY(link_id) REFERENCES zotero_links (id),
        FOREIGN KEY(document_version_id)
            REFERENCES attachment_revisions (id),
        FOREIGN KEY(evidence_id) REFERENCES evidence_spans (id)
    )
    """)
    op.execute(
        "CREATE INDEX ix_annotations_document_version_id ON annotations (document_version_id)"
    )
    op.execute("""
    CREATE TABLE knowledge_dependencies (
        node_id VARCHAR(36) NOT NULL,
        dependee_id VARCHAR(36) NOT NULL,
        role VARCHAR(32) NOT NULL,
        PRIMARY KEY (node_id, dependee_id, role),
        FOREIGN KEY(node_id) REFERENCES knowledge_nodes (id),
        FOREIGN KEY(dependee_id) REFERENCES knowledge_nodes (id)
    )
    """)
    op.execute("""
    CREATE TABLE node_evidence_links (
        node_id VARCHAR(36) NOT NULL,
        evidence_id VARCHAR(36) NOT NULL,
        role VARCHAR(24) NOT NULL,
        PRIMARY KEY (node_id, evidence_id),
        FOREIGN KEY(node_id) REFERENCES knowledge_nodes (id),
        FOREIGN KEY(evidence_id) REFERENCES evidence_spans (id)
    )
    """)
    op.execute("""
    CREATE TABLE review_decisions (
        id VARCHAR(36) NOT NULL,
        node_id VARCHAR(36) NOT NULL,
        action VARCHAR(24) NOT NULL,
        actor VARCHAR(40) NOT NULL,
        reason TEXT NOT NULL,
        "before" JSON NOT NULL,
        "after" JSON NOT NULL,
        created_at VARCHAR(40) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(node_id) REFERENCES knowledge_nodes (id)
    )
    """)
    op.execute("CREATE INDEX ix_review_decisions_node_id ON review_decisions (node_id)")
    op.add_column("knowledge_events", sa.Column("actor", sa.String(40), nullable=True))
    op.add_column("knowledge_events", sa.Column("model_run_id", sa.String(36), nullable=True))
    op.add_column("knowledge_events", sa.Column("before_revision", sa.Integer(), nullable=True))
    op.add_column("knowledge_events", sa.Column("after_revision", sa.Integer(), nullable=True))
    op.add_column("knowledge_events", sa.Column("trigger", sa.String(80), nullable=True))


def downgrade() -> None:
    raise RuntimeError("涓嶆敮鎸佸師鍦伴檷绾э紱璇锋仮澶嶅崌绾у墠澶囦唤")
