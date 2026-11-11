"""Explicit, full-document PDF translation contracts."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from researchgraph.core import KnowledgeError, StrictModel

TASK_KIND = "pdf_translation"
TranslationOutputMode = Literal["dual", "mono", "both"]
ENGINE_VERSION = "zotero-pdf2zh/4.1.8;pdf2zh_next/openai;bridge-1"
ESTIMATE_NOTE = (
    "按当前 PDF 文本 UTF-8 字节保守估算，外部引擎的提示和分段会影响实际用量；"
    "这不是收费上限。请求次数和累计输入字节估算上限由本机代理独立执行，"
    "真实 Token 以模型返回值统计；每次输出另有 8192 Token 上限或模型已知的更低上限。"
)
EXTERNAL_WARNING = (
    "翻译服务必须是当前软件专用的本机实例。取消或退出会阻断后续模型请求，"
    "但该服务没有停止子进程接口，外部进程状态可能仍未知。"
)


class TranslationSettings(StrictModel):
    enabled: bool = True
    service_url: str = Field(default="http://127.0.0.1:8890", max_length=200)
    launch_mode: Literal["bundled", "managed", "manual"] = "bundled"
    python_path: str | None = Field(default=None, max_length=1000)
    server_path: str | None = Field(default=None, max_length=1000)

    @field_validator("service_url")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("翻译服务只允许无凭据、无路径的本机 HTTP 地址")
        try:
            port = parsed.port
        except ValueError:
            raise ValueError("翻译服务端口无效") from None
        if port is None or not 1 <= port <= 65535:
            raise ValueError("请提供翻译服务端口")
        host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
        return f"http://{host}:{port}"


class TranslationHealth(StrictModel):
    available: bool
    status: str
    version: str | None = None
    active_tasks: int = 0
    message: str


class TranslationRequest(StrictModel):
    document_version_id: str = Field(min_length=1, max_length=36)
    profile_id: str = Field(min_length=1, max_length=36)
    # Legacy clients omitted this field and requested both outputs. New clients
    # explicitly send dual as their UI default.
    output_mode: TranslationOutputMode = "both"
    page_start: int | None = Field(default=None, ge=1, le=300)
    page_end: int | None = Field(default=None, ge=1, le=300)
    max_calls: int = Field(default=100, ge=1, le=2000)
    max_input_tokens: int = Field(default=200_000, ge=1000, le=5_000_000)


class TranslationCreate(TranslationRequest):
    expected_fingerprint: str = Field(pattern="^[a-f0-9]{64}$")
    allow_network: bool = False
    exclusive_service: bool = False


class TranslationPrepare(StrictModel):
    launch_mode: Literal["bundled", "managed", "manual"] = "manual"
    output_mode: TranslationOutputMode = "both"
    prepare_fingerprint: str
    paper_id: str
    document_version_id: str
    source_hash: str
    page_start: int
    page_end: int
    page_count: int
    source_characters: int
    estimated_input_tokens: int
    estimate_is_limit: Literal[False] = False
    estimate_note: str = ESTIMATE_NOTE
    profile_id: str
    model_id: str
    cache_hit: bool
    cached_translation_id: str | None = None
    service_ready: bool
    active_tasks: int
    warnings: list[str]


class TranslationArtifact(StrictModel):
    kind: Literal["mono", "dual"]
    sha256: str
    size_bytes: int
    page_count: int


class TranslationArtifactPath(TranslationArtifact):
    translation_id: str
    path: str


class TranslationUsage(StrictModel):
    calls: int = 0
    retry_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    unknown_usage_calls: int = 0
    cost_estimate: float | None = 0
    cost_known: bool = True


class TranslationView(StrictModel):
    launch_mode: Literal["bundled", "managed", "manual"] = "manual"
    output_mode: TranslationOutputMode = "both"
    id: str
    paper_id: str
    document_version_id: str
    source_hash: str
    profile_id: str
    model_id: str
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"]
    page_start: int
    page_end: int
    page_count: int
    progress: float
    stage: str
    job_id: str
    external_task_id: str | None
    external_state: Literal["not_started", "active", "completed", "failed", "unknown"]
    cache_hit: bool
    error_code: str | None
    error: str | None
    warnings: list[str]
    artifacts: list[TranslationArtifact]
    usage: TranslationUsage
    max_calls: int
    max_input_tokens: int
    created_at: str
    updated_at: str


def output_kinds(output_mode: str) -> tuple[Literal["mono", "dual"], ...]:
    if output_mode == "both":
        return ("mono", "dual")
    if output_mode == "mono":
        return ("mono",)
    if output_mode == "dual":
        return ("dual",)
    raise KnowledgeError("TRANSLATION_OUTPUT_MODE_INVALID", "翻译输出模式无效")
