"""Global model settings with compatibility routes. Responses never expose credentials."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError
from researchgraph.credentials import CredentialError, SecretStore
from researchgraph.model_adapters import new_task_parameters
from researchgraph.model_settings import (
    GlobalModelRole,
    ProfileInput,
    ProfileView,
    RolesInput,
    SettingsView,
    from_snapshot,
    require_profile,
    require_project,
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
            for reference in profile.secret_refs:
                try:
                    secrets.delete(reference)
                except CredentialError as error:
                    raise KnowledgeError("CREDENTIAL_FAILURE", str(error)) from None
            profile.active, profile.credential_ref, profile.secret_refs = False, None, []
            session.execute(delete(GlobalModelRole).where(GlobalModelRole.profile_id == profile_id))
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
            snapshot = {
                key: getattr(p, key)
                for key in ("provider", "base_url", "model", "parameters", "credential_ref")
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
