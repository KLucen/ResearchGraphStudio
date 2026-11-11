"""Global model settings with compatibility routes. Responses never expose credentials."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError
from researchgraph.credentials import CredentialError, SecretStore
from researchgraph.model_adapters import new_task_parameters
from researchgraph.model_settings import (
    ConnectionInput,
    ConnectionView,
    GlobalModelRole,
    ModelConnection,
    ModelProfile,
    ProfileInput,
    ProfileView,
    RolesInput,
    SettingsView,
    _connection_for_profile,
    from_snapshot,
    require_profile,
    require_project,
    save_connection,
    save_profile,
    settings_view,
)
from researchgraph.providers import ConfiguredProvider


def register_settings_api(app: FastAPI, engine: Callable[[], Engine], data_dir: Path) -> None:
    secrets = SecretStore(data_dir)

    @app.get("/api/v1/settings/models", response_model=SettingsView)
    @app.get("/api/v1/projects/{project_id}/models", response_model=SettingsView)
    def settings(project_id: str | None = None) -> SettingsView:
        with Session(engine()) as session:
            return settings_view(session, project_id)

    @app.post("/api/v1/settings/connections", response_model=ConnectionView)
    @app.post("/api/v1/projects/{project_id}/connections", response_model=ConnectionView)
    def create_connection(body: ConnectionInput, project_id: str | None = None) -> ConnectionView:
        try:
            with Session(engine()) as session, session.begin():
                return save_connection(session, secrets, project_id, body)
        except CredentialError as error:
            raise KnowledgeError("CREDENTIAL_FAILURE", str(error)) from None

    @app.post("/api/v1/settings/connections/{connection_id}/update", response_model=ConnectionView)
    @app.post(
        "/api/v1/projects/{project_id}/connections/{connection_id}/update",
        response_model=ConnectionView,
    )
    def update_connection(
        connection_id: str, body: ConnectionInput, project_id: str | None = None
    ) -> ConnectionView:
        try:
            with Session(engine()) as session, session.begin():
                return save_connection(session, secrets, project_id, body, connection_id)
        except CredentialError as error:
            raise KnowledgeError("CREDENTIAL_FAILURE", str(error)) from None

    @app.post("/api/v1/settings/connections/{connection_id}/delete")
    @app.post("/api/v1/projects/{project_id}/connections/{connection_id}/delete")
    def remove_connection(connection_id: str, project_id: str | None = None) -> dict[str, bool]:
        with Session(engine()) as session, session.begin():
            require_project(session, project_id)
            connection = session.get(ModelConnection, connection_id)
            if connection is None or not connection.active:
                raise KnowledgeError("CONNECTION_NOT_FOUND", "模型连接不存在或已删除")
            for reference in connection.secret_refs:
                try:
                    secrets.delete(reference)
                except CredentialError as error:
                    raise KnowledgeError("CREDENTIAL_FAILURE", str(error)) from None
            connection.active, connection.credential_ref, connection.secret_refs = False, None, []
            for profile in session.scalars(
                select(ModelProfile).where(ModelProfile.connection_id == connection_id)
            ):
                profile.active = False
            session.execute(
                delete(GlobalModelRole).where(
                    GlobalModelRole.profile_id.in_(
                        select(ModelProfile.id).where(ModelProfile.connection_id == connection_id)
                    )
                )
            )
        return {"deleted": True}

    @app.post("/api/v1/settings/connections/{connection_id}/test")
    @app.post("/api/v1/projects/{project_id}/connections/{connection_id}/test")
    async def test_model_connection(
        connection_id: str, project_id: str | None = None
    ) -> dict[str, Any]:
        # A connection stores endpoint credentials; an active model profile
        # supplies the model ID for the fixed no-document JSON probe.
        with Session(engine()) as session:
            require_project(session, project_id)
            profile = session.scalar(
                select(ModelProfile)
                .where(
                    ModelProfile.connection_id == connection_id,
                    ModelProfile.active.is_(True),
                    *([ModelProfile.project_id == project_id] if project_id else []),
                )
                .order_by(ModelProfile.updated_at.desc())
            )
            if profile is None:
                raise KnowledgeError("MODEL_NOT_CONFIGURED", "请先在该连接下创建模型配置")
            connection = _connection_for_profile(session, profile)
            snapshot: dict[str, Any] = {
                "provider": connection.provider if connection else profile.provider,
                "base_url": connection.base_url if connection else profile.base_url,
                "model": profile.model,
                "parameters": profile.parameters,
                "credential_ref": (
                    connection.credential_ref if connection else profile.credential_ref
                ),
            }
        try:
            provider = from_snapshot(
                {
                    **snapshot,
                    "parameters": new_task_parameters(
                        snapshot["base_url"],
                        snapshot["model"],
                        snapshot["parameters"],
                        "extraction",
                    ),
                },
                data_dir,
                True,
            )
            raw = await provider.complete(
                'Return exactly the JSON object {"ok":true}.',
                {"purpose": "connection_test_no_paper_data"},
                {
                    "title": "ConnectionTest",
                    "type": "object",
                    "properties": {"ok": {"const": True}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
            )
            return {
                "connected": True,
                "valid_json": json.loads(raw) == {"ok": True},
                "model": provider.model,
                "mock": False,
                "capabilities": provider.capabilities.model_dump()
                if isinstance(provider, ConfiguredProvider)
                else None,
            }
        except KnowledgeError:
            raise
        except Exception:
            raise KnowledgeError(
                "MODEL_CONNECTION_FAILED",
                "模型连接或 JSON 测试失败，请检查端点、密钥、模型、参数和额度",
            ) from None

    @app.post("/api/v1/settings/models", response_model=ProfileView)
    @app.post("/api/v1/projects/{project_id}/models", response_model=ProfileView)
    def create(body: ProfileInput, project_id: str | None = None) -> ProfileView:
        try:
            with Session(engine()) as session, session.begin():
                return save_profile(session, secrets, project_id, body)
        except CredentialError as error:
            raise KnowledgeError("CREDENTIAL_FAILURE", str(error)) from None

    @app.post("/api/v1/settings/models/{profile_id}/update", response_model=ProfileView)
    @app.post(
        "/api/v1/projects/{project_id}/models/{profile_id}/update", response_model=ProfileView
    )
    def update(profile_id: str, body: ProfileInput, project_id: str | None = None) -> ProfileView:
        try:
            with Session(engine()) as session, session.begin():
                return save_profile(session, secrets, project_id, body, profile_id)
        except CredentialError as error:
            raise KnowledgeError("CREDENTIAL_FAILURE", str(error)) from None

    @app.post("/api/v1/settings/models/{profile_id}/delete")
    @app.post("/api/v1/projects/{project_id}/models/{profile_id}/delete")
    def remove(profile_id: str, project_id: str | None = None) -> dict[str, bool]:
        with Session(engine()) as session, session.begin():
            profile = require_profile(session, profile_id, project_id)
            connection = (
                session.get(ModelConnection, profile.connection_id)
                if profile.connection_id
                else None
            )
            # Profile references are an opaque audit trail that can include
            # credentials from a previous connection after an edit.  Delete
            # only references no other active profile still uses; do not sweep
            # every inactive connection, because queued snapshots may still
            # rely on one of those references.
            protected: set[str] = set()
            for other in session.scalars(
                select(ModelProfile).where(
                    ModelProfile.active.is_(True), ModelProfile.id != profile_id
                )
            ):
                protected.update(other.secret_refs or [])
                if other.connection_id:
                    other_connection = session.get(ModelConnection, other.connection_id)
                    if other_connection is not None:
                        protected.update(other_connection.secret_refs or [])
            candidate_refs = set(profile.secret_refs or [])
            if connection is not None:
                candidate_refs.update(connection.secret_refs or [])
            for reference in candidate_refs:
                if reference in protected:
                    continue
                try:
                    secrets.delete(reference)
                except CredentialError as error:
                    raise KnowledgeError("CREDENTIAL_FAILURE", str(error)) from None
            profile.active, profile.credential_ref, profile.secret_refs = False, None, []
            session.execute(delete(GlobalModelRole).where(GlobalModelRole.profile_id == profile_id))
            if connection is not None:
                remaining = session.scalar(
                    select(ModelProfile.id)
                    .where(
                        ModelProfile.connection_id == connection.id,
                        ModelProfile.active.is_(True),
                        ModelProfile.id != profile_id,
                    )
                    .limit(1)
                )
                if remaining is None:
                    connection.active, connection.credential_ref, connection.secret_refs = (
                        False,
                        None,
                        [],
                    )
        return {"deleted": True}

    @app.post("/api/v1/settings/model-roles", response_model=SettingsView)
    @app.post("/api/v1/projects/{project_id}/model-roles", response_model=SettingsView)
    def select_models(body: RolesInput, project_id: str | None = None) -> SettingsView:
        with Session(engine()) as session, session.begin():
            require_project(session, project_id)
            for role, profile_id in body.model_dump().items():
                if profile_id:
                    require_profile(session, profile_id, project_id)
                existing = session.get(GlobalModelRole, role)
                if existing:
                    if profile_id:
                        existing.profile_id = profile_id
                    else:
                        session.delete(existing)
                elif profile_id:
                    session.add(GlobalModelRole(role=role, profile_id=profile_id))
            session.flush()
            return settings_view(session, project_id)

    @app.post("/api/v1/settings/models/{profile_id}/test")
    @app.post("/api/v1/projects/{project_id}/models/{profile_id}/test")
    async def test_connection(profile_id: str, project_id: str | None = None) -> dict[str, Any]:
        with Session(engine()) as session:
            p = require_profile(session, profile_id, project_id)
            connection = _connection_for_profile(session, p)
            snapshot: dict[str, Any] = {
                "provider": connection.provider if connection else p.provider,
                "base_url": connection.base_url if connection else p.base_url,
                "model": p.model,
                "parameters": p.parameters,
                "credential_ref": connection.credential_ref if connection else p.credential_ref,
            }
        try:
            provider = from_snapshot(
                {
                    **snapshot,
                    "parameters": new_task_parameters(
                        snapshot["base_url"],
                        snapshot["model"],
                        snapshot["parameters"],
                        "extraction",
                    ),
                },
                data_dir,
                True,
            )
            raw = await provider.complete(
                'Return exactly the JSON object {"ok":true}.',
                {"purpose": "connection_test_no_paper_data"},
                {
                    "title": "ConnectionTest",
                    "type": "object",
                    "properties": {"ok": {"const": True}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
            )
            valid = json.loads(raw) == {"ok": True}
            if isinstance(provider, ConfiguredProvider):
                with Session(engine()) as session, session.begin():
                    profile = require_profile(session, profile_id, project_id)
                    if all(getattr(profile, k) == v for k, v in snapshot.items()):
                        profile.parameters = {
                            **profile.parameters,
                            "capabilities": provider.capabilities.model_dump(),
                        }
            return {
                "connected": True,
                "valid_json": valid,
                "model": provider.model,
                "mock": snapshot["provider"] == "mock",
                "capabilities": (
                    provider.capabilities.model_dump()
                    if isinstance(provider, ConfiguredProvider)
                    else None
                ),
            }
        except Exception:
            raise KnowledgeError(
                "MODEL_CONNECTION_FAILED",
                "模型连接或 JSON 测试失败，请检查端点、密钥、模型、参数和额度",
            ) from None
