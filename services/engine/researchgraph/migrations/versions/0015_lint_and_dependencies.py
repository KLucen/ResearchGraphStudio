"""Add derived reverse dependencies and resumable deterministic Lint reports."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE dependency_cursors (
        project_id TEXT PRIMARY KEY NOT NULL REFERENCES projects(id),
        event_sequence INTEGER NOT NULL, generation INTEGER NOT NULL,
        objects JSON NOT NULL, changes JSON NOT NULL, updated_at TEXT NOT NULL)""")
    op.execute("""CREATE TABLE dependency_index (
        id TEXT PRIMARY KEY NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
        dependent_type TEXT NOT NULL, dependent_id TEXT NOT NULL,
        source_type TEXT NOT NULL, source_id TEXT NOT NULL, role TEXT NOT NULL,
        category TEXT NOT NULL, expected JSON NOT NULL, state TEXT NOT NULL,
        UNIQUE(project_id, dependent_type, dependent_id, source_type, source_id, role))""")
    op.execute("""CREATE INDEX ix_dependency_reverse
        ON dependency_index(project_id, source_type, source_id)""")
    op.execute("""CREATE INDEX ix_dependency_forward
        ON dependency_index(project_id, dependent_type, dependent_id)""")
    op.execute("""CREATE TABLE lint_runs (
        id TEXT PRIMARY KEY NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
        status TEXT NOT NULL, scope JSON NOT NULL, scope_hash TEXT NOT NULL,
        rule_version TEXT NOT NULL, event_sequence INTEGER NOT NULL,
        input_hash TEXT NOT NULL, targets JSON NOT NULL, processed INTEGER NOT NULL,
        counts JSON NOT NULL, diff JSON NOT NULL, previous_run_id TEXT, errors JSON NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, finished_at TEXT)""")
    op.execute("CREATE INDEX ix_lint_runs_project_id ON lint_runs(project_id)")
    op.execute("""CREATE TABLE lint_issues (
        id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES lint_runs(id),
        fingerprint TEXT NOT NULL, code TEXT NOT NULL, rule_version TEXT NOT NULL,
        severity TEXT NOT NULL, category TEXT NOT NULL, object_type TEXT NOT NULL,
        object_id TEXT NOT NULL, paper_id TEXT, location JSON NOT NULL,
        message TEXT NOT NULL, suggestion TEXT NOT NULL, lifecycle TEXT NOT NULL,
        UNIQUE(run_id, fingerprint))""")
    op.execute("CREATE INDEX ix_lint_issues_run_id ON lint_issues(run_id)")
    op.execute("CREATE INDEX ix_lint_issue_filter ON lint_issues(run_id, severity, category)")
    op.execute("""CREATE TABLE lint_operations (
        key TEXT PRIMARY KEY NOT NULL, request_hash TEXT NOT NULL, response JSON NOT NULL)""")


def downgrade() -> None:
    raise RuntimeError("Restore the verified pre-upgrade backup; preserve Lint report history")
