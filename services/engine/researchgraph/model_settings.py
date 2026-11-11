"""Workspace model profiles; only credential references are persisted in SQLite."""

from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import Field, SecretStr, model_validator
from sqlalchemy import JSON, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from researchgraph.core import KnowledgeError, StrictModel
from researchgraph.credentials import SecretStore
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.models import Base, Project, now
from researchgraph.providers import ConfiguredProvider, MockProvider, Provider
from researchgraph.structured_output import OutputPolicy, freeze_output_policy


class ModelParameters(StrictModel):
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    # Read old profiles/snapshots without enforcing their former manual output cap.
    max_output_tokens: int | None = Field(default=None, ge=128, le=2_000_000, deprecated=True)
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = (
        None
    )
    adapter_policy: Literal["tencent-deepseek-v41-structured-v1"] | None = None
    timeout_seconds: int = Field(default=90, ge=5, le=180)
    json_mode: bool = True
    output_policy: OutputPolicy | None = None


class ConnectionInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    provider: Literal["openai", "compatible", "local"]
    base_url: str = Field(default="", max_length=1000)
    api_key: SecretStr | None = Field(default=None, max_length=2400)
    clear_key: bool = False

    @model_validator(mode="after")
    def validate_endpoint(self) -> "ConnectionInput":
        self.base_url = _validated_base_url(self.provider, self.base_url)
        return self


class ProfileInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    connection_id: str | None = Field(default=None, min_length=1, max_length=36)
    # Kept for one release as an additive compatibility path. New clients use
    # connection_id and save endpoint credentials through ConnectionInput.
    provider: Literal["openai", "compatible", "local"] | None = None
    base_url: str | None = Field(default=None, max_length=1000)
    model: str = Field(min_length=1, max_length=150)
    parameters: ModelParameters = Field(default_factory=ModelParameters)
    api_key: SecretStr | None = Field(default=None, max_length=2400)
    clear_key: bool = False

    @model_validator(mode="after")
    def validate_endpoint(self) -> "ProfileInput":
        if self.connection_id is None:
            if self.provider is None or self.base_url is None:
                raise ValueError("新模型配置必须选择连接")
            self.base_url = _validated_base_url(self.provider, self.base_url)
        elif self.base_url is not None:
            # Reject accidental endpoint drift when a connection is selected.
            self.base_url = self.base_url.strip().rstrip("/")
        return self


def _validated_base_url(provider: str, base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    parsed = urlsplit(value)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and loopback))
    ):
        raise ValueError("远端 URL 必须为 HTTPS，且不能包含凭据、查询或片段")
    if provider == "openai" and value != "https://api.openai.com/v1":
        raise ValueError("OpenAI 使用官方 https://api.openai.com/v1；其他端点请选择兼容 API")
    if provider == "local" and not loopback:
        raise ValueError("本地模型仅允许 loopback 地址")
    return value


class ModelConnection(Base):
    __tablename__ = "model_connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(24))
    base_url: Mapped[str] = mapped_column(Text)
    credential_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)
    secret_refs: Mapped[list[str]] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[str] = mapped_column(String(40))


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_connections.id"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(24))
    base_url: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    credential_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)
    secret_refs: Mapped[list[str]] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[str] = mapped_column(String(40))


class GlobalModelRole(Base):
    __tablename__ = "global_model_roles"
    role: Mapped[str] = mapped_column(String(24), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("model_profiles.id"))


class ProfileView(StrictModel):
    id: str
    project_id: str | None
    name: str
    connection_id: str | None
    connection_name: str | None
    provider: str
    base_url: str
    model: str
    parameters: ModelParameters
    has_api_key: bool
    updated_at: str


class ConnectionView(StrictModel):
    id: str
    project_id: str | None
    name: str
    provider: str
    base_url: str
    has_api_key: bool
    updated_at: str


class RolesInput(StrictModel):
    extraction: str | None = None
    reasoning: str | None = None


class SettingsView(StrictModel):
    connections: list[ConnectionView]
    profiles: list[ProfileView]
    roles: RolesInput
    credential_backend: str = "Windows Credential Manager"


def connection_view(connection: ModelConnection) -> ConnectionView:
    return ConnectionView(
        id=connection.id,
        project_id=connection.project_id,
        name=connection.name,
        provider=connection.provider,
        base_url=connection.base_url,
        has_api_key=bool(connection.credential_ref),
        updated_at=connection.updated_at,
    )


def _connection_for_profile(session: Session, profile: ModelProfile) -> ModelConnection | None:
    if profile.connection_id:
        return session.get(ModelConnection, profile.connection_id)
    return None


def profile_view(profile: ModelProfile, connection: ModelConnection | None = None) -> ProfileView:
    from researchgraph.model_adapters import with_documented_limits

    view = ProfileView(
        **{
            key: getattr(profile, key)
            for key in (
                "id",
                "project_id",
                "name",
                "model",
                "parameters",
                "updated_at",
            )
        },
        connection_id=connection.id if connection else profile.connection_id,
        connection_name=connection.name if connection else None,
        provider=connection.provider if connection else profile.provider,
        base_url=connection.base_url if connection else profile.base_url,
        has_api_key=bool(connection.credential_ref if connection else profile.credential_ref),
    )
    view.parameters.capabilities = with_documented_limits(
        connection.base_url if connection else profile.base_url,
        profile.model,
        view.parameters.capabilities,
    )
    return view


def require_project(session: Session, project_id: str | None) -> None:
    if project_id is not None and session.get(Project, project_id) is None:
        raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")


def require_profile(
    session: Session, profile_id: str, project_id: str | None = None
) -> ModelProfile:
    require_project(session, project_id)
    profile = session.get(ModelProfile, profile_id)
    if profile is None or not profile.active:
        raise KnowledgeError("MODEL_NOT_FOUND", "全局模型配置不存在或已删除")
    return profile


def save_profile(
    session: Session,
    secrets: SecretStore,
    project_id: str | None,
    body: ProfileInput,
    profile_id: str | None = None,
) -> ProfileView:
    require_project(session, project_id)
    previous_connection: ModelConnection | None = None
    if profile_id:
        profile = require_profile(session, profile_id, project_id)
        previous_connection = _connection_for_profile(session, profile)
    else:
        profile = ModelProfile(
            id=str(uuid4()),
            project_id=project_id,
            name=body.name,
            provider=body.provider or "compatible",
            base_url=body.base_url or "",
            model=body.model,
            parameters=body.parameters.model_dump(),
            credential_ref=None,
            secret_refs=[],
            active=True,
            updated_at=now(),
        )
        session.add(profile)
    connection: ModelConnection | None
    if body.connection_id:
        connection = session.get(ModelConnection, body.connection_id)
        if connection is None or not connection.active:
            raise KnowledgeError("CONNECTION_NOT_FOUND", "模型连接不存在或已删除")
        if body.api_key is not None or body.clear_key:
            _update_connection_secret(session, secrets, connection, body.api_key, body.clear_key)
    else:
        assert body.provider is not None and body.base_url is not None
        # Compatibility requests become a reusable connection instead of
        # copying Base URL/API Key into every new profile.
        connection = session.scalar(
            select(ModelConnection).where(
                ModelConnection.project_id.is_(None),
                ModelConnection.active.is_(True),
                ModelConnection.provider == body.provider,
                ModelConnection.base_url == body.base_url,
            )
        )
        if connection is None:
            connection = ModelConnection(
                id=str(uuid4()),
                project_id=None,
                name=f"{body.name} 连接",
                provider=body.provider,
                base_url=body.base_url,
                credential_ref=None,
                secret_refs=[],
                active=True,
                updated_at=now(),
            )
            session.add(connection)
        if body.api_key is not None or body.clear_key:
            _update_connection_secret(session, secrets, connection, body.api_key, body.clear_key)
    if connection.provider in {"openai", "compatible"} and not connection.credential_ref:
        if connection.provider == "openai":
            raise KnowledgeError("KEY_REQUIRED", "OpenAI 需要 API Key")
    profile.connection_id = connection.id
    profile.provider = connection.provider
    profile.base_url = connection.base_url
    profile.credential_ref = connection.credential_ref
    # Keep a profile-local audit trail of the references it has used.  This is
    # still only opaque references; it lets the legacy profile-delete route
    # clean up credentials created through that compatibility route without
    # placing key material in SQLite.
    profile.secret_refs = list(dict.fromkeys([*profile.secret_refs, *connection.secret_refs]))
    profile.name, profile.model = body.name, body.model
    parameters = body.parameters.model_dump()
    parameters["max_output_tokens"] = None
    parameters["capabilities"] = ModelCapabilities().model_dump()
    # A profile cannot claim strict support; only new task creation freezes it.
    parameters["output_policy"] = None
    profile.parameters, profile.updated_at = parameters, now()
    session.flush()
    if previous_connection is not None and previous_connection.id != connection.id:
        remaining = session.scalar(
            select(ModelProfile.id)
            .where(
                ModelProfile.connection_id == previous_connection.id,
                ModelProfile.active.is_(True),
                ModelProfile.id != profile.id,
            )
            .limit(1)
        )
        if remaining is None:
            previous_connection.active = False
    return profile_view(profile, connection)


def save_connection(
    session: Session,
    secrets: SecretStore,
    project_id: str | None,
    body: ConnectionInput,
    connection_id: str | None = None,
) -> ConnectionView:
    require_project(session, project_id)
    if connection_id:
        connection = session.get(ModelConnection, connection_id)
        if connection is None or not connection.active:
            raise KnowledgeError("CONNECTION_NOT_FOUND", "模型连接不存在或已删除")
        if connection.provider != body.provider or connection.base_url != body.base_url:
            connection.credential_ref = None
        connection.name = body.name
        connection.provider, connection.base_url = body.provider, body.base_url
    else:
        connection = ModelConnection(
            id=str(uuid4()),
            project_id=project_id,
            name=body.name,
            provider=body.provider,
            base_url=body.base_url,
            credential_ref=None,
            secret_refs=[],
            active=True,
            updated_at=now(),
        )
        session.add(connection)
    _update_connection_secret(session, secrets, connection, body.api_key, body.clear_key)
    if connection.provider in {"openai", "compatible"} and not connection.credential_ref:
        if connection.provider == "openai":
            raise KnowledgeError("KEY_REQUIRED", "OpenAI 需要 API Key")
    connection.updated_at = now()
    session.flush()
    return connection_view(connection)


def _update_connection_secret(
    session: Session,
    secrets: SecretStore,
    connection: ModelConnection,
    api_key: SecretStr | None,
    clear_key: bool,
) -> None:
    if clear_key:
        connection.credential_ref = None
    if api_key is not None and api_key.get_secret_value().strip():
        reference = str(uuid4())
        secrets.put(reference, api_key.get_secret_value().strip())
        connection.credential_ref = reference
        connection.secret_refs = [*connection.secret_refs, reference]
    connection.updated_at = now()


def snapshot_for(session: Session, project_id: str, role: str) -> dict[str, Any]:
    require_project(session, project_id)
    selection = session.get(GlobalModelRole, role)
    if selection is None:
        raise KnowledgeError("MODEL_NOT_CONFIGURED", f"请先在设置与诊断选择全局 {role} 模型")
    p = require_profile(session, selection.profile_id, project_id)
    connection = _connection_for_profile(session, p)
    provider = connection.provider if connection else p.provider
    base_url = connection.base_url if connection else p.base_url
    credential_ref = connection.credential_ref if connection else p.credential_ref
    if provider == "mock":
        raise KnowledgeError(
            "MODEL_NOT_CONFIGURED", "请选择真实 API 或本地模型；历史测试配置不能用于新任务"
        )
    snapshot = {
        key: getattr(p, key)
        for key in (
            "id",
            "project_id",
            "model",
            "parameters",
        )
    }
    snapshot.update(
        {
            "provider": provider,
            "base_url": base_url,
            "credential_ref": credential_ref,
        }
    )
    from researchgraph.model_adapters import new_task_parameters

    snapshot["parameters"] = new_task_parameters(base_url, p.model, p.parameters, role)
    snapshot["parameters"] = {
        **snapshot["parameters"],
        "output_policy": freeze_output_policy(provider, base_url, p.model, snapshot["parameters"]),
    }
    return snapshot


def from_snapshot(snapshot: dict[str, Any], data_dir: Path, allow_network: bool) -> Provider:
    if snapshot["provider"] == "mock":
        return MockProvider()
    if not allow_network:
        raise KnowledgeError("NETWORK_CONSENT_REQUIRED", "请明确同意发送所选论文/主张及证据文本")
    key = (
        SecretStore(data_dir).get(snapshot["credential_ref"])
        if snapshot.get("credential_ref")
        else ""
    )
    return ConfiguredProvider(
        base_url=snapshot["base_url"],
        model=snapshot["model"],
        key=key,
        parameters=snapshot["parameters"],
        provider_name=snapshot["provider"],
    )


def settings_view(session: Session, project_id: str | None = None) -> SettingsView:
    require_project(session, project_id)
    connections = [
        connection_view(c)
        for c in session.scalars(
            select(ModelConnection)
            .where(ModelConnection.active.is_(True))
            .order_by(ModelConnection.name, ModelConnection.id)
        )
    ]
    profiles = []
    for p in session.scalars(
        select(ModelProfile)
        .where(ModelProfile.active.is_(True))
        .order_by(ModelProfile.name, ModelProfile.id)
    ):
        profiles.append(profile_view(p, _connection_for_profile(session, p)))
    return SettingsView(
        connections=connections,
        profiles=profiles,
        roles=RolesInput(
            **{r.role: r.profile_id for r in session.scalars(select(GlobalModelRole))}
        ),
    )
