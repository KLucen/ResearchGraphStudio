"""Model-first document parsing and materialization helpers.

The ordinary Provider protocol is intentionally text based. This module keeps
the new model document layer separate from legacy ``Chunk``/``Section`` rows
and refuses unsupported PDF/image capability instead of silently invoking the
local parser. A test or future native provider can inject ``complete_document``
to send a real file reference; current configured chat providers can still run
the text fixture path for deterministic contract tests.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.app import Key, remember, remembered
from researchgraph.core import KnowledgeError
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.model_document_contracts import (
    ModelDocumentParseInput,
    ModelDocumentSegmentInput,
)
from researchgraph.model_document_models import (
    LlmDocumentOutput,
    LlmDocumentParse,
    LlmDocumentSegment,
)
from researchgraph.models import Job, Paper, now
from researchgraph.providers import Provider, ProviderError, require_document_capability


class ModelDocumentSegmentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parse_id: str
    chapter_ref: str
    chapter_title: str
    chapter_level: int
    chapter_order: int
    kind: str
    ordinal: int
    text: str | None
    latex: str | None
    mathml: str | None
    raw_table_text: str | None
    table_data: dict[str, Any] | None
    locator: dict[str, Any] | None
    confidence: float | None
    status: str
    warnings: list[str]
    created_at: str


class ModelDocumentParseView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    import_session_id: str
    parse_version: str
    provider_id: str | None
    model_id: str | None
    modality: str
    status: str
    raw_response: dict[str, Any] | None
    warnings: list[str]
    error_code: str | None
    error: str | None
    started_at: str | None
    finished_at: str | None
    created_at: str
    updated_at: str
    segments: list[ModelDocumentSegmentView] = Field(default_factory=list)


class ModelDocumentOutputView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    import_session_id: str
    parse_id: str
    item_kind: str
    status: str
    provider_id: str | None
    model_id: str | None
    output_json: dict[str, Any] | None
    usage: dict[str, Any] | None
    error_code: str | None
    error: str | None
    created_at: str
    updated_at: str


class DocumentParseMaterializeRequest(ModelDocumentParseInput):
    """Explicit test/bridge endpoint payload.

    ``raw_response`` is optional because a native provider may keep the raw
    provider envelope in the worker workspace. It is stored verbatim when
    supplied; the model cannot supply formal database IDs.
    """

    raw_response: dict[str, Any] | None = None
    provider_id: str | None = Field(default=None, max_length=120)
    model_id: str | None = Field(default=None, max_length=200)


class ModelDocumentSegmentEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=1_000_000)
    latex: str | None = Field(default=None, max_length=100_000)
    mathml: str | None = Field(default=None, max_length=200_000)
    raw_table_text: str | None = Field(default=None, max_length=500_000)
    table_data: dict[str, Any] | None = None


class ModelDocumentOutputEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_json: dict[str, Any]


def _failure(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def _segments_for(db: Session, parse_id: str) -> list[LlmDocumentSegment]:
    return list(
        db.scalars(
            select(LlmDocumentSegment)
            .where(LlmDocumentSegment.parse_id == parse_id)
            .order_by(
                LlmDocumentSegment.chapter_order,
                LlmDocumentSegment.chapter_level,
                LlmDocumentSegment.ordinal,
                LlmDocumentSegment.id,
            )
        ).all()
    )


def parse_view(db: Session, parse: LlmDocumentParse) -> ModelDocumentParseView:
    return ModelDocumentParseView(
        **{
            key: getattr(parse, key)
            for key in (
                "id",
                "import_session_id",
                "parse_version",
                "provider_id",
                "model_id",
                "modality",
                "status",
                "raw_response",
                "warnings",
                "error_code",
                "error",
                "started_at",
                "finished_at",
                "created_at",
                "updated_at",
            )
        },
        segments=[ModelDocumentSegmentView.model_validate(x) for x in _segments_for(db, parse.id)],
    )


def _refresh_session_status(db: Session, session: ImportSession) -> None:
    items = list(
        db.scalars(select(ImportPlanItem).where(ImportPlanItem.session_id == session.id)).all()
    )
    statuses = {item.status for item in items}
    if statuses and statuses <= {"succeeded"}:
        session.status = "succeeded"
    elif "failed" in statuses:
        session.status = "failed"
    elif "running" in statuses or "queued" in statuses:
        session.status = "running"
    elif "paused" in statuses:
        session.status = "paused"
    else:
        session.status = "planned"
    session.updated_at = now()


def _queue_selected_postprocessing(
    db: Session, session: ImportSession, parse: LlmDocumentParse
) -> None:
    """Create downstream jobs only after the model document is published.

    The parser is the sole source for this transition.  Each selected item gets
    one idempotent Job and keeps the frozen import plan/provider authorization.
    Legacy API workers still perform their normal source checks; this bridge
    only makes the user selection visible to the worker queue and never calls a
    provider inline.
    """

    if parse.status != "succeeded":
        return
    paper_id = str(session.source_snapshot.get("paper_id", ""))
    if not paper_id:
        # A PDF import stores the paper identity in the parent parse Job payload.
        parse_item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session.id,
                ImportPlanItem.item_kind == "document_parse",
            )
        )
        if parse_item is not None and parse_item.job_id:
            parent = db.get(Job, parse_item.job_id)
            paper_id = str((parent.payload or {}).get("paper_id", "")) if parent else ""
    if not paper_id:
        return
    plan = session.plan
    snapshot = None
    parse_item = db.scalar(
        select(ImportPlanItem).where(
            ImportPlanItem.session_id == session.id,
            ImportPlanItem.item_kind == "document_parse",
        )
    )
    if parse_item is not None and parse_item.job_id:
        parent = db.get(Job, parse_item.job_id)
        snapshot = (parent.payload or {}).get("provider_snapshot") if parent else None
    for item_kind in ("paper_overview", "paper_reading", "translation"):
        item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session.id,
                ImportPlanItem.item_kind == item_kind,
            )
        )
        if item is None or item.status not in {"planned", "interrupted"} or item.job_id:
            continue
        payload: dict[str, Any] = {
            "paper_id": paper_id,
            "import_session_id": session.id,
            "llm_document_parse_id": parse.id,
            "allow_network": bool(plan.get("allow_network", False)),
            "provider_snapshot": snapshot,
            "translation_mode": plan.get("translation_mode", "none"),
            "model_first_source": True,
            "item_kind": item_kind,
        }
        job = Job(
            id=str(uuid4()),
            project_id=session.project_id,
            kind="llm_document_postprocess",
            payload=payload,
            status="queued",
            stage="queued",
            attempt=0,
            created_at=now(),
            updated_at=now(),
        )
        db.add(job)
        item.job_id = job.id
        item.status = "queued"
        item.config = {**item.config, "llm_document_parse_id": parse.id}
        item.updated_at = now()
    _refresh_session_status(db, session)


class DocumentPostprocessSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_ref: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=1_000_000)
    role: str | None = Field(default=None, max_length=80)


class DocumentTranslation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_ref: str = Field(min_length=1, max_length=160)
    source_text: str = Field(min_length=1, max_length=1_000_000)
    translation_zh: str = Field(min_length=1, max_length=1_000_000)


class DocumentPostprocessResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_kind: str = Field(min_length=1, max_length=32)
    summary: str | None = Field(default=None, max_length=12000)
    sections: list[DocumentPostprocessSection] = Field(default_factory=list, max_length=2000)
    contributions: list[str] = Field(default_factory=list, max_length=20)
    findings: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    translations: list[DocumentTranslation] = Field(default_factory=list, max_length=2000)

    @classmethod
    def validate_for_item(
        cls, value: dict[str, Any], item_kind: str
    ) -> DocumentPostprocessResult:
        result = cls.model_validate(value)
        if result.item_kind != item_kind:
            raise ValueError("后处理响应任务类型不匹配")
        if item_kind != "translation" and result.translations:
            raise ValueError("只有 translation 任务可以返回逐段翻译")
        if item_kind == "translation" and not result.translations:
            raise ValueError("translation 任务必须返回逐段翻译")
        return result


def _validate_postprocess_evidence(
    db: Session, parse: LlmDocumentParse, result: DocumentPostprocessResult, item_kind: str
) -> None:
    segments = _segments_for(db, parse.id)
    chapter_refs = {segment.chapter_ref for segment in segments}
    if not chapter_refs:
        raise ValueError("模型解析没有可供后处理引用的章节材料")
    for section in result.sections:
        if section.chapter_ref not in chapter_refs:
            raise ValueError("后处理章节引用不属于当前模型文档")
    if item_kind in {"paper_overview", "paper_reading"} and not any(
        [result.summary, result.sections, result.contributions, result.findings, result.limitations]
    ):
        raise ValueError("概览或精读任务不能返回空结果")
    if item_kind == "translation":
        source_texts = {segment.text for segment in segments if segment.text}
        required_texts = {
            segment.text
            for segment in segments
            if segment.kind == "paragraph" and segment.text
        }
        seen: set[tuple[str, str]] = set()
        for translation in result.translations:
            key = (translation.chapter_ref, translation.source_text)
            if translation.chapter_ref not in chapter_refs or key in seen:
                raise ValueError("翻译结果包含重复或未知章节引用")
            if translation.source_text not in source_texts:
                raise ValueError("翻译原文必须精确引用模型解析段落")
            seen.add(key)
        translated_texts = {translation.source_text for translation in result.translations}
        if required_texts - translated_texts:
            raise ValueError("translation 任务必须覆盖全部正文段落")


def _postprocess_context(db: Session, parse: LlmDocumentParse, item_kind: str) -> dict[str, Any]:
    return {
        "item_kind": item_kind,
        "parse_id": parse.id,
        "chapters": [
            {
                "chapter_ref": segment.chapter_ref,
                "chapter_title": segment.chapter_title,
                "kind": segment.kind,
                "ordinal": segment.ordinal,
                "text": segment.text,
                "latex": segment.latex,
                "mathml": segment.mathml,
                "raw_table_text": segment.raw_table_text,
                "table_data": segment.table_data,
                "status": segment.status,
            }
            for segment in _segments_for(db, parse.id)
        ],
    }


async def execute_document_postprocess(
    engine: Engine, job_id: str, data_dir: Any, *, provider: Provider | None = None
) -> None:
    """Generate one selected post-import output from model-derived sections."""

    from researchgraph.model_settings import from_snapshot

    provider_config_error: str | None = None
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        if job is None or not job.payload or job.status not in {"queued", "running"}:
            return
        payload = dict(job.payload)
        session_id = str(payload.get("import_session_id", ""))
        item_kind = str(payload.get("item_kind", ""))
        import_session = db.get(ImportSession, session_id)
        parse = db.get(LlmDocumentParse, str(payload.get("llm_document_parse_id", "")))
        item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session_id, ImportPlanItem.item_kind == item_kind
            )
        )
        if (
            import_session is None
            or parse is None
            or parse.status != "succeeded"
            or item is None
            or item_kind not in {"paper_overview", "paper_reading", "translation"}
        ):
            return
        item.status = "running"
        job.status, job.stage, job.updated_at = "running", "generating", now()
        output = db.scalar(
            select(LlmDocumentOutput)
            .where(LlmDocumentOutput.parse_id == parse.id, LlmDocumentOutput.item_kind == item_kind)
            .order_by(LlmDocumentOutput.created_at.desc(), LlmDocumentOutput.id.desc())
        )
        if output is None:
            output = LlmDocumentOutput(
                id=str(uuid4()),
                import_session_id=session_id,
                parse_id=parse.id,
                item_kind=item_kind,
                status="pending",
                created_at=now(),
                updated_at=now(),
            )
            db.add(output)
            db.flush()
        output_id = output.id
        snapshot = payload.get("provider_snapshot")
        if provider is None and payload.get("allow_network") and isinstance(snapshot, dict):
            try:
                provider = from_snapshot(snapshot, data_dir, True)
            except (KnowledgeError, KeyError, TypeError, ValueError) as exc:
                # Do not leave the output/job in ``running`` when a frozen
                # provider snapshot is stale or network consent was revoked.
                # The common terminal failure path below records a stable code.
                provider_config_error = str(exc)
        context = _postprocess_context(db, parse, item_kind)
    if provider is None:
        message = provider_config_error or "后处理任务没有可用的模型 Provider；未生成输出"
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            output = db.get(LlmDocumentOutput, output_id)
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == session_id,
                    ImportPlanItem.item_kind == item_kind,
                )
            )
            if output is not None:
                output.status, output.error_code, output.error, output.updated_at = (
                    "failed",
                    (
                        "MODEL_DOCUMENT_PROVIDER_CONFIG_ERROR"
                        if provider_config_error
                        else "NETWORK_CONSENT_REQUIRED"
                    ),
                    message,
                    now(),
                )
            if item is not None:
                item.status, item.error, item.updated_at = "failed", message, now()
            if job is not None:
                job.status, job.stage, job.error, job.updated_at = (
                    "failed",
                    "failed",
                    message,
                    now(),
                )
            failed_session = db.get(ImportSession, session_id)
            if failed_session is not None:
                failed_session.error = message
                failed_session.updated_at = now()
                _refresh_session_status(db, failed_session)
        raise ProviderError("document_capability", message)
    prompt = (
        "你是论文阅读后处理模型，只根据给定的模型文档章节输出严格 JSON。"
        "不得补造输入中没有的实验数字、公式或表格内容；保留 chapter_ref。"
        f"任务类型为 {item_kind}。"
    )
    try:
        raw = await provider.complete(
            prompt, context, DocumentPostprocessResult.model_json_schema()
        )
        result = DocumentPostprocessResult.validate_for_item(json.loads(raw), item_kind)
        with Session(engine) as validation_db:
            parse = validation_db.get(
                LlmDocumentParse, str(payload.get("llm_document_parse_id", ""))
            )
            if parse is None:
                raise ValueError("模型解析结果已不存在")
            _validate_postprocess_evidence(validation_db, parse, result, item_kind)
    except Exception as exc:
        message = str(exc)
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            output = db.get(LlmDocumentOutput, output_id)
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == session_id, ImportPlanItem.item_kind == item_kind
                )
            )
            if output is not None:
                output.status, output.error_code, output.error, output.updated_at = (
                    "failed",
                    "MODEL_DOCUMENT_POSTPROCESS_FAILED",
                    message,
                    now(),
                )
            if item is not None:
                item.status, item.error, item.updated_at = "failed", message, now()
            if job is not None:
                job.status, job.stage, job.error, job.updated_at = (
                    "failed",
                    "failed",
                    message,
                    now(),
                )
            failed_session = db.get(ImportSession, session_id)
            if failed_session is not None:
                failed_session.error = message
                failed_session.updated_at = now()
                _refresh_session_status(db, failed_session)
        raise
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        output = db.get(LlmDocumentOutput, output_id)
        item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session_id, ImportPlanItem.item_kind == item_kind
            )
        )
        session = db.get(ImportSession, session_id)
        if (
            job is None
            or output is None
            or item is None
            or session is None
            or job.status != "running"
        ):
            return
        output.status, output.output_json, output.raw_response = (
            "succeeded",
            result.model_dump(),
            raw,
        )
        output.provider_id, output.model_id = (
            getattr(provider, "name", None),
            getattr(provider, "model", None),
        )
        output.usage, output.updated_at = dict(getattr(provider, "usage", {})), now()
        item.status, item.result, item.error, item.updated_at = (
            "succeeded",
            {"output_id": output.id},
            None,
            now(),
        )
        job.status, job.stage, job.result, job.error, job.updated_at = (
            "succeeded",
            "completed",
            {"output_id": output.id},
            None,
            now(),
        )
        _refresh_session_status(db, session)


def materialize_document_parse(
    db: Session,
    import_session_id: str,
    body: ModelDocumentParseInput,
    *,
    provider_id: str | None = None,
    model_id: str | None = None,
    raw_response: dict[str, Any] | None = None,
    parse_id: str | None = None,
    status: str = "succeeded",
    error_code: str | None = None,
    error: str | None = None,
    started_at: str | None = None,
) -> LlmDocumentParse:
    """Validate and persist one complete model document result.

    The formal parse and segment identifiers are generated here. This function
    is the only path used by the result bridge and worker publication, so model
    output cannot choose IDs or write legacy extraction tables.
    """

    session = db.get(ImportSession, import_session_id)
    if session is None:
        raise ValueError("导入会话不存在")
    if status not in {"succeeded", "failed", "paused"}:
        raise ValueError("模型解析状态无效")
    timestamp = now()
    parse = LlmDocumentParse(
        id=parse_id or str(uuid4()),
        import_session_id=import_session_id,
        parse_version=body.parse_version,
        provider_id=provider_id,
        model_id=model_id,
        modality=body.modality,
        status=status,
        raw_response=raw_response,
        warnings=list(body.warnings),
        error_code=error_code,
        error=error,
        started_at=started_at or timestamp,
        finished_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(parse)
    db.flush()
    if status == "succeeded":
        db.add_all(
            LlmDocumentSegment(
                id=str(uuid4()),
                parse_id=parse.id,
                chapter_ref=segment.chapter_ref,
                chapter_title=segment.chapter_title,
                chapter_level=segment.chapter_level,
                chapter_order=segment.chapter_order,
                kind=segment.kind,
                ordinal=segment.ordinal,
                text=segment.text,
                latex=segment.latex,
                mathml=segment.mathml,
                raw_table_text=segment.raw_table_text,
                table_data=segment.table_data,
                locator=segment.locator,
                confidence=segment.confidence,
                status=segment.status,
                warnings=list(segment.warnings),
                created_at=timestamp,
            )
            for segment in body.segments
        )
    item = db.scalar(
        select(ImportPlanItem).where(
            ImportPlanItem.session_id == import_session_id,
            ImportPlanItem.item_kind == "document_parse",
        )
    )
    if item is not None:
        item.status = "succeeded" if status == "succeeded" else status
        item.result = {
            "parse_id": parse.id,
            "parse_version": parse.parse_version,
            "segment_count": len(body.segments) if status == "succeeded" else 0,
            "warnings": list(body.warnings),
        }
        item.error = error
        item.updated_at = timestamp
    if status == "succeeded":
        _queue_selected_postprocessing(db, session, parse)
    _refresh_session_status(db, session)
    return parse


def _decode_provider_result(
    raw: str | dict[str, Any],
) -> tuple[ModelDocumentParseInput, dict[str, Any]]:
    if isinstance(raw, str):
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError("response", "模型文档解析响应不是有效 JSON") from exc
    else:
        envelope = raw
    if not isinstance(envelope, dict):
        raise ProviderError("response", "模型文档解析响应必须是 JSON 对象")
    try:
        parsed = ModelDocumentParseInput.model_validate(envelope)
    except Exception as exc:
        raise ProviderError("schema", "模型文档解析响应未通过契约校验") from exc
    return parsed, envelope


async def execute_document_parse(
    engine: Engine,
    job_id: str,
    data_dir: Any,
    *,
    provider: Provider | None = None,
) -> None:
    """Execute a queued ``llm_document_parse`` job.

    A provider can expose ``complete_document`` for native PDF/image transport.
    Without it, only an explicit text fixture is accepted. The legacy
    ``run_file_job`` parser is deliberately never called from this path.
    """

    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        if job is None or job.status != "running" or not job.payload:
            return
        payload = dict(job.payload)
        job_kind = job.kind
        session_id = str(payload.get("import_session_id", ""))
        import_session = db.get(ImportSession, session_id)
        if import_session is None:
            raise ValueError("导入会话不存在")
        modality = str(payload.get("modality") or import_session.plan.get("modality") or "text")
        require_multimodal = bool(
            payload.get("require_multimodal", import_session.plan.get("require_multimodal", False))
        )
        payload.setdefault("source_snapshot", import_session.source_snapshot or {})
        payload.setdefault(
            "file_name",
            (import_session.source_snapshot or {}).get("file_name"),
        )
        item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session_id,
                ImportPlanItem.item_kind == "document_parse",
            )
        )
        if item is not None and item.status in {"planned", "queued", "interrupted"}:
            item.status = "running"
            item.job_id = job_id
            item.updated_at = now()
            import_session.status = "running"
            import_session.updated_at = now()
        fixture = payload.get("source_text")
        raw_fixture = payload.get("response")
        provider_snapshot = payload.get("provider_snapshot")

    if job_kind == "zotero_import" and not payload.get("path"):
        from researchgraph.integrations import ZoteroAdapter

        adapter = ZoteroAdapter()
        library = str(payload.get("library", "users/0"))
        attachment_key = str(payload.get("attachment_key", ""))
        path = await asyncio.to_thread(adapter.attachment_path, library, attachment_key)
        if not path.is_file():
            raise ProviderError("document_input", "Zotero PDF 未下载到本机或无法读取")
        payload["path"] = str(path)
        with Session(engine) as db, db.begin():
            current = db.get(Job, job_id)
            if current is not None and current.status == "running":
                if not payload.get("paper_id") and current.project_id:
                    paper = Paper(
                        id=str(uuid4()),
                        project_id=current.project_id,
                        title=str(payload.get("item_key") or attachment_key),
                        created_at=now(),
                    )
                    db.add(paper)
                    db.flush()
                    payload["paper_id"] = paper.id
                current.payload = payload

    if provider is None and provider_snapshot:
        from researchgraph.model_settings import from_snapshot

        try:
            provider = from_snapshot(
                provider_snapshot,
                data_dir,
                bool(payload.get("allow_network", import_session.plan.get("allow_network", False))),
            )
        except (KnowledgeError, KeyError, TypeError, ValueError) as exc:
            message = str(exc)
            _record_document_failure(
                engine,
                job_id,
                code="MODEL_DOCUMENT_PROVIDER_CONFIG_ERROR",
                message=message,
            )
            raise ProviderError("document_capability", message) from exc
    elif provider is None and payload.get("allow_network"):
        # Freeze the extraction profile at queue time when the caller has
        # explicitly authorized network use. A missing profile is recorded as a
        # normal model failure; the worker never falls back to local parsing.
        from researchgraph.model_settings import from_snapshot, snapshot_for

        try:
            with Session(engine) as db:
                snapshot = snapshot_for(db, str(payload.get("project_id") or ""), "extraction")
            provider = from_snapshot(snapshot, data_dir, True)
        except (KnowledgeError, KeyError, TypeError, ValueError) as exc:
            message = str(exc)
            _record_document_failure(
                engine,
                job_id,
                code="MODEL_DOCUMENT_PROVIDER_CONFIG_ERROR",
                message=message,
            )
            raise ProviderError("document_capability", message) from exc

    try:
        if provider is None:
            if raw_fixture is None and fixture is None:
                raise ProviderError(
                    "document_capability",
                    "当前 Provider 未提供 PDF/文档输入适配；未回退本地解析",
                )
            # This branch is deliberately only for local deterministic fixtures.
            if modality != "text":
                raise ProviderError(
                    "document_capability",
                    "当前 Provider 仅支持文本 fixture，无法接收 PDF/图像；未回退本地解析",
                )
            raw_result: str | dict[str, Any] = raw_fixture or fixture  # type: ignore[assignment]
        else:
            require_document_capability(provider, modality, require_multimodal=require_multimodal)
            if hasattr(provider, "complete_document"):
                raw_result = await provider.complete_document(payload)
            elif modality == "text" and raw_fixture is not None:
                raw_result = raw_fixture
            else:
                raise ProviderError(
                    "document_capability",
                    "当前 Provider 未提供文档输入接口；未回退本地解析",
                )
    except ProviderError as exc:
        _record_document_failure(
            engine,
            job_id,
            code=(
                "MODEL_DOCUMENT_CAPABILITY_UNSUPPORTED"
                if exc.category == "document_capability"
                else "MODEL_DOCUMENT_PROVIDER_ERROR"
            ),
            message=str(exc),
            status=(
                "paused"
                if require_multimodal and exc.category == "document_capability"
                else "failed"
            ),
        )
        raise

    try:
        parsed, envelope = _decode_provider_result(raw_result)
    except ProviderError as exc:
        _record_document_failure(
            engine,
            job_id,
            code="MODEL_DOCUMENT_SCHEMA_INVALID",
            message=str(exc),
        )
        raise
    provider_id = getattr(provider, "name", None) if provider else None
    model_id = getattr(provider, "model", None) if provider else None
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        if job is None or job.status != "running":
            return
        job_payload = job.payload
        if not job_payload or "import_session_id" not in job_payload:
            return
        parse = materialize_document_parse(
            db,
            str(job_payload["import_session_id"]),
            parsed,
            provider_id=provider_id,
            model_id=model_id,
            raw_response=envelope,
            status="succeeded",
        )
        job.status = "succeeded"
        job.stage = "completed"
        job.result = {"parse_id": parse.id, "segment_count": len(parsed.segments)}
        job.error = None
        job.updated_at = now()


def _record_document_failure(
    engine: Engine,
    job_id: str,
    *,
    code: str,
    message: str,
    status: str = "failed",
) -> None:
    """Persist a terminal parse failure while retaining the failed Job history."""

    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        if job is None or not job.payload:
            return
        session_id = str(job.payload.get("import_session_id", ""))
        import_session = db.get(ImportSession, session_id)
        if import_session is None:
            return
        timestamp = now()
        job.status = status
        job.stage = status
        job.error = message
        job.updated_at = timestamp
        parse = LlmDocumentParse(
            id=str(uuid4()),
            import_session_id=session_id,
            parse_version=str(import_session.plan.get("parse_version", "llm-document-1")),
            provider_id=None,
            model_id=None,
            modality=str(job.payload.get("modality", "text")),
            status=status,
            raw_response=None,
            warnings=[],
            error_code=code,
            error=message,
            started_at=timestamp,
            finished_at=timestamp,
            created_at=timestamp,
            updated_at=timestamp,
        )
        db.add(parse)
        item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session_id,
                ImportPlanItem.item_kind == "document_parse",
            )
        )
        if item is not None:
            item.status = status
            item.error = message
            item.result = {"parse_id": parse.id, "error_code": code}
            item.updated_at = timestamp
        import_session.status = status
        import_session.error = message
        import_session.updated_at = timestamp


def register_model_document_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    @app.get(
        "/api/v1/import-sessions/{session_id}/document-parse",
        response_model=ModelDocumentParseView,
    )
    def get_document_parse(session_id: str) -> ModelDocumentParseView:
        with Session(engine()) as db:
            parse = db.scalar(
                select(LlmDocumentParse)
                .where(LlmDocumentParse.import_session_id == session_id)
                .order_by(LlmDocumentParse.created_at.desc(), LlmDocumentParse.id.desc())
            )
            if parse is None:
                raise _failure(404, "DOCUMENT_PARSE_NOT_FOUND", "模型文档解析结果不存在")
            return parse_view(db, parse)

    @app.get(
        "/api/v1/import-sessions/{session_id}/document-outputs",
        response_model=list[ModelDocumentOutputView],
    )
    def get_document_outputs(session_id: str) -> list[ModelDocumentOutputView]:
        with Session(engine()) as db:
            if db.get(ImportSession, session_id) is None:
                raise _failure(404, "IMPORT_SESSION_NOT_FOUND", "导入会话不存在")
            rows = db.scalars(
                select(LlmDocumentOutput)
                .where(LlmDocumentOutput.import_session_id == session_id)
                .order_by(LlmDocumentOutput.created_at, LlmDocumentOutput.id)
            ).all()
            return [ModelDocumentOutputView.model_validate(row) for row in rows]

    @app.patch(
        "/api/v1/import-sessions/{session_id}/document-segments/{segment_id}",
        response_model=ModelDocumentSegmentView,
    )
    def update_document_segment(
        session_id: str, segment_id: str, body: ModelDocumentSegmentEdit
    ) -> ModelDocumentSegmentView:
        changes = body.model_dump(exclude_unset=True)
        if not changes:
            raise _failure(422, "EMPTY_DOCUMENT_EDIT", "没有可保存的内容")
        with Session(engine()) as db, db.begin():
            if db.get(ImportSession, session_id) is None:
                raise _failure(404, "IMPORT_SESSION_NOT_FOUND", "导入会话不存在")
            segment = db.get(LlmDocumentSegment, segment_id)
            parse = db.get(LlmDocumentParse, segment.parse_id) if segment else None
            if segment is None or parse is None or parse.import_session_id != session_id:
                raise _failure(404, "DOCUMENT_SEGMENT_NOT_FOUND", "模型解析材料不存在")
            if parse.status != "succeeded":
                raise _failure(409, "DOCUMENT_PARSE_NOT_READY", "解析完成后才能编辑材料")
            original = {
                "chapter_ref": segment.chapter_ref,
                "chapter_title": segment.chapter_title,
                "chapter_level": segment.chapter_level,
                "chapter_order": segment.chapter_order,
                "kind": segment.kind,
                "ordinal": segment.ordinal,
                "text": segment.text,
                "latex": segment.latex,
                "mathml": segment.mathml,
                "raw_table_text": segment.raw_table_text,
                "table_data": segment.table_data,
                "locator": segment.locator,
                "confidence": segment.confidence,
                "status": segment.status,
                "warnings": segment.warnings,
            }
            try:
                validated = ModelDocumentSegmentInput.model_validate(original | changes)
            except ValueError as exc:
                raise _failure(422, "DOCUMENT_SEGMENT_EDIT_INVALID", str(exc)) from exc
            for name in changes:
                setattr(segment, name, getattr(validated, name))
            return ModelDocumentSegmentView.model_validate(segment)

    @app.patch(
        "/api/v1/import-sessions/{session_id}/document-outputs/{output_id}",
        response_model=ModelDocumentOutputView,
    )
    def update_document_output(
        session_id: str, output_id: str, body: ModelDocumentOutputEdit
    ) -> ModelDocumentOutputView:
        with Session(engine()) as db, db.begin():
            if db.get(ImportSession, session_id) is None:
                raise _failure(404, "IMPORT_SESSION_NOT_FOUND", "导入会话不存在")
            output = db.get(LlmDocumentOutput, output_id)
            parse = db.get(LlmDocumentParse, output.parse_id) if output else None
            if output is None or parse is None or output.import_session_id != session_id:
                raise _failure(404, "DOCUMENT_OUTPUT_NOT_FOUND", "模型生成内容不存在")
            if output.status != "succeeded" or parse.status != "succeeded":
                raise _failure(409, "DOCUMENT_OUTPUT_NOT_READY", "生成完成后才能编辑内容")
            try:
                result = DocumentPostprocessResult.validate_for_item(
                    body.output_json, output.item_kind
                )
                _validate_postprocess_evidence(db, parse, result, output.item_kind)
            except ValueError as exc:
                raise _failure(422, "DOCUMENT_OUTPUT_EDIT_INVALID", str(exc)) from exc
            output.output_json = result.model_dump()
            output.updated_at = now()
            return ModelDocumentOutputView.model_validate(output)

    @app.post(
        "/api/v1/import-sessions/{session_id}/document-parse/result",
        response_model=ModelDocumentParseView,
        status_code=201,
    )
    def publish_document_parse(
        session_id: str,
        body: DocumentParseMaterializeRequest,
        idempotency_key: Key,
    ) -> ModelDocumentParseView:
        request = {"session_id": session_id, **body.model_dump()}
        key = "document-parse-result:" + idempotency_key
        with Session(engine()) as db, db.begin():
            previous = remembered(db, key, request)
            if previous:
                return ModelDocumentParseView.model_validate(previous)
            if db.get(ImportSession, session_id) is None:
                raise _failure(404, "IMPORT_SESSION_NOT_FOUND", "导入会话不存在")
            parsed = materialize_document_parse(
                db,
                session_id,
                body,
                provider_id=body.provider_id,
                model_id=body.model_id,
                raw_response=body.raw_response or body.model_dump(exclude={"raw_response"}),
            )
            response = parse_view(db, parsed)
            remember(db, key, request, response.model_dump())
            return response
