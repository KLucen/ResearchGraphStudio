"""Reading-only card sets, independent of the research knowledge graph contract."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError, digest
from researchgraph.knowledge_sources import build_knowledge_sources
from researchgraph.models import AttachmentRevision, Job, Paper, now
from researchgraph.paper_card_set_contracts import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    SYSTEM_PROMPT,
    anchored_model_input,
    model_input,
    paper_card_set_schema,
    validate_paper_card_set,
    validate_saved_paper_card_set,
)
from researchgraph.paper_overview_contracts import OverviewUsage, OverviewView
from researchgraph.paper_overview_models import PaperOverviewResult
from researchgraph.providers import Provider
from researchgraph.task_runtime import ModelWaitCancelled, wait_for_model


def build_card_manifest(
    db: Session, paper_id: str, source_kind: str, source_id: str
) -> dict[str, Any]:
    """Use every saved eligible source, without re-reading PDF or modifying K2."""
    return build_knowledge_sources(db, paper_id, source_kind, source_id)


def card_context(manifest: dict[str, Any], *, anchored: bool = False) -> dict[str, Any]:
    return {
        **(anchored_model_input(manifest) if anchored else model_input(manifest)),
        "paper_id": manifest["paper_id"],
        "document_version_id": manifest["source_id"],
        "source_fingerprint": manifest["source_fingerprint"],
    }


def card_overview_view(db: Session, row: PaperOverviewResult) -> OverviewView:
    content = None
    if row.schema_version != SCHEMA_VERSION:
        raise KnowledgeError("OVERVIEW_RETIRED", "旧概览已退出阅读工作区，请生成新的文章卡片集")
    if row.status == "COMPLETED":
        manifest = build_card_manifest(db, row.paper_id, "local_revision", row.document_version_id)
        try:
            content = validate_saved_paper_card_set(row.paper_card_json or {}, manifest)
        except ValueError as error:
            raise KnowledgeError(
                "CARD_SOURCE_OR_CONTENT_CHANGED", "卡片集与当前解析或已验证内容不一致，请重新生成"
            ) from error
    return OverviewView(
        id=row.id,
        paper_id=row.paper_id,
        document_version_id=row.document_version_id,
        pdf_hash=row.pdf_hash,
        input_hash=row.input_hash,
        schema_version=row.schema_version,
        prompt_version=row.prompt_version,
        provider_id=row.provider_id,
        model_id=row.model_id,
        status=cast(Any, row.status),
        graph_status="NOT_ENOUGH_INFO",
        card_set=content,
        paper_card=None,
        graph=None,
        usage=OverviewUsage.model_validate(row.usage_json or {}),
        generated_at=row.updated_at,
        cache_hit=row.cache_hit,
        job_id=row.job_id,
        error_code=row.error_code,
        error=row.error,
    )


def latest_card_overview(
    db: Session, paper_id: str, revision_id: str | None
) -> PaperOverviewResult | None:
    query = select(PaperOverviewResult).where(
        PaperOverviewResult.paper_id == paper_id,
        PaperOverviewResult.schema_version == SCHEMA_VERSION,
    )
    if revision_id:
        query = query.where(PaperOverviewResult.document_version_id == revision_id)
    return db.scalar(
        query.order_by(PaperOverviewResult.created_at.desc(), PaperOverviewResult.id.desc()).limit(
            1
        )
    )


def _identity(manifest: dict[str, Any], snapshot: dict[str, Any]) -> tuple[str, str]:
    configuration = digest(
        {
            key: snapshot.get(key)
            for key in ("provider", "model", "base_url", "parameters", "output_policy")
        }
    )
    identity = digest(
        {
            "source": manifest["source_fingerprint"],
            "schema": SCHEMA_VERSION,
            "prompt_version": PROMPT_VERSION,
            "prompt": SYSTEM_PROMPT,
            "schema_definition": paper_card_set_schema(),
            "config": configuration,
        }
    )
    return identity, configuration


def queue_card_overview(
    db: Session,
    paper: Paper,
    revision: AttachmentRevision,
    snapshot: dict[str, Any],
    *,
    force: bool,
    retry: bool,
) -> OverviewView:
    manifest = build_card_manifest(db, paper.id, "local_revision", revision.id)
    identity, configuration = _identity(manifest, snapshot)
    prior = db.scalar(
        select(PaperOverviewResult)
        .where(
            PaperOverviewResult.paper_id == paper.id,
            PaperOverviewResult.document_version_id == revision.id,
            PaperOverviewResult.cache_key == identity,
            PaperOverviewResult.schema_version == SCHEMA_VERSION,
        )
        .order_by(PaperOverviewResult.created_at.desc(), PaperOverviewResult.id.desc())
        .limit(1)
    )
    if prior is not None:
        if prior.status == "PENDING" or (prior.status == "FAILED" and not retry and not force):
            return card_overview_view(db, prior)
        if prior.status == "COMPLETED" and not force:
            # Explicit generate may reuse only a fully revalidated current-source result.
            from researchgraph.lite_usage import record_usage

            try:
                view = card_overview_view(db, prior)
            except KnowledgeError as error:
                if error.code != "CARD_SOURCE_OR_CONTENT_CHANGED":
                    raise
                # The explicit authorized generate action may replace an unusable
                # cache entry. Reading alone never repairs it or sends a request.
            else:
                record_usage(
                    db,
                    project_id=paper.project_id,
                    paper_id=paper.id,
                    document_version_id=revision.id,
                    task_kind="paper_overview",
                    provider=prior.provider_id,
                    model=prior.model_id,
                    prompt_version=PROMPT_VERSION,
                    cache_hit=True,
                    extra={"schema_version": SCHEMA_VERSION, "cache_key": identity},
                )
                return view.model_copy(update={"cache_hit": True, "usage": OverviewUsage()})
    timestamp = now()
    job = Job(
        id=str(uuid4()),
        project_id=paper.project_id,
        kind="paper_overview",
        payload={
            "paper_id": paper.id,
            "document_version_id": revision.id,
            "allow_network": True,
            "model_snapshot": snapshot,
            "overview_contract_version": 2,
            "source_fingerprint": manifest["source_fingerprint"],
            "cache_key": identity,
            "config_fingerprint": configuration,
            "retry_of": prior.id if prior and prior.status == "FAILED" else None,
            "force_regenerate": force,
        },
        status="queued",
        stage="queued",
        attempt=0,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(job)
    db.flush()
    row = PaperOverviewResult(
        id=str(uuid4()),
        project_id=paper.project_id,
        paper_id=paper.id,
        document_version_id=revision.id,
        pdf_hash=revision.sha256,
        input_hash=manifest["source_fingerprint"],
        cache_key=identity,
        schema_version=SCHEMA_VERSION,
        prompt_version=PROMPT_VERSION,
        provider_id=str(snapshot["provider"]),
        model_id=str(snapshot["model"]),
        status="PENDING",
        graph_status="NOT_ENOUGH_INFO",
        job_id=job.id,
        request_metadata={"source_manifest": manifest, "request_started": False},
        usage_json=OverviewUsage().model_dump(),
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(row)
    db.flush()
    return card_overview_view(db, row)


async def execute_card_overview(
    engine: Engine, job_id: str, data_dir: Path, *, provider: Provider | None = None
) -> None:
    from researchgraph.lite_models import LiteTokenUsage
    from researchgraph.lite_usage import record_usage
    from researchgraph.model_settings import from_snapshot
    from researchgraph.paper_overview_api import _provider_usage
    from researchgraph.providers import ConfiguredProvider, ProviderError

    raw: str | None = None
    usage_id: str | None = None

    def retain_failure(error: BaseException, *, interrupted: bool = False) -> None:
        not_sent = (
            isinstance(provider, ConfiguredProvider)
            and isinstance(error, ProviderError)
            and error.category in {"context_limit", "structured_output_unsupported"}
        )
        code = (
            "INTERRUPTED"
            if interrupted
            else error.code
            if isinstance(error, KnowledgeError)
            else (
                "CARD_PROVIDER_FAILED"
                if isinstance(error, ProviderError)
                else "CARD_RESPONSE_SCHEMA_INVALID"
                if isinstance(error, ValidationError)
                else "CARD_RESPONSE_INVALID"
            )
        )
        message = (
            "应用退出，卡片集任务已中断；已有响应保留，未自动重发"
            if interrupted
            else str(error)
            if isinstance(error, (KnowledgeError, ProviderError))
            else ("卡片集未通过字段或引文校验；完整响应已保留在本机，未发布或自动重发")
        )
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            row = db.scalar(select(PaperOverviewResult).where(PaperOverviewResult.job_id == job_id))
            if interrupted and job and job.status == "cancelled":
                code, message = "CANCELLED", "卡片集任务已取消；已有响应保留，未自动重发"
            if job and job.status in {"queued", "running"}:
                job.status, job.stage, job.error, job.updated_at = (
                    "interrupted" if interrupted else "failed",
                    "interrupted" if interrupted else "failed",
                    message,
                    now(),
                )
            if row and row.status == "PENDING":
                row.status, row.error_code, row.error, row.updated_at = (
                    "FAILED",
                    code,
                    message,
                    now(),
                )
            if row is not None:
                # Preserve the response and receipt even if publication rolled back or
                # cancellation won while the provider was generating.
                row.raw_output = (
                    raw if raw is not None else getattr(provider, "partial_output", None)
                )
                row.request_metadata = {
                    **row.request_metadata,
                    "provider": getattr(provider, "request_metadata", {}),
                    **({"generation_request_sent": False} if not_sent else {}),
                }
                if usage_id is not None and provider is not None:
                    inp, out, total, source = _provider_usage(provider)
                    row.usage_json = OverviewUsage(
                        input_tokens=inp,
                        output_tokens=out,
                        total_tokens=total,
                        calls=0 if not_sent else 1,
                        usage_source=cast(Any, source),
                        retry_count=(
                            int(bool((job.payload or {}).get("retry_of")))
                            if job and not not_sent
                            else 0
                        ),
                    ).model_dump()
            failed_usage = db.get(LiteTokenUsage, usage_id) if usage_id else None
            if failed_usage:
                failed_usage.status = (
                    "not_sent"
                    if not_sent
                    else "cancelled"
                    if job and job.status == "cancelled"
                    else "interrupted"
                    if interrupted
                    else "failed"
                )
                if not_sent:
                    failed_usage.retry_count = 0
                    failed_usage.extra = {
                        **(failed_usage.extra or {}),
                        "generation_request_sent": False,
                    }
                failed_usage.reason_code = code
                if provider:
                    inp, out, total, source = _provider_usage(provider)
                    (
                        failed_usage.input_tokens,
                        failed_usage.output_tokens,
                        failed_usage.total_tokens,
                    ) = inp, out, total
                    failed_usage.usage_source = source

    try:
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            row = db.scalar(select(PaperOverviewResult).where(PaperOverviewResult.job_id == job_id))
            if job is None or row is None or job.status not in {"queued", "running"}:
                return
            if row.status != "PENDING" or (row.request_metadata or {}).get("request_started"):
                return
            manifest = build_card_manifest(
                db, row.paper_id, "local_revision", row.document_version_id
            )
            if manifest != row.request_metadata.get("source_manifest"):
                raise KnowledgeError("CARD_SOURCE_CHANGED", "解析内容已变化，未发送卡片生成请求")
            payload = job.payload or {}
            snapshot = payload.get("model_snapshot")
            if not isinstance(snapshot, dict) or _identity(manifest, snapshot)[0] != row.cache_key:
                raise KnowledgeError(
                    "CARD_CONTRACT_CHANGED", "卡片生成合同或配置已变化，请新建任务"
                )
            if not payload.get("allow_network"):
                raise KnowledgeError("NETWORK_CONSENT_REQUIRED", "请明确允许本次卡片生成请求")
            if provider is None:
                provider = from_snapshot(snapshot, data_dir, True)
            context, schema = card_context(manifest), paper_card_set_schema()
            build_body = getattr(provider, "_build_body", None)
            if callable(build_body):
                # Run the same deterministic request validation before reserving a
                # send slot. Frozen capabilities require no network discovery here.
                build_body(SYSTEM_PROMPT, context, schema)
            usage = record_usage(
                db,
                project_id=row.project_id,
                paper_id=row.paper_id,
                document_version_id=row.document_version_id,
                task_kind="paper_overview",
                provider=row.provider_id,
                model=row.model_id,
                prompt_version=PROMPT_VERSION,
                task_run_id=job.id,
                status="started",
                retry_count=int(bool(payload.get("retry_of"))),
                extra={"schema_version": SCHEMA_VERSION, "cache_key": row.cache_key},
            )
            db.flush()
            usage_id = usage.id
            row.request_metadata = {**row.request_metadata, "request_started": True}
            job.status, job.stage, job.updated_at = "running", "generating", now()
        raw = await wait_for_model(provider.complete(SYSTEM_PROMPT, context, schema))
        content = validate_paper_card_set(raw, manifest)
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            row = db.scalar(select(PaperOverviewResult).where(PaperOverviewResult.job_id == job_id))
            if job is None or row is None:
                return
            row.raw_output = raw
            inp, out, total, source = _provider_usage(provider)
            row.usage_json = OverviewUsage(
                input_tokens=inp,
                output_tokens=out,
                total_tokens=total,
                calls=1,
                retry_count=int(bool((job.payload or {}).get("retry_of"))),
                usage_source=cast(Any, source),
            ).model_dump()
            current_usage = db.get(LiteTokenUsage, usage_id) if usage_id else None
            if current_usage:
                (
                    current_usage.input_tokens,
                    current_usage.output_tokens,
                    current_usage.total_tokens,
                ) = inp, out, total
                current_usage.usage_source = source
                current_usage.status = "succeeded" if job.status == "running" else job.status
            if job.status != "running":
                return
            fresh = build_card_manifest(db, row.paper_id, "local_revision", row.document_version_id)
            if fresh != manifest:
                raise KnowledgeError("CARD_SOURCE_CHANGED", "解析内容已变化，卡片集未发布")
            validate_saved_paper_card_set(content, fresh)
            row.paper_card_json, row.graph_json = content, None
            row.status, row.graph_status, row.updated_at = "COMPLETED", "NOT_ENOUGH_INFO", now()
            row.request_metadata = {
                **row.request_metadata,
                "provider": getattr(provider, "request_metadata", {}),
            }
            job.status, job.stage, job.updated_at = "succeeded", "completed", now()
            job.result = {"overview_result_id": row.id, "schema_version": SCHEMA_VERSION}
    except asyncio.CancelledError as error:
        retain_failure(error, interrupted=True)
        raise
    except ModelWaitCancelled as error:
        retain_failure(error, interrupted=True)
    except Exception as error:
        retain_failure(error)
