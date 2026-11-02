"""Workspace model profiles; only credential references are persisted in SQLite."""

from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import Field, SecretStr, model_validator
from sqlalchemy import JSON, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from researchgraph.credentials import SecretStore
from researchgraph.knowledge_contracts import StrictModel
from researchgraph.knowledge_store import KnowledgeError
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.models import Base, Project, now
from researchgraph.providers import ConfiguredProvider, MockProvider, Provider


class ModelParameters(StrictModel):
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    # Read old profiles/snapshots without enforcing their former manual output cap.
    max_output_tokens: int | None = Field(default=None, ge=128, le=2_000_000, deprecated=True)
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    timeout_seconds: int = Field(default=90, ge=5, le=180)
    json_mode: bool = True


class ProfileInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    provider: Literal["openai", "compatible", "local", "mock"]
    base_url: str = Field(default="", max_length=1000)
    model: str = Field(min_length=1, max_length=150)
    parameters: ModelParameters = Field(default_factory=ModelParameters)
    api_key: SecretStr | None = Field(default=None, max_length=2400)
    clear_key: bool = False

    @model_validator(mode="after")
    def validate_endpoint(self) -> "ProfileInput":
        self.base_url = self.base_url.strip().rstrip("/")
        if self.provider == "mock":
            if self.api_key or self.base_url:
                raise ValueError("Mock 不接受 URL 或密钥")
            return self
        parsed = urlsplit(self.base_url)
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
        if self.provider == "openai" and self.base_url != "https://api.openai.com/v1":
            raise ValueError("OpenAI 使用官方 https://api.openai.com/v1；其他端点请选择兼容 API")
        if self.provider == "local" and not loopback:
            raise ValueError("本地模型仅允许 loopback 地址")
        return self


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(24))
    base_url: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    credential_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)
    secret_refs: Mapped[list[str]] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[str] = mapped_column(String(40))


class ModelRole(Base):
    __tablename__ = "project_model_roles"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(24), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("model_profiles.id"))


class GlobalModelRole(Base):
    __tablename__ = "global_model_roles"
    role: Mapped[str] = mapped_column(String(24), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("model_profiles.id"))


class ProfileView(StrictModel):
    id: str
    project_id: str | None
    name: str
    provider: str
    base_url: str
    model: str
    parameters: ModelParameters
    has_api_key: bool
    updated_at: str


class RolesInput(StrictModel):
    extraction: str | None = None
    reasoning: str | None = None


class SettingsView(StrictModel):
    profiles: list[ProfileView]
    roles: RolesInput
    credential_backend: str = "Windows Credential Manager"


def profile_view(profile: ModelProfile) -> ProfileView:
    return ProfileView(
        **{
            key: getattr(profile, key)
            for key in (
                "id",
                "project_id",
                "name",
                "provider",
                "base_url",
                "model",
                "parameters",
                "updated_at",
            )
        },
        has_api_key=bool(profile.credential_ref),
    )


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
    if profile_id:
        profile = require_profile(session, profile_id, project_id)
    else:
        profile = ModelProfile(id=str(uuid4()), project_id=project_id, secret_refs=[], active=True)
        session.add(profile)
    # Immutable secret references preserve the endpoint/configuration of queued jobs.
    if profile.base_url != body.base_url or profile.provider != body.provider or body.clear_key:
        profile.credential_ref = None
    if body.api_key is not None and body.api_key.get_secret_value().strip():
        reference = str(uuid4())
        secrets.put(reference, body.api_key.get_secret_value().strip())
        profile.credential_ref = reference
        profile.secret_refs = [*profile.secret_refs, reference]
    if body.provider in {"openai", "compatible"} and not profile.credential_ref:
        # Compatible gateways may intentionally need no key; OpenAI may not.
        if body.provider == "openai":
            raise KnowledgeError("KEY_REQUIRED", "OpenAI 需要 API Key")
    for key in ("name", "provider", "base_url", "model"):
        setattr(profile, key, getattr(body, key))
    parameters = body.parameters.model_dump()
    parameters["max_output_tokens"] = None
    parameters["capabilities"] = ModelCapabilities().model_dump()
    profile.parameters, profile.updated_at = parameters, now()
    session.flush()
    return profile_view(profile)


def snapshot_for(session: Session, project_id: str, role: str) -> dict[str, Any]:
    require_project(session, project_id)
    selection = session.get(GlobalModelRole, role)
    if selection is None:
        raise KnowledgeError("MODEL_NOT_CONFIGURED", f"请先在设置与诊断选择全局 {role} 模型")
    p = require_profile(session, selection.profile_id, project_id)
    if p.provider == "mock":
        raise KnowledgeError(
            "MODEL_NOT_CONFIGURED", "请选择真实 API 或本地模型；历史测试配置不能用于新任务"
        )
    return {
        key: getattr(p, key)
        for key in (
            "id",
            "project_id",
            "provider",
            "base_url",
            "model",
            "parameters",
            "credential_ref",
        )
    }


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
    return SettingsView(
        profiles=[
            profile_view(p)
            for p in session.scalars(
                select(ModelProfile)
                .where(ModelProfile.active.is_(True))
                .order_by(ModelProfile.name, ModelProfile.id)
            )
        ],
        roles=RolesInput(
            **{r.role: r.profile_id for r in session.scalars(select(GlobalModelRole))}
        ),
    )
