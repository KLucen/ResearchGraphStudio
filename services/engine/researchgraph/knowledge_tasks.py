"""One paid dispatch per job, explicit bounded retry, raw-first local recovery."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError, digest
from researchgraph.knowledge_connection_models import (
    KnowledgeAnalysisEvent,
    KnowledgeConnectionRequest,
    KnowledgeConnectionRun,
    KnowledgeUsageTombstone,
)
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.knowledge_library import ensure_library, ensure_library_paper, publish_version
from researchgraph.knowledge_library_contracts import LibrarySettings
from researchgraph.knowledge_library_models import LibraryPaper, PaperKnowledgeVersion
from researchgraph.knowledge_sources import build_knowledge_sources, revalidate_knowledge_sources
from researchgraph.model_settings import from_snapshot
from researchgraph.models import Job, Paper, now
from researchgraph.paper_knowledge import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    SYSTEM_PROMPT,
    knowledge_model_input,
    knowledge_schema,
    validate_knowledge_response,
)
from researchgraph.providers import Provider


def check_knowledge_request_budget(db: Session, limit: int, *, additional: int = 0) -> None:
    """Sent slots and live reservations share the personal library's total budget."""
    extracts = (
        db.scalar(
            select(func.count())
            .select_from(KnowledgeExtractionRun)
            .where(
                or_(
                    KnowledgeExtractionRun.request_sent.is_(True),
                    KnowledgeExtractionRun.status.in_(["queued", "preparing", "request_sent"]),
                )
            )
        )
        or 0
    )
    connections = (
        db.scalar(
            select(func.count())
            .select_from(KnowledgeConnectionRequest)
            .join(
                KnowledgeConnectionRun,
                KnowledgeConnectionRun.id == KnowledgeConnectionRequest.run_id,
            )
            .where(
                or_(
                    KnowledgeConnectionRequest.sent_at.is_not(None),
                    (KnowledgeConnectionRequest.status == "planned")
                    & KnowledgeConnectionRun.status.in_(["queued", "running"]),
                )
            )
        )
        or 0
    )
    purged = db.scalar(select(func.count()).select_from(KnowledgeUsageTombstone)) or 0
    if extracts + connections + purged + additional > limit:
        raise KnowledgeError(
            "KNOWLEDGE_TOTAL_BUDGET_EXHAUSTED", "知识库累计请求预算已用完或已预留；未发送模型请求"
        )


def _active_library_paper(db: Session, run: KnowledgeExtractionRun) -> LibraryPaper:
    paper = db.get(LibraryPaper, run.library_paper_id) if run.library_paper_id else None
    if paper is None or paper.archived:
        raise KnowledgeError("KNOWLEDGE_PAPER_UNAVAILABLE", "知识库条目已归档或移除，已停止构建")
    return paper


def _effective_policy(current: LibrarySettings, frozen: LibrarySettings) -> LibrarySettings:
    values = frozen.model_dump()
    for field in (
        "max_candidates",
        "max_requests_per_run",
        "max_input_tokens",
        "max_output_tokens",
        "total_request_limit",
    ):
        values[field] = min(getattr(current, field), getattr(frozen, field))
    return LibrarySettings.model_validate(values)


def queue_knowledge_extract(
    db: Session,
    *,
    paper_id: str,
    source_kind: str,
    source_version_id: str,
    model_snapshot: dict[str, Any],
    allow_network: bool = False,
    auto_connect: bool = False,
    retry_failed: bool = False,
    max_attempts: int = 2,
    policy_snapshot: dict[str, Any] | None = None,
) -> Job:
    if type(max_attempts) is not int or not 1 <= max_attempts <= 2:
        raise KnowledgeError("KNOWLEDGE_BUDGET_INVALID", "每份相同输入最多允许两次显式模型请求")
    if model_snapshot.get("provider") == "mock":
        raise KnowledgeError("KNOWLEDGE_REAL_MODEL_REQUIRED", "请选择已配置的真实全局模型")
    manifest = build_knowledge_sources(db, paper_id, source_kind, source_version_id)
    paper = db.get(Paper, paper_id)
    assert paper is not None
    library_paper = ensure_library_paper(db, paper)
    if library_paper.archived:
        raise KnowledgeError("KNOWLEDGE_PAPER_UNAVAILABLE", "请先恢复已归档的知识库条目")
    current_policy = LibrarySettings.model_validate(ensure_library(db).settings_json)
    policy = (
        _effective_policy(current_policy, LibrarySettings.model_validate(policy_snapshot))
        if policy_snapshot is not None
        else current_policy
    )
    if policy_snapshot is not None and not current_policy.allow_network:
        raise KnowledgeError("KNOWLEDGE_POLICY_REVOKED", "自动构建的网络授权已撤销，未发送模型请求")
    input_hash = digest(manifest)
    # Credential references identify access, not scientific behavior.
    config = {key: value for key, value in model_snapshot.items() if key != "credential_ref"}
    key = digest(
        {
            "input": input_hash,
            "config": config,
            "prompt": SYSTEM_PROMPT,
            "schema": knowledge_schema(),
        }
    )
    runs = list(
        db.scalars(
            select(KnowledgeExtractionRun)
            .where(
                KnowledgeExtractionRun.paper_id == paper_id,
                KnowledgeExtractionRun.input_hash == input_hash,
            )
            .order_by(KnowledgeExtractionRun.created_at.desc(), KnowledgeExtractionRun.id.desc())
        )
    )
    matching = next((run for run in runs if run.cache_key == key), None)
    if matching:
        old_job = db.get(Job, matching.job_id)
        if old_job and old_job.status == "cancelled" and not retry_failed:
            return old_job
        if old_job and matching.status == "succeeded" and matching.raw_response is not None:
            content = validate_knowledge_response(matching.raw_response, manifest)
            if content != matching.output_json:
                raise KnowledgeError("KNOWLEDGE_CACHE_INVALID", "知识图谱缓存与冻结原始响应不一致")
            version = (
                db.get(PaperKnowledgeVersion, matching.version_id) if matching.version_id else None
            )
            if (
                version is None
                or version.library_paper_id != library_paper.id
                or version.content_json != content
                or version.source_snapshot_json != manifest
            ):
                raise KnowledgeError(
                    "KNOWLEDGE_CACHE_INVALID", "知识库版本与冻结来源或原始响应不一致"
                )
            return old_job
        if old_job and old_job.status in {"queued", "running"}:
            return old_job
        if old_job and old_job.status != "cancelled" and matching.raw_response is not None:
            try:
                validate_knowledge_response(matching.raw_response, manifest)
            except ValueError:
                pass
            else:
                # Explicit local revalidation has no network dependency or new dispatch slot.
                old_job.status, old_job.stage, old_job.error = "queued", "checking", None
                old_job.updated_at = now()
                matching.status, matching.error_code = "received", None
                return old_job
        if old_job and not retry_failed:
            return old_job
    # A model/configuration change cannot reset the source/input request budget.
    limit = min([max_attempts, *(run.max_attempts for run in runs)])
    dispatched = sum(run.request_sent for run in runs)
    if dispatched >= limit:
        raise KnowledgeError(
            "KNOWLEDGE_RETRY_EXHAUSTED", "相同解析输入已达到显式请求上限；未再次调用模型"
        )
    if runs and not retry_failed:
        raise KnowledgeError("KNOWLEDGE_RETRY_EXPLICIT", "同一输入已有构建记录，请明确选择重试")
    check_knowledge_request_budget(db, policy.total_request_limit, additional=1)
    job = Job(
        id=str(uuid4()),
        kind="knowledge_extract",
        project_id=manifest["project_id"],
        status="queued",
        stage="queued",
        created_at=now(),
        updated_at=now(),
    )
    run = KnowledgeExtractionRun(
        id=str(uuid4()),
        job_id=job.id,
        source_project_id=manifest["project_id"],
        library_paper_id=library_paper.id,
        paper_id=paper_id,
        source_kind=source_kind,
        source_id=source_version_id,
        source_manifest=manifest,
        input_hash=input_hash,
        model_snapshot=model_snapshot,
        policy_json=policy.model_dump(),
        cache_key=key,
        status="queued",
        request_sent=False,
        usage_json={"calls": 0, "retry_count": 0, "usage_source": "unknown"},
        previous_run_id=runs[0].id if runs else None,
        attempt=dispatched + 1,
        max_attempts=limit,
    )
    job.payload = {
        "run_id": run.id,
        "paper_id": paper_id,
        "allow_network": allow_network,
        "auto_connect": auto_connect,
        "automatic": policy_snapshot is not None,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
    }
    db.add_all([job, run])
    db.flush()
    return job


def _provider_usage(provider: Provider) -> dict[str, Any]:
    source = getattr(provider, "usage", {})
    if not isinstance(source, dict):
        source = {}
    result: dict[str, Any] = {"calls": 1, "usage_source": "unknown", "cost": None}
    for target, names in {
        "input_tokens": ("prompt_tokens", "input_tokens"),
        "output_tokens": ("completion_tokens", "output_tokens"),
        "total_tokens": ("total_tokens",),
    }.items():
        result[target] = next(
            (source[name] for name in names if type(source.get(name)) is int and source[name] >= 0),
            None,
        )
    if result["input_tokens"] is not None and result["output_tokens"] is not None:
        result["usage_source"] = "provider"
    return result


def _capacity_preflight(
    provider: Provider, manifest: dict[str, Any], policy: LibrarySettings
) -> dict[str, Any]:
    schema = knowledge_schema()
    capabilities = getattr(provider, "capabilities", None)
    # Conservative byte estimate is intentionally identified as capacity planning, not usage.
    model_input = knowledge_model_input(manifest)
    serialized = json.dumps(
        {"prompt": SYSTEM_PROMPT, "data": model_input, "schema": schema}, ensure_ascii=False
    )
    estimate = len(serialized.encode())
    # Deliberately conservative for mixed scientific English/Chinese; not provider usage.
    token_estimate = sum(1 if ord(char) < 128 else 6 for char in serialized) // 3 + 1
    context = getattr(capabilities, "context_window", None)
    output = getattr(capabilities, "max_output_tokens", None)
    if token_estimate > policy.max_input_tokens:
        raise KnowledgeError(
            "KNOWLEDGE_INPUT_BUDGET_EXCEEDED", "完整正文超出本次知识库输入预算；未截断或发送"
        )
    if policy.max_output_tokens < 2048:
        raise KnowledgeError("KNOWLEDGE_CAPACITY_INSUFFICIENT", "知识库输出预算不足以构建知识图谱")
    if context and estimate + 2048 + 512 > context:
        raise KnowledgeError(
            "KNOWLEDGE_CAPACITY_INSUFFICIENT", "完整正文超出当前模型容量；未截断或发送"
        )
    if output and output < 2048:
        raise KnowledgeError(
            "KNOWLEDGE_CAPACITY_INSUFFICIENT", "当前模型输出容量不足以构建知识图谱"
        )
    build = getattr(provider, "_build_body", None)
    if build:
        build(SYSTEM_PROMPT, model_input, schema)
        actual_limit = getattr(provider, "request_metadata", {}).get("output_limit")
        if actual_limit and actual_limit < 2048:
            raise KnowledgeError(
                "KNOWLEDGE_CAPACITY_INSUFFICIENT", "完整正文占用后模型输出容量不足"
            )
    return {
        "input_byte_estimate": estimate,
        "input_token_estimate": token_estimate,
        "minimum_output_tokens": 2048,
        "context_window": context,
        "max_output_tokens": output,
    }


def _publish(db: Session, job: Job, run: KnowledgeExtractionRun) -> None:
    _active_library_paper(db, run)
    revalidate_knowledge_sources(db, run.source_manifest)
    assert run.raw_response is not None
    content = validate_knowledge_response(run.raw_response, run.source_manifest)
    version = publish_version(
        db,
        paper_id=run.paper_id,
        source_kind=run.source_kind,
        source_id=run.source_id,
        source_fingerprint=run.source_manifest["source_fingerprint"],
        content_json=content,
        source_snapshot_json=run.source_manifest,
        evidence_status="grounded",
        provider_id=run.model_snapshot.get("provider"),
        model_id=run.model_snapshot.get("model"),
        job_id=job.id,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
    )
    run.output_json, run.version_id = content, version.id
    run.library_paper_id = version.library_paper_id
    run.status, run.error_code, run.updated_at = "succeeded", None, now()
    if (job.payload or {}).get("auto_connect") and db.get(
        KnowledgeAnalysisEvent, version.id
    ) is None:
        db.add(KnowledgeAnalysisEvent(version_id=version.id, state="pending"))
    job.status, job.stage, job.error, job.updated_at = "succeeded", "completed", None, now()
    job.result = {"knowledge_version_id": version.id, "library_paper_id": version.library_paper_id}


def recover_knowledge_extractions(engine: Engine) -> int:
    """Startup records uncertainty; only an explicit action may resume a received raw."""
    count = 0
    with Session(engine) as db, db.begin():
        for run in db.scalars(
            select(KnowledgeExtractionRun).where(
                KnowledgeExtractionRun.status.in_(
                    ["queued", "preparing", "request_sent", "received"]
                )
            )
        ):
            job = db.get(Job, run.job_id)
            if job is None or job.status in {"succeeded", "cancelled", "failed"}:
                continue
            run.status, run.error_code, run.updated_at = (
                "interrupted",
                "KNOWLEDGE_REQUEST_INTERRUPTED",
                now(),
            )
            job.status, job.stage, job.error, job.updated_at = (
                "interrupted",
                "interrupted",
                "KNOWLEDGE_REQUEST_INTERRUPTED",
                now(),
            )
            count += 1
    return count


async def run_knowledge_extract(
    engine: Engine, job_id: str, data_dir: Path, *, provider: Provider | None = None
) -> None:
    active = provider
    sent_here = False
    try:
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            run = db.scalar(
                select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
            )
            if job is None or run is None or job.status == "cancelled":
                return
            if run.status == "succeeded":
                return
            _active_library_paper(db, run)
            revalidate_knowledge_sources(db, run.source_manifest)
            if run.raw_response is not None:
                _publish(db, job, run)
                return
            if run.request_sent:
                raise KnowledgeError(
                    "KNOWLEDGE_REQUEST_INTERRUPTED",
                    "先前请求已发送且未保留完整响应；不会自动重发，请显式重试",
                )
            if not (job.payload or {}).get("allow_network"):
                raise KnowledgeError(
                    "NETWORK_CONSENT_REQUIRED", "请明确允许发送所选解析正文以构建知识图谱"
                )
            snapshot = run.model_snapshot
            manifest = run.source_manifest
            policy = LibrarySettings.model_validate(run.policy_json)
            current_policy = LibrarySettings.model_validate(ensure_library(db).settings_json)
            policy = _effective_policy(current_policy, policy)
            if (job.payload or {}).get("automatic") and not current_policy.allow_network:
                raise KnowledgeError("KNOWLEDGE_POLICY_REVOKED", "自动构建的网络授权已撤销")
        if active is None:
            active = from_snapshot(snapshot, data_dir, True)
        if hasattr(active, "task_output_budget"):
            active.task_output_budget = policy.max_output_tokens
        prepare = getattr(active, "prepare", None)
        if prepare:
            await prepare()
        preflight = _capacity_preflight(active, manifest, policy)
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            run = db.scalar(
                select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
            )
            if job is None or run is None or job.status == "cancelled":
                return
            if run.request_sent:
                return  # Another worker already owns this durable slot.
            _active_library_paper(db, run)
            revalidate_knowledge_sources(db, run.source_manifest)
            current_policy = LibrarySettings.model_validate(ensure_library(db).settings_json)
            if (job.payload or {}).get("automatic") and not current_policy.allow_network:
                raise KnowledgeError("KNOWLEDGE_POLICY_REVOKED", "自动构建的网络授权已撤销")
            policy = _effective_policy(current_policy, policy)
            if hasattr(active, "task_output_budget"):
                active.task_output_budget = policy.max_output_tokens
            preflight = _capacity_preflight(active, manifest, policy)
            check_knowledge_request_budget(
                db, min(policy.total_request_limit, current_policy.total_request_limit)
            )
            dispatched = db.scalars(
                select(KnowledgeExtractionRun).where(
                    KnowledgeExtractionRun.paper_id == run.paper_id,
                    KnowledgeExtractionRun.input_hash == run.input_hash,
                    KnowledgeExtractionRun.request_sent.is_(True),
                )
            ).all()
            if len(dispatched) >= run.max_attempts:
                raise KnowledgeError("KNOWLEDGE_RETRY_EXHAUSTED", "相同解析输入已达到显式请求上限")
            run.request_sent, run.status, run.updated_at = True, "request_sent", now()
            run.usage_json = {
                "calls": 1,
                "retry_count": int(bool(dispatched)),
                "usage_source": "unknown",
                "cost": None,
            }
            run.request_metadata = {
                "capacity": preflight,
                "prompt_version": PROMPT_VERSION,
                "schema_version": SCHEMA_VERSION,
                "provider": getattr(active, "request_metadata", {}),
            }
            job.status, job.stage, job.updated_at = "running", "generating", now()
        sent_here = True
        raw = await active.complete(
            SYSTEM_PROMPT, knowledge_model_input(manifest), knowledge_schema()
        )
        # Persist the complete raw and receipt before DTO validation or source rereads.
        with Session(engine) as db, db.begin():
            run = db.scalar(
                select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
            )
            assert run is not None
            run.raw_response, run.status, run.updated_at = raw, "received", now()
            run.usage_json = {**run.usage_json, **_provider_usage(active)}
            run.request_metadata = {
                **run.request_metadata,
                "provider": getattr(active, "request_metadata", {}),
            }
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            run = db.scalar(
                select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
            )
            if job and run and job.status != "cancelled":
                _publish(db, job, run)
            elif job and run:
                run.status, run.updated_at = "cancelled", now()
    except (Exception, asyncio.CancelledError) as error:
        code = getattr(error, "code", None) or (
            "KNOWLEDGE_RESPONSE_INVALID"
            if isinstance(error, ValueError)
            else "KNOWLEDGE_REQUEST_FAILED"
        )
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            run = db.scalar(
                select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
            )
            if run and run.status != "succeeded":
                run.status, run.error_code, run.updated_at = "failed", code, now()
                if sent_here and active:
                    run.usage_json = {**run.usage_json, **_provider_usage(active)}
                    partial = getattr(active, "partial_output", None)
                    if partial and run.raw_response is None:
                        run.request_metadata = {**run.request_metadata, "partial_output": partial}
                if job and job.status != "cancelled":
                    job.status, job.stage, job.error, job.updated_at = (
                        "failed",
                        "failed",
                        code,
                        now(),
                    )
        if isinstance(error, asyncio.CancelledError):
            raise
