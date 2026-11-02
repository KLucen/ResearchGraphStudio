"""Share model configuration across the workspace without changing credential references."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite cannot rebuild a referenced parent while FK enforcement is active.
    # Preserve and restore every legacy selection within the migration transaction.
    op.execute("CREATE TABLE saved_model_roles AS SELECT * FROM project_model_roles")
    op.drop_table("project_model_roles")
    with op.batch_alter_table("model_profiles") as batch:
        batch.alter_column("project_id", existing_type=sa.String(36), nullable=True)
    op.execute("""CREATE TABLE project_model_roles (
        project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
        role VARCHAR(24) NOT NULL, profile_id VARCHAR(36) NOT NULL REFERENCES model_profiles(id),
        PRIMARY KEY (project_id, role)
    )""")
    op.execute("INSERT INTO project_model_roles SELECT * FROM saved_model_roles")
    op.execute("""CREATE TABLE global_model_roles (
        role VARCHAR(24) PRIMARY KEY NOT NULL,
        profile_id VARCHAR(36) NOT NULL REFERENCES model_profiles(id)
    )""")
    # Conflicting project choices remain intact; do not arbitrarily choose a model.
    op.execute("""INSERT INTO global_model_roles(role, profile_id)
        SELECT r.role, MIN(r.profile_id) FROM saved_model_roles r
        JOIN model_profiles p ON p.id=r.profile_id WHERE p.active=1
        GROUP BY r.role HAVING COUNT(DISTINCT r.profile_id)=1""")
    op.drop_table("saved_model_roles")


def downgrade() -> None:
    raise RuntimeError("Restore the pre-migration backup instead of discarding global settings")
