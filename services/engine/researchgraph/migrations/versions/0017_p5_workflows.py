"""P5 project model workflow ledger; no changes to existing scientific or Query rows."""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE p5_workflows (
        id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
        kind VARCHAR(32) NOT NULL, request JSON NOT NULL, snapshot JSON NOT NULL,
        input_hash VARCHAR(64) NOT NULL, status VARCHAR(24) NOT NULL,
        job_id VARCHAR(36) REFERENCES jobs(id), result JSON, error_code VARCHAR(80),
        error TEXT, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)""")
    op.execute("CREATE INDEX ix_p5_workflows_project_id ON p5_workflows(project_id)")
    op.execute("""CREATE TABLE p5_model_runs (
        id VARCHAR(36) PRIMARY KEY, workflow_id VARCHAR(36) NOT NULL REFERENCES p5_workflows(id),
        job_id VARCHAR(36) NOT NULL REFERENCES jobs(id), sequence INTEGER NOT NULL,
        prompt_name VARCHAR(80) NOT NULL, prompt_hash VARCHAR(64) NOT NULL,
        input_hash VARCHAR(64) NOT NULL, parameters JSON NOT NULL,
        status VARCHAR(32) NOT NULL, raw_output TEXT, error TEXT,
        created_at VARCHAR(40) NOT NULL, finished_at VARCHAR(40),
        UNIQUE(workflow_id,sequence))""")
    op.execute("CREATE INDEX ix_p5_model_runs_workflow_id ON p5_model_runs(workflow_id)")


def downgrade() -> None:
    op.execute("DROP TABLE p5_model_runs")
    op.execute("DROP TABLE p5_workflows")
