"""Opt-in PDF translation jobs and immutable, source-bound derived artifacts."""

import asyncio
import hashlib
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Query
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError, digest
from researchgraph.lite_models import LiteTokenUsage
from researchgraph.lite_usage import record_usage
from researchgraph.model_settings import _connection_for_profile, require_profile
from researchgraph.models import (
    AttachmentRevision,
    Chunk,
    Idempotency,
    Job,
    Paper,
    PaperSource,
    now,
)
from researchgraph.storage import read_session
from researchgraph.translation_bridge import (
    MAX_OUTPUT_BYTES,
    TranslationBridge,
    output_names,
    progress_value,
)
from researchgraph.translation_contracts import (
    ENGINE_VERSION,
    EXTERNAL_WARNING,
    TASK_KIND,
    TranslationArtifactPath,
    TranslationCreate,
    TranslationHealth,
    TranslationPrepare,
    TranslationRequest,
    TranslationSettings,
    TranslationUsage,
    TranslationView,
    output_kinds,
)
from researchgraph.translation_models import PDFTranslation, PDFTranslationSettings
from researchgraph.workspaces import plain

POLL_SECONDS = 0.5
MAX_TRANSLATION_SECONDS = 3 * 60 * 60
MAX_SOURCE_BYTES = 50 * 1024 * 1024
TRANSLATION_REQUEST_POLICY = "text-chat-minimal-1"

_PROXY_ERROR_MESSAGES = {
    "TRANSLATION_BUDGET_EXCEEDED": (
        "已达到本次翻译预设的模型请求或输入预算，后续请求已阻断。请提高预算或缩小范围后重新预检。"
    ),
    "TRANSLATION_TEXT_ONLY": (
        "翻译引擎发送了不兼容的请求格式，后续请求已阻断。请更新内置翻译运行时或检查翻译模型配置。"
    ),
    "TRANSLATION_PROVIDER_REQUEST_REJECTED": (
        "模型服务拒绝了翻译请求（请求参数或模型接口不兼容），后续请求已阻断。"
        "请检查 Base URL、模型 ID 和兼容配置。"
    ),
    "TRANSLATION_PROVIDER_AUTH_FAILED": (
        "模型服务鉴权失败，后续请求已阻断。请在设置中检查 API Key 和 Base URL。"
    ),
    "TRANSLATION_PROVIDER_RATE_LIMITED": (
        "模型服务返回限流，后续请求已阻断。请稍后重新预检并提交翻译。"
    ),
    "TRANSLATION_PROVIDER_TRUNCATED": (
        "模型响应被截断，译文未发布。请提高模型输出上限或改用支持更长输出的模型。"
    ),
    "TRANSLATION_PROVIDER_RESPONSE_INVALID": (
        "模型服务返回了不兼容的响应格式，译文未发布。请检查模型接口是否兼容 Chat Completions。"
    ),
    "TRANSLATION_PROVIDER_FAILED": (
        "模型服务请求失败，译文未发布。请检查网络、Base URL 和模型服务状态。"
    ),
    "TRANSLATION_SCOPE_CHANGED": "翻译来源或任务状态发生变化，后续请求已阻断。请重新预检并提交。",
    "TRANSLATION_CANCELLED": "翻译已取消，后续请求已阻断。",
}


def _proxy_error_message(code: str) -> str:
    return _PROXY_ERROR_MESSAGES.get(
        code, "模型代理已阻断后续请求，译文未发布。请检查任务详情和模型配置。"
    )


def _error(code: str, message: str, status: int = 409) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def _settings(session: Session) -> TranslationSettings:
    row = session.get(PDFTranslationSettings, "global")
    return (
        TranslationSettings.model_validate(
            {
                "enabled": row.enabled,
                "service_url": row.service_url,
                "launch_mode": row.launch_mode,
                "python_path": row.python_path,
                "server_path": row.server_path,
            }
        )
        if row is not None
        else TranslationSettings()
    )


def _runtime_snapshot(settings: TranslationSettings) -> dict[str, Any]:
    return settings.model_dump(include={"launch_mode", "python_path", "server_path"})


def _service_warning(settings: TranslationSettings) -> str:
    if settings.launch_mode == "bundled":
        return "内置翻译核心按需启停；待翻译文本发至所选模型，原 PDF 不覆盖。"
    if settings.launch_mode == "managed":
        return (
            "翻译时自动后台启动专用服务，完成、失败或取消后关闭本应用启动的进程树；"
            "不会接管或关闭已有服务。外部服务可能在启动时查询上游通知。"
        )
    return EXTERNAL_WARNING


async def _check_service(settings: TranslationSettings, data_dir: Path) -> TranslationHealth:
    if settings.launch_mode == "manual":
        return await TranslationBridge(settings.service_url).check()
    from researchgraph.translation_runtime import ManagedTranslationRuntime

    try:
        # A preflight never starts Python, the renderer, or a model request.
        runtime = ManagedTranslationRuntime(settings, data_dir)
        await asyncio.to_thread(runtime.validate)
        return TranslationHealth(
            available=True,
            status="configured",
            version=runtime.expected_version,
            message=(
                "内置翻译运行文件已就绪；翻译时自动启动"
                if settings.launch_mode == "bundled"
                else "启动路径与端口检查通过；翻译时自动启动，尚未验证运行依赖"
            ),
        )
    except KnowledgeError as exc:
        return TranslationHealth(available=False, status=exc.code, message=str(exc))


def _scope(
    session: Session, paper_id: str, body: TranslationRequest
) -> tuple[Paper, AttachmentRevision, dict[str, Any]]:
    paper = session.get(Paper, paper_id)
    revision = session.get(AttachmentRevision, body.document_version_id)
    if paper is None:
        raise _error("PAPER_NOT_FOUND", "论文不存在", 404)
    if revision is None or revision.paper_id != paper_id:
        raise _error("REVISION_NOT_FOUND", "所选文献版本不属于当前论文", 404)
    if body.page_start not in {None, 1} or body.page_end not in {None, revision.page_count}:
        raise _error("TRANSLATION_RANGE_UNSUPPORTED", "当前外部引擎桥接仅支持全文翻译", 422)
    profile = require_profile(session, body.profile_id, paper.project_id)
    connection = _connection_for_profile(session, profile)
    provider = connection.provider if connection else profile.provider
    if provider not in {"openai", "compatible", "local"}:
        raise _error("MODEL_NOT_CONFIGURED", "请选择已配置的真实兼容 API 或本地模型")
    snapshot = {
        "id": profile.id,
        "provider": provider,
        "base_url": connection.base_url if connection else profile.base_url,
        "model": profile.model,
        "parameters": profile.parameters,
        "credential_ref": connection.credential_ref if connection else profile.credential_ref,
    }
    if _settings(session).launch_mode == "bundled":
        from researchgraph.translation_bundled import BUNDLED_ENGINE_ID

        snapshot["translation_engine"] = BUNDLED_ENGINE_ID
        snapshot["translation_request_policy"] = TRANSLATION_REQUEST_POLICY
    return paper, revision, snapshot


def _identity(
    revision: AttachmentRevision, snapshot: dict[str, Any], output_mode: str = "both"
) -> str:
    return digest(
        {
            "paper_id": revision.paper_id,
            "document_version_id": revision.id,
            "source_hash": revision.sha256,
            "engine": snapshot.get("translation_engine", ENGINE_VERSION),
            "source_language": "en",
            "target_language": "zh-CN",
            "outputs": list(output_kinds(output_mode)),
            "range": [1, revision.page_count],
            "provider": snapshot["provider"],
            "base_url": snapshot["base_url"],
            "model": snapshot["model"],
            "parameters": snapshot["parameters"],
            # Old task/cache identities remain byte-for-byte compatible.
            # New translation parameter semantics have a separate identity.
            **(
                {"translation_request_policy": snapshot["translation_request_policy"]}
                if "translation_request_policy" in snapshot
                else {}
            ),
        }
    )


def _prepare_fingerprint(
    revision: AttachmentRevision,
    snapshot: dict[str, Any],
    body: TranslationRequest,
    settings: TranslationSettings,
    health: TranslationHealth | None,
) -> str:
    return digest(
        {
            "cache_key": _identity(revision, snapshot, body.output_mode),
            "profile_id": body.profile_id,
            "credential_ref": snapshot.get("credential_ref"),
            "service_url": settings.service_url,
            "enabled": settings.enabled,
            "runtime": _runtime_snapshot(settings),
            "verified_version": health.version if health and health.available else None,
            "max_calls": body.max_calls,
            "max_input_tokens": body.max_input_tokens,
            "options": {
                "output_mode": body.output_mode,
                "mono": "mono" in output_kinds(body.output_mode),
                "dual": "dual" in output_kinds(body.output_mode),
                "ignoreCache": True,
            },
        }
    )


def _source_bytes(session: Session, revision: AttachmentRevision) -> bytes:
    sources = session.scalars(
        select(PaperSource).where(
            PaperSource.paper_id == revision.paper_id,
            PaperSource.revision_id == revision.id,
        )
    ).all()
    paths = list(
        dict.fromkeys(
            path for source in sources for path in (source.managed_path, source.path) if path
        )
    )
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            continue
        try:
            with path.open("rb") as stream:
                before = os.fstat(stream.fileno())
                content = stream.read(MAX_SOURCE_BYTES + 1)
                after = os.fstat(stream.fileno())
            current = path.stat()
            signature = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            if any(
                (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns) != signature
                for item in (after, current)
            ):
                continue
            if len(content) > MAX_SOURCE_BYTES:
                continue
            if hashlib.sha256(content).hexdigest() == revision.sha256:
                return content
        except OSError:
            continue
    raise KnowledgeError(
        "TRANSLATION_SOURCE_UNAVAILABLE",
        "找不到与所选修订字节一致的 PDF；请检查文件或重新导入，旧译文仍保留",
    )


def _pdf_pages(content: bytes) -> int:
    import pymupdf

    if not content.startswith(b"%PDF-") or len(content) > MAX_OUTPUT_BYTES:
        raise KnowledgeError("TRANSLATION_OUTPUT_INVALID", "译文不是可验证的 PDF")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass or not 1 <= document.page_count <= 1200:
                raise ValueError("invalid page count or encryption")
            # Force page-tree access; a PDF header alone is insufficient.
            for page in document:
                if page.rect.is_empty or page.rect.is_infinite:
                    raise ValueError("invalid page geometry")
            return int(document.page_count)
    except Exception:
        raise KnowledgeError(
            "TRANSLATION_OUTPUT_INVALID", "译文 PDF 损坏、加密或页结构无效"
        ) from None


def _artifact(row: PDFTranslation, kind: str, data_dir: Path) -> TranslationArtifactPath:
    if kind not in output_kinds(row.output_mode) or row.status != "COMPLETED":
        raise _error("TRANSLATION_ARTIFACT_NOT_FOUND", "该译文产物不可用", 404)
    try:
        UUID(row.id)
    except ValueError:
        raise _error("TRANSLATION_ARTIFACT_INVALID", "译文记录标识无效") from None
    metadata = next((item for item in row.artifacts if item.get("kind") == kind), None)
    if metadata is None:
        raise _error("TRANSLATION_ARTIFACT_NOT_FOUND", "该译文产物不存在", 404)
    root = data_dir.resolve()
    path = root / "translations" / row.id / f"{kind}.pdf"
    try:
        if not all(plain(parent, directory=True) for parent in (path.parent.parent, path.parent)):
            raise ValueError("unsafe parent")
        if not plain(path) or path.resolve() != path:
            raise ValueError("unsafe output")
        with path.open("rb") as stream:
            content = stream.read(MAX_OUTPUT_BYTES + 1)
        if (
            len(content) != metadata["size_bytes"]
            or hashlib.sha256(content).hexdigest() != metadata["sha256"]
            or _pdf_pages(content) != metadata["page_count"]
        ):
            raise ValueError("output changed")
    except (OSError, KeyError, ValueError):
        raise _error(
            "TRANSLATION_ARTIFACT_CHANGED", "译文文件缺失或内容已变化，请重新生成"
        ) from None
    return TranslationArtifactPath(
        translation_id=row.id,
        kind=kind,
        path=str(path),
        sha256=metadata["sha256"],
        size_bytes=metadata["size_bytes"],
        page_count=metadata["page_count"],
    )


def _cached(
    session: Session, key: str, data_dir: Path, *, output_mode: str = "both"
) -> PDFTranslation | None:
    rows = session.scalars(
        select(PDFTranslation)
        .where(
            PDFTranslation.cache_key == key,
            PDFTranslation.status == "COMPLETED",
            PDFTranslation.output_mode == output_mode,
        )
        .order_by(PDFTranslation.created_at.desc())
    )
    for row in rows:
        try:
            expected = output_kinds(row.output_mode)
            if len(row.artifacts) != len(expected) or {
                item.get("kind") for item in row.artifacts
            } != set(expected):
                continue
            for kind in expected:
                _artifact(row, kind, data_dir)
            return row
        except HTTPException:
            continue
    return None


def _usage(session: Session, job_id: str) -> TranslationUsage:
    rows = session.scalars(
        select(LiteTokenUsage).where(
            LiteTokenUsage.task_run_id == job_id,
            LiteTokenUsage.task_kind == TASK_KIND,
            LiteTokenUsage.cache_hit.is_(False),
        )
    ).all()
    known = all(row.cost_estimate is not None for row in rows)
    return TranslationUsage(
        calls=len(rows),
        retry_count=sum(row.retry_count for row in rows),
        input_tokens=sum(row.input_tokens or 0 for row in rows),
        output_tokens=sum(row.output_tokens or 0 for row in rows),
        total_tokens=sum(row.total_tokens or 0 for row in rows),
        unknown_usage_calls=sum(row.usage_source == "unknown" for row in rows),
        cost_estimate=sum(row.cost_estimate or 0 for row in rows) if known else None,
        cost_known=known,
    )


def _verify_successful_calls(session: Session, job_id: str) -> None:
    rows = session.scalars(
        select(LiteTokenUsage).where(
            LiteTokenUsage.task_run_id == job_id,
            LiteTokenUsage.task_kind == TASK_KIND,
            LiteTokenUsage.cache_hit.is_(False),
        )
    ).all()
    if not rows or any(row.status != "succeeded" for row in rows):
        raise KnowledgeError(
            "TRANSLATION_MODEL_USAGE_INCOMPLETE",
            "没有完整成功的模型请求记录，不能把外部原文回退 PDF 标为翻译完成",
        )


def _view(session: Session, row: PDFTranslation, *, cache_hit: bool = False) -> TranslationView:
    values = {
        key: getattr(row, key)
        for key in TranslationView.model_fields
        if key not in {"cache_hit", "usage", "artifacts", "launch_mode"}
    }
    return TranslationView.model_validate(
        {
            **values,
            "launch_mode": (row.runtime_snapshot or {}).get("launch_mode", "manual"),
            "cache_hit": cache_hit,
            "usage": TranslationUsage() if cache_hit else _usage(session, row.job_id),
            "artifacts": [
                {key: item[key] for key in ("kind", "sha256", "size_bytes", "page_count")}
                for item in row.artifacts
            ],
        }
    )


def cancel_translation_job(session: Session, job: Job) -> None:
    row = session.scalar(select(PDFTranslation).where(PDFTranslation.job_id == job.id))
    if row is not None and row.status in {"PENDING", "RUNNING"}:
        row.status, row.stage = "CANCELLED", "cancelled"
        row.error_code, row.error = (
            "CANCELLED",
            "翻译已取消；后续模型请求已阻断，正在回收自动启动的翻译服务"
            if (row.runtime_snapshot or {}).get("launch_mode") in {"managed", "bundled"}
            else "翻译已取消；后续模型请求已阻断，手动服务中的外部进程可能仍在运行",
        )
        row.external_state = "unknown" if row.external_state != "not_started" else "not_started"
        row.updated_at = now()
    if job.status in {"queued", "running"}:
        job.status, job.error, job.updated_at = "cancelled", "翻译已取消", now()


def recover_translations(engine: Engine) -> int:
    count = 0
    with Session(engine) as session, session.begin():
        for row in session.scalars(
            select(PDFTranslation).where(PDFTranslation.status.in_(["PENDING", "RUNNING"]))
        ):
            row.status, row.stage, row.updated_at = "INTERRUPTED", "interrupted", now()
            row.error_code = "INTERRUPTED"
            row.error = "上次翻译中断，未自动重发；请确认外部服务空闲后手动新建任务"
            if row.external_state != "not_started":
                row.external_state = "unknown"
            job = session.get(Job, row.job_id)
            if job is not None and job.status in {"queued", "running"}:
                job.status, job.stage, job.error, job.updated_at = (
                    "interrupted",
                    "interrupted",
                    row.error,
                    now(),
                )
            for usage in session.scalars(
                select(LiteTokenUsage).where(
                    LiteTokenUsage.task_run_id == row.job_id,
                    LiteTokenUsage.status.in_(["started", "running"]),
                )
            ):
                usage.status, usage.reason_code = "interrupted", "INTERRUPTED"
            count += 1
    return count


def _running(engine: Engine, job_id: str) -> bool:
    with read_session(engine) as session:
        job = session.get(Job, job_id)
        return job is not None and job.status == "running"


def _update_progress(engine: Engine, job_id: str, progress: float, stage: str) -> None:
    with Session(engine) as session, session.begin():
        row = session.scalar(select(PDFTranslation).where(PDFTranslation.job_id == job_id))
        job = session.get(Job, job_id)
        if row is not None and row.status == "RUNNING" and job and job.status == "running":
            row.progress, row.stage, row.updated_at = max(row.progress, progress), stage, now()
            job.stage = (
                stage
                if stage in {"starting_service", "stopping_service"}
                else "saving"
                if stage == "downloading"
                else "generating"
            )
            job.updated_at = now()


async def execute_translation(engine: Engine, job_id: str, data_dir: Path) -> None:
    from researchgraph.translation_proxy import TranslationProxy

    proxy: Any = None
    runtime: Any = None
    submitted = False
    try:
        with Session(engine) as session, session.begin():
            row = session.scalar(select(PDFTranslation).where(PDFTranslation.job_id == job_id))
            job = session.get(Job, job_id)
            if (
                row is None
                or job is None
                or row.status != "PENDING"
                or job.status not in {"queued", "running"}
            ):
                return
            revision = session.get(AttachmentRevision, row.document_version_id)
            if revision is None or revision.sha256 != row.source_hash:
                raise KnowledgeError("TRANSLATION_SOURCE_CHANGED", "翻译来源版本已变化")
            content = _source_bytes(session, revision)
            if _pdf_pages(content) != revision.page_count:
                raise KnowledgeError("TRANSLATION_SOURCE_CHANGED", "翻译来源页数不一致")
            output_mode = row.output_mode
            if _identity(revision, row.model_snapshot, output_mode) != row.cache_key:
                raise KnowledgeError("TRANSLATION_CONFIG_CHANGED", "翻译缓存身份与冻结配置不一致")
            snapshot, service_url = row.model_snapshot, row.service_url
            runtime_settings = TranslationSettings(
                enabled=True,
                service_url=service_url,
                **{"launch_mode": "manual", **(row.runtime_snapshot or {})},
            )
            scope = {
                "project_id": row.project_id,
                "paper_id": row.paper_id,
                "document_version_id": row.document_version_id,
            }
            max_calls, max_input_tokens = row.max_calls, row.max_input_tokens
            row.status, row.stage, row.updated_at = "RUNNING", "checking", now()
            job.status, job.stage, job.updated_at = "running", "checking", now()
        if runtime_settings.launch_mode in {"managed", "bundled"}:
            from researchgraph.translation_runtime import ManagedTranslationRuntime

            _update_progress(engine, job_id, 0, "starting_service")
            runtime = ManagedTranslationRuntime(
                runtime_settings, data_dir, cancelled=lambda: not _running(engine, job_id)
            )
            await runtime.__aenter__()
            service_url = runtime.service_url
        bridge = TranslationBridge(
            service_url,
            before_request=runtime.ensure_owned if runtime is not None else None,
            service_token=runtime.service_token if runtime is not None else None,
            expected_version=runtime.expected_version if runtime is not None else "4.1.8",
        )
        health = await bridge.check()
        if not health.available or health.active_tasks:
            raise KnowledgeError(
                "TRANSLATION_SERVICE_BUSY"
                if health.active_tasks
                else "TRANSLATION_SERVICE_UNAVAILABLE",
                health.message,
            )
        if not _running(engine, job_id):
            return
        stem = "rg-" + job_id
        proxy = TranslationProxy(
            engine,
            job_id,
            data_dir,
            snapshot,
            scope,
            max_calls,
            max_input_tokens,
        )
        # The bundled CLI explicitly disables optional sampling/reasoning
        # fields.  Do not re-inject the reading profile's parameters into its
        # Chat Completions request; some compatible endpoints reject them.
        proxy.forward_parameters = (
            snapshot.get("translation_request_policy") != TRANSLATION_REQUEST_POLICY
        )
        async with proxy:
            if not _running(engine, job_id):
                await proxy.cancel()
                return
            # Mark the external state before upload; a timeout cannot prove the
            # server did not accept the request.
            with Session(engine) as session, session.begin():
                current = session.scalar(
                    select(PDFTranslation).where(PDFTranslation.job_id == job_id)
                )
                if current is None or current.status != "RUNNING":
                    return
                current.external_state, current.stage, current.updated_at = (
                    "active",
                    "translating",
                    now(),
                )
            submitted = True
            response = await bridge.submit(
                content,
                stem,
                proxy.base_url,
                proxy.token,
                snapshot["model"],
                output_mode=output_mode,
            )
            if response.get("status") == "accepted":
                task_id = response.get("taskId")
                if not isinstance(task_id, str) or not 1 <= len(task_id) <= 200:
                    raise KnowledgeError(
                        "TRANSLATION_SERVICE_PROTOCOL", "翻译服务没有返回合法任务标识"
                    )
                with Session(engine) as session, session.begin():
                    current = session.scalar(
                        select(PDFTranslation).where(PDFTranslation.job_id == job_id)
                    )
                    if current is not None:
                        current.external_task_id, current.updated_at = task_id, now()
                started, missing = time.monotonic(), 0
                while True:
                    if not _running(engine, job_id):
                        await proxy.cancel()
                        return
                    if proxy.error_code:
                        raise KnowledgeError(
                            proxy.error_code, _proxy_error_message(proxy.error_code)
                        )
                    if time.monotonic() - started > MAX_TRANSLATION_SECONDS:
                        raise KnowledgeError(
                            "TRANSLATION_TIMEOUT", "翻译超过本机等待时限，已阻断后续模型请求"
                        )
                    item = await bridge.poll(task_id)
                    if item is None:
                        missing += 1
                        if missing >= 10:
                            raise KnowledgeError(
                                "TRANSLATION_EXTERNAL_UNKNOWN", "外部任务状态不可确认，未自动重发"
                            )
                    else:
                        missing = 0
                        status = item.get("status")
                        if status in {"failed", "失败"}:
                            raise KnowledgeError(
                                "TRANSLATION_EXTERNAL_FAILED", "外部翻译失败，未自动重发模型请求"
                            )
                        if (
                            status in {"success", "完成"}
                            and item.get("active") is False
                            and item.get("finished") is True
                        ):
                            response = item
                            break
                        _update_progress(
                            engine, job_id, progress_value(item.get("progress")), "translating"
                        )
                    await asyncio.sleep(POLL_SECONDS)
            elif response.get("status") != "success":
                raise KnowledgeError(
                    "TRANSLATION_SERVICE_PROTOCOL", "翻译服务未接受任务，未自动重发"
                )
            names = output_names(response, stem, output_mode=output_mode)
            if proxy.error_code:
                raise KnowledgeError(proxy.error_code, _proxy_error_message(proxy.error_code))
            _update_progress(engine, job_id, 99, "downloading")
            downloaded: dict[str, bytes] = {}
            for kind, filename in names.items():
                if not _running(engine, job_id):
                    await proxy.cancel()
                    return
                downloaded[kind] = await bridge.download(filename)
            if proxy.error_code:
                raise KnowledgeError(proxy.error_code, _proxy_error_message(proxy.error_code))
            with read_session(engine) as session:
                _verify_successful_calls(session, job_id)
            artifacts = _save_outputs(data_dir, job_id, downloaded, output_mode=output_mode)
            if runtime is not None:
                _update_progress(engine, job_id, 99, "stopping_service")
                await runtime.stop()
            with Session(engine) as session, session.begin():
                current = session.scalar(
                    select(PDFTranslation).where(PDFTranslation.job_id == job_id)
                )
                job = session.get(Job, job_id)
                if (
                    current is None
                    or job is None
                    or current.status != "RUNNING"
                    or job.status != "running"
                ):
                    return
                if proxy.error_code:
                    raise KnowledgeError(proxy.error_code, _proxy_error_message(proxy.error_code))
                _verify_successful_calls(session, job_id)
                revision = session.get(AttachmentRevision, current.document_version_id)
                if revision is None or revision.sha256 != current.source_hash:
                    raise KnowledgeError("TRANSLATION_SOURCE_CHANGED", "来源变化，译文未发布")
                if current.output_mode != output_mode or (
                    _identity(revision, current.model_snapshot, current.output_mode)
                    != current.cache_key
                ):
                    raise KnowledgeError(
                        "TRANSLATION_CONFIG_CHANGED", "冻结输出模式或模型配置变化，译文未发布"
                    )
                current.artifacts = artifacts
                current.status, current.stage, current.progress = "COMPLETED", "completed", 100
                current.external_state, current.updated_at = "completed", now()
                job.status, job.stage, job.updated_at = "succeeded", "completed", now()
                job.result = {"translation_id": current.id}
    except asyncio.CancelledError:
        _failed(
            engine,
            job_id,
            "INTERRUPTED",
            "应用退出，翻译中断且未自动重发",
            submitted,
            interrupted=True,
        )
        raise
    except Exception as exc:
        if proxy is not None and getattr(proxy, "error_code", None):
            code, message = proxy.error_code, _proxy_error_message(proxy.error_code)
        elif isinstance(exc, KnowledgeError):
            code, message = exc.code, str(exc)
        else:
            code, message = "TRANSLATION_FAILED", "翻译失败或响应不兼容，未自动重发"
        _failed(engine, job_id, code, message, submitted)
    finally:
        if runtime is not None:
            try:
                await runtime.stop()
            except KnowledgeError as cleanup_error:
                _failed(engine, job_id, cleanup_error.code, str(cleanup_error), submitted)
                with Session(engine) as session, session.begin():
                    current = session.scalar(
                        select(PDFTranslation).where(PDFTranslation.job_id == job_id)
                    )
                    if current is not None:
                        current.warnings = [*current.warnings, str(cleanup_error)]
                        if current.status == "CANCELLED":
                            current.error = "翻译已取消；后续模型请求已阻断，但服务停止未能确认"
                        current.updated_at = now()
            else:
                with Session(engine) as session, session.begin():
                    current = session.scalar(
                        select(PDFTranslation).where(PDFTranslation.job_id == job_id)
                    )
                    if current is not None and current.status == "CANCELLED":
                        current.error = (
                            "翻译已取消；本应用自动启动的服务已关闭，已发送的请求仍可能计费"
                        )
                        current.updated_at = now()


def _save_outputs(
    data_dir: Path, job_id: str, outputs: dict[str, bytes], *, output_mode: str = "both"
) -> list[dict[str, Any]]:
    # Translation/result and job IDs intentionally match to keep artifact paths
    # independent of any server-provided filename or directory.
    expected = output_kinds(output_mode)
    if set(outputs) != set(expected):
        raise KnowledgeError("TRANSLATION_OUTPUT_INVALID", "译文输出集合与冻结模式不一致")
    root = data_dir.resolve() / "translations"
    destination = root / job_id
    root.mkdir(exist_ok=True)
    if not plain(root, directory=True):
        raise KnowledgeError("TRANSLATION_OUTPUT_INVALID", "译文目录不是受管普通目录")
    destination.mkdir(exist_ok=True)
    if not plain(destination, directory=True):
        raise KnowledgeError("TRANSLATION_OUTPUT_INVALID", "译文目标目录不是受管普通目录")
    metadata = []
    for kind in expected:
        content = outputs[kind]
        pages = _pdf_pages(content)
        path = destination / f"{kind}.pdf"
        if path.exists() or path.is_symlink():
            raise KnowledgeError("TRANSLATION_OUTPUT_EXISTS", "译文目标已存在，未覆盖旧文件")
        with path.open("xb") as stream:
            stream.write(content)
        metadata.append(
            {
                "kind": kind,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
                "page_count": pages,
            }
        )
    return metadata


def _failed(
    engine: Engine,
    job_id: str,
    code: str,
    message: str,
    submitted: bool,
    *,
    interrupted: bool = False,
) -> None:
    with Session(engine) as session, session.begin():
        row = session.scalar(select(PDFTranslation).where(PDFTranslation.job_id == job_id))
        job = session.get(Job, job_id)
        if row is not None and row.status in {"PENDING", "RUNNING"}:
            row.status = "INTERRUPTED" if interrupted else "FAILED"
            row.stage = "interrupted" if interrupted else "failed"
            row.error_code, row.error, row.updated_at = code, message, now()
            row.external_state = (
                "failed"
                if code == "TRANSLATION_EXTERNAL_FAILED"
                else "unknown"
                if submitted
                else "not_started"
            )
        if job is not None and job.status in {"queued", "running"}:
            job.status = "interrupted" if interrupted else "failed"
            job.stage, job.error, job.updated_at = (
                "interrupted" if interrupted else "failed",
                message,
                now(),
            )


def register_translation_api(app: FastAPI, engine: Callable[[], Engine], data_dir: Path) -> None:
    @app.get("/api/v1/settings/translation", response_model=TranslationSettings)
    def settings() -> TranslationSettings:
        with read_session(engine()) as session:
            return _settings(session)

    @app.put("/api/v1/settings/translation", response_model=TranslationSettings)
    def save_settings(body: TranslationSettings) -> TranslationSettings:
        with Session(engine()) as session, session.begin():
            row = session.get(PDFTranslationSettings, "global")
            if row is None:
                session.add(PDFTranslationSettings(id="global", **body.model_dump()))
            else:
                row.enabled, row.service_url = body.enabled, body.service_url
                row.launch_mode, row.python_path, row.server_path = (
                    body.launch_mode,
                    body.python_path,
                    body.server_path,
                )
        return body

    @app.post("/api/v1/settings/translation/check", response_model=TranslationHealth)
    async def check() -> TranslationHealth:
        with read_session(engine()) as session:
            value = _settings(session)
        return await _check_service(value, data_dir)

    @app.post("/api/v1/papers/{paper_id}/translations/prepare", response_model=TranslationPrepare)
    async def prepare(paper_id: str, body: TranslationRequest) -> TranslationPrepare:
        with read_session(engine()) as session:
            paper, revision, snapshot = _scope(session, paper_id, body)
            _source_bytes(session, revision)
            texts = session.scalars(
                select(Chunk.text).where(Chunk.revision_id == revision.id)
            ).all()
            count = sum(len(text) for text in texts)
            estimate = sum(len(text.encode("utf-8")) for text in texts)
            cache = _cached(
                session,
                _identity(revision, snapshot, body.output_mode),
                data_dir,
                output_mode=body.output_mode,
            )
            settings = _settings(session)
            payload = {
                "paper_id": paper.id,
                "document_version_id": revision.id,
                "source_hash": revision.sha256,
                "page_start": 1,
                "page_end": revision.page_count,
                "page_count": revision.page_count,
                "source_characters": count,
                "estimated_input_tokens": max(1, estimate),
                "profile_id": body.profile_id,
                "model_id": snapshot["model"],
                "cache_hit": cache is not None,
                "cached_translation_id": cache.id if cache else None,
                "launch_mode": settings.launch_mode,
                "output_mode": body.output_mode,
            }
        health = await _check_service(settings, data_dir) if settings.enabled else None
        return TranslationPrepare(
            **payload,
            prepare_fingerprint=_prepare_fingerprint(revision, snapshot, body, settings, health),
            service_ready=bool(health and health.available and not health.active_tasks),
            active_tasks=health.active_tasks if health else 0,
            warnings=[
                _service_warning(settings),
                "首版仅支持英文全文到简体中文；复杂公式、表格与扫描页的排版由外部引擎决定。",
                *([] if settings.enabled else ["请先在设置中启用本机翻译服务"]),
                *([health.message] if health and not health.available else []),
            ],
        )

    @app.post("/api/v1/papers/{paper_id}/translations", response_model=TranslationView)
    async def create(
        paper_id: str,
        body: TranslationCreate,
        idempotency_key: str | None = Header(
            default=None, alias="Idempotency-Key", min_length=8, max_length=120
        ),
    ) -> TranslationView:
        with read_session(engine()) as settings_session:
            checked_settings = _settings(settings_session)
        health = (
            await _check_service(checked_settings, data_dir) if checked_settings.enabled else None
        )
        with Session(engine()) as session, session.begin():
            paper, revision, snapshot = _scope(session, paper_id, body)
            settings = _settings(session)
            fingerprint = _prepare_fingerprint(revision, snapshot, body, settings, health)
            if settings != checked_settings or body.expected_fingerprint != fingerprint:
                raise _error(
                    "TRANSLATION_PREPARE_CHANGED", "来源、模型、服务或预算已变化，请重新预检"
                )
            key = _identity(revision, snapshot, body.output_mode)
            request_hash = digest({"paper_id": paper_id, **body.model_dump()})
            idempotency_id = f"pdf-translation:{idempotency_key}" if idempotency_key else None
            if idempotency_id:
                previous = session.get(Idempotency, idempotency_id)
                if previous:
                    if previous.request_hash != request_hash:
                        raise _error("IDEMPOTENCY_CONFLICT", "相同请求标识不能用于不同翻译参数")
                    row = session.get(PDFTranslation, previous.response.get("translation_id"))
                    if row is None or row.paper_id != paper_id:
                        raise _error("TRANSLATION_NOT_FOUND", "翻译记录不存在", 404)
                    return _view(session, row, cache_hit=bool(previous.response.get("cache_hit")))
            cached = _cached(session, key, data_dir, output_mode=body.output_mode)
            if cached:
                record_usage(
                    session,
                    project_id=paper.project_id,
                    paper_id=paper_id,
                    document_version_id=revision.id,
                    task_kind=TASK_KIND,
                    provider=str(snapshot["provider"]),
                    model=str(snapshot["model"]),
                    prompt_version=str(snapshot.get("translation_engine", ENGINE_VERSION)),
                    cache_hit=True,
                    extra={"translation_id": cached.id},
                )
                if idempotency_id:
                    session.add(
                        Idempotency(
                            key=idempotency_id,
                            request_hash=request_hash,
                            response={"translation_id": cached.id, "cache_hit": True},
                        )
                    )
                return _view(session, cached, cache_hit=True)
            if not body.allow_network or not body.exclusive_service:
                raise _error(
                    "TRANSLATION_CONSENT_REQUIRED", "请允许本次全文模型翻译，并确认使用专用本机服务"
                )
            if not settings.enabled:
                raise _error("TRANSLATION_DISABLED", "请先在设置中启用本机翻译服务")
            _source_bytes(session, revision)
            pending = session.scalar(
                select(PDFTranslation).where(
                    PDFTranslation.cache_key == key,
                    PDFTranslation.output_mode == body.output_mode,
                    PDFTranslation.status.in_(["PENDING", "RUNNING"]),
                )
            )
            if pending is not None:
                if idempotency_id:
                    session.add(
                        Idempotency(
                            key=idempotency_id,
                            request_hash=request_hash,
                            response={"translation_id": pending.id, "cache_hit": False},
                        )
                    )
                return _view(session, pending)
            identifier, timestamp = str(uuid4()), now()
            job = Job(
                id=identifier,
                project_id=paper.project_id,
                kind=TASK_KIND,
                payload={
                    "translation_id": identifier,
                    "paper_id": paper_id,
                    "document_version_id": revision.id,
                    "output_mode": body.output_mode,
                },
                status="queued",
                stage="queued",
                attempt=0,
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(job)
            session.flush()
            row = PDFTranslation(
                id=identifier,
                project_id=paper.project_id,
                paper_id=paper_id,
                document_version_id=revision.id,
                source_hash=revision.sha256,
                profile_id=body.profile_id,
                model_id=str(snapshot["model"]),
                model_snapshot=snapshot,
                output_mode=body.output_mode,
                runtime_snapshot=_runtime_snapshot(settings),
                cache_key=key,
                service_url=settings.service_url,
                engine_version=str(snapshot.get("translation_engine", ENGINE_VERSION)),
                status="PENDING",
                page_start=1,
                page_end=revision.page_count,
                page_count=revision.page_count,
                progress=0,
                stage="queued",
                job_id=identifier,
                external_task_id=None,
                external_state="not_started",
                error_code=None,
                error=None,
                warnings=[
                    _service_warning(settings),
                    "外部引擎生成的译文与排版尚未经科学质量核验；原文仍为证据来源。",
                ],
                artifacts=[],
                max_calls=body.max_calls,
                max_input_tokens=body.max_input_tokens,
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(row)
            if idempotency_id:
                session.add(
                    Idempotency(
                        key=idempotency_id,
                        request_hash=request_hash,
                        response={"translation_id": row.id},
                    )
                )
            session.flush()
            return _view(session, row)

    @app.get("/api/v1/papers/{paper_id}/translations", response_model=list[TranslationView])
    def list_translations(
        paper_id: str, document_version_id: str | None = Query(default=None)
    ) -> list[TranslationView]:
        with read_session(engine()) as session:
            if session.get(Paper, paper_id) is None:
                raise _error("PAPER_NOT_FOUND", "论文不存在", 404)
            statement = select(PDFTranslation).where(PDFTranslation.paper_id == paper_id)
            if document_version_id:
                statement = statement.where(
                    PDFTranslation.document_version_id == document_version_id
                )
            return [
                _view(session, row)
                for row in session.scalars(statement.order_by(PDFTranslation.created_at.desc()))
            ]

    @app.get(
        "/api/v1/papers/{paper_id}/translations/{translation_id}", response_model=TranslationView
    )
    def get_translation(paper_id: str, translation_id: str) -> TranslationView:
        with read_session(engine()) as session:
            row = session.get(PDFTranslation, translation_id)
            if row is None or row.paper_id != paper_id:
                raise _error("TRANSLATION_NOT_FOUND", "翻译记录不存在", 404)
            return _view(session, row)

    @app.post(
        "/api/v1/papers/{paper_id}/translations/{translation_id}/cancel",
        response_model=TranslationView,
    )
    def cancel(paper_id: str, translation_id: str) -> TranslationView:
        with Session(engine()) as session, session.begin():
            row = session.get(PDFTranslation, translation_id)
            if row is None or row.paper_id != paper_id:
                raise _error("TRANSLATION_NOT_FOUND", "翻译记录不存在", 404)
            job = session.get(Job, row.job_id)
            if job:
                cancel_translation_job(session, job)
            return _view(session, row)

    @app.get(
        "/api/v1/papers/{paper_id}/translations/{translation_id}/artifacts/{kind}",
        response_model=TranslationArtifactPath,
    )
    @app.get(
        "/api/v1/translations/{translation_id}/artifacts/{kind}",
        response_model=TranslationArtifactPath,
    )
    def artifact(
        translation_id: str, kind: str, paper_id: str | None = None
    ) -> TranslationArtifactPath:
        with read_session(engine()) as session:
            row = session.get(PDFTranslation, translation_id)
            if row is None or (paper_id is not None and row.paper_id != paper_id):
                raise _error("TRANSLATION_NOT_FOUND", "翻译记录不存在", 404)
            return _artifact(row, kind, data_dir)
