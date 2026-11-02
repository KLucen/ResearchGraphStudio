"""Project model selection; credentials live in the OS vault, never SQLite."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE model_profiles (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
        name TEXT NOT NULL, provider VARCHAR(24) NOT NULL, base_url TEXT NOT NULL,
        model TEXT NOT NULL, parameters JSON NOT NULL, credential_ref VARCHAR(36),
        secret_refs JSON NOT NULL, active BOOLEAN NOT NULL, updated_at VARCHAR(40) NOT NULL
    )""")
    op.execute("CREATE INDEX ix_model_profiles_project_id ON model_profiles(project_id)")
    op.execute("""CREATE TABLE project_model_roles (
        project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
        role VARCHAR(24) NOT NULL, profile_id VARCHAR(36) NOT NULL REFERENCES model_profiles(id),
        PRIMARY KEY (project_id, role)
    )""")


def downgrade() -> None:
    raise RuntimeError("Restore the pre-migration backup instead of discarding configuration")
