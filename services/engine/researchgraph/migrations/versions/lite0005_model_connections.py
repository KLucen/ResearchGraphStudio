"""Store provider endpoint credentials separately from model profiles."""

from uuid import uuid4

from alembic import op
from sqlalchemy import inspect, text

revision = "lite0005"
down_revision = "lite0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("model_connections"):
        op.execute(
            """
            CREATE TABLE model_connections (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                project_id VARCHAR(36),
                name TEXT NOT NULL,
                provider VARCHAR(24) NOT NULL,
                base_url TEXT NOT NULL,
                credential_ref VARCHAR(36),
                secret_refs JSON NOT NULL,
                active BOOLEAN NOT NULL DEFAULT 1,
                updated_at VARCHAR(40) NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects (id)
            )
            """
        )
        op.execute("CREATE INDEX ix_model_connections_project_id ON model_connections (project_id)")
    inspector = inspect(bind)
    profile_columns = {column["name"] for column in inspector.get_columns("model_profiles")}
    if "connection_id" not in profile_columns:
        op.execute("ALTER TABLE model_profiles ADD COLUMN connection_id VARCHAR(36)")
        op.execute("CREATE INDEX ix_model_profiles_connection_id ON model_profiles (connection_id)")

    # Existing Lite profiles are converted into one reusable connection each.
    # Credentials remain references only; no key material is copied into SQLite.
    rows = (
        bind.execute(
            text(
                "SELECT id, project_id, name, provider, base_url, credential_ref, "
                "secret_refs, updated_at "
                "FROM model_profiles WHERE connection_id IS NULL"
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        connection_id = str(uuid4())
        bind.execute(
            text(
                "INSERT INTO model_connections "
                "(id, project_id, name, provider, base_url, credential_ref, "
                "secret_refs, active, updated_at) "
                "VALUES (:id, :project_id, :name, :provider, :base_url, "
                ":credential_ref, :secret_refs, 1, :updated_at)"
            ),
            {
                "id": connection_id,
                "project_id": row["project_id"],
                "name": f"{row['name']} 连接",
                "provider": row["provider"],
                "base_url": row["base_url"],
                "credential_ref": row["credential_ref"],
                "secret_refs": row["secret_refs"] or "[]",
                "updated_at": row["updated_at"],
            },
        )
        bind.execute(
            text("UPDATE model_profiles SET connection_id = :connection_id WHERE id = :profile_id"),
            {"connection_id": connection_id, "profile_id": row["id"]},
        )


def downgrade() -> None:
    raise RuntimeError("不支持原地降级；请恢复 Lite 备份")
