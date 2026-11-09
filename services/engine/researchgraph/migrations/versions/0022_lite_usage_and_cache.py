"""Add Lite usage accounting and versioned cache foundations."""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE lite_token_usage (
            id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
            paper_id VARCHAR(36) NOT NULL REFERENCES papers(id),
            document_version_id VARCHAR(36) NOT NULL REFERENCES attachment_revisions(id),
            section_id VARCHAR(36) REFERENCES sections(id),
            task_run_id VARCHAR(36),
            task_kind VARCHAR(24) NOT NULL,
            provider VARCHAR(40),
            model TEXT,
            prompt_version VARCHAR(80),
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            retry_count INTEGER NOT NULL DEFAULT 0,
            cache_hit BOOLEAN NOT NULL DEFAULT 0,
            usage_source VARCHAR(16) NOT NULL DEFAULT 'unknown',
            cost_estimate FLOAT,
            status VARCHAR(24) NOT NULL DEFAULT 'succeeded',
            reason_code VARCHAR(80),
            metadata JSON NOT NULL DEFAULT '{}',
            created_at VARCHAR(40) NOT NULL
        )"""
    )
    op.execute(
        """CREATE TABLE lite_cache_entries (
            cache_key VARCHAR(64) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
            task_kind VARCHAR(24) NOT NULL,
            paper_id VARCHAR(36) NOT NULL REFERENCES papers(id),
            document_version_id VARCHAR(36) NOT NULL REFERENCES attachment_revisions(id),
            section_id VARCHAR(36) REFERENCES sections(id),
            input_fingerprint VARCHAR(64) NOT NULL,
            prompt_version VARCHAR(80) NOT NULL,
            schema_version VARCHAR(80) NOT NULL,
            provider VARCHAR(40) NOT NULL,
            model TEXT NOT NULL,
            config_fingerprint VARCHAR(64) NOT NULL,
            source_hash VARCHAR(64) NOT NULL,
            state VARCHAR(16) NOT NULL DEFAULT 'fresh',
            stale_reason VARCHAR(120),
            response JSON,
            hit_count INTEGER NOT NULL DEFAULT 0,
            created_at VARCHAR(40) NOT NULL,
            updated_at VARCHAR(40) NOT NULL
        )"""
    )
    op.execute(
        "CREATE INDEX ix_lite_usage_project_created ON lite_token_usage(project_id, created_at)"
    )
    op.execute("CREATE INDEX ix_lite_usage_project_kind ON lite_token_usage(project_id, task_kind)")
    op.execute("CREATE INDEX ix_lite_usage_paper ON lite_token_usage(paper_id, created_at)")
    op.execute(
        "CREATE INDEX ix_lite_cache_project_kind ON lite_cache_entries(project_id, task_kind)"
    )
    op.execute(
        "CREATE INDEX ix_lite_cache_document ON lite_cache_entries(document_version_id, task_kind)"
    )
    op.execute("CREATE INDEX ix_lite_usage_task_run ON lite_token_usage(task_run_id)")


def downgrade() -> None:
    op.execute("DROP TABLE lite_cache_entries")
    op.execute("DROP TABLE lite_token_usage")
