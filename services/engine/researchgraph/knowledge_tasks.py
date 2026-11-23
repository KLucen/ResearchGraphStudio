"""One paid dispatch per job, explicit bounded retry, raw-first local recovery."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from researchgraph.archive_models import archived_target
from researchgraph.core import KnowledgeError, digest, text_hash
from researchgraph.knowledge_budgets import (
    MINIMUM_KNOWLEDGE_OUTPUT_TOKENS,
    estimate_knowledge_input_tokens,
    stricter_limit,
)
from researchgraph.knowledge_connection_models import (
    KnowledgeAnalysisEvent,
    KnowledgeConnectionRequest,
    KnowledgeConnectionRun,
    KnowledgeUsageTombstone,
)
from researchgraph.knowledge_diagnostics import diagnostic_for_raw, stored_extraction_prompt_version
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.knowledge_library import ensure_library, ensure_library_paper, publish_version
from researchgraph.knowledge_library_contracts import LibrarySettings
from researchgraph.knowledge_library_models import LibraryPaper, PaperKnowledgeVersion
from researchgraph.knowledge_quote_recovery import isolate_unmatched_quotes
from researchgraph.knowledge_sources import build_knowledge_sources, revalidate_knowledge_sources
from researchgraph.model_settings import from_snapshot
from researchgraph.models import Job, Paper, now
from researchgraph.paper_knowledge import (
    LEGACY_PROMPT_VERSION,
    PREVIOUS_PROMPT_VERSION,
    PROMPT_VERSION,
    RELATION_RULE_VERSION,
    SCHEMA_VERSION,
    isolate_invalid_knowledge_relations,
    knowledge_contract,
    knowledge_model_input,
    validate_knowledge_response,
)
from researchgraph.providers import Provider, ProviderError
from researchgraph.task_runtime import wait_for_model


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
        values[field] = stricter_limit(getattr(current, field), getattr(frozen, field))
    return LibrarySettings.model_validate(values)


def _request_contract(run: KnowledgeExtractionRun) -> dict[str, Any]:
    frozen = (run.request_metadata or {}).get("request_contract")
    if frozen is None:
        # Previously queued/running records used precisely this legacy request.
        return knowledge_contract(LEGACY_PROMPT_VERSION)
    if not isinstance(frozen, dict) or frozen.get("contract_hash") != digest(
        {key: value for key, value in frozen.items() if key != "contract_hash"}
    ):
        raise KnowledgeError("KNOWLEDGE_CONTEXT_CHANGED", "冻结知识抽取协议完整性校验失败")
    if frozen.get("prompt_version") not in {
        LEGACY_PROMPT_VERSION,
        PREVIOUS_PROMPT_VERSION,
        PROMPT_VERSION,
    }:
        raise KnowledgeError("KNOWLEDGE_CONTEXT_CHANGED", "冻结知识抽取协议版本不可用")
    return deepcopy(frozen)


def validate_extraction_response(run: KnowledgeExtractionRun) -> dict[str, Any]:
    assert run.raw_response is not None
    return validate_knowledge_response(
        run.raw_response,
        run.source_manifest,
        prompt_version=_request_contract(run)["prompt_version"],
    )


def _extract_cache_key(input_hash: str, config: dict[str, Any], contract: dict[str, Any]) -> str:
    return digest(
        {
            "input": input_hash,
            "config": config,
            "prompt": contract["prompt"],
            "schema": contract["schema"],
        }
    )


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
    if archived_target(db, "paper", paper_id):
        raise KnowledgeError("KNOWLEDGE_PAPER_UNAVAILABLE", "请先恢复文献库中已归档的论文")
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
    if policy_snapshot is not None and not (
        current_policy.allow_network and current_policy.auto_collect
    ):
        raise KnowledgeError("KNOWLEDGE_POLICY_REVOKED", "自动构建的网络授权已撤销，未发送模型请求")
    input_hash = digest(manifest)
    # Credential references identify access, not scientific behavior.
    config = {key: value for key, value in model_snapshot.items() if key != "credential_ref"}
    contract = knowledge_contract()
    key = _extract_cache_key(input_hash, config, contract)
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
    if matching is None and runs:
        old_keys = {
            _extract_cache_key(input_hash, config, knowledge_contract(version))
            for version in (LEGACY_PROMPT_VERSION, PREVIOUS_PROMPT_VERSION)
        }
        matching = next(
            (
                run
                for run in runs
                if run.cache_key in old_keys
                and run.status in {"queued", "preparing", "request_sent", "received", "succeeded"}
            ),
            None,
        )
    if matching:
        if matching.source_manifest != manifest:
            raise KnowledgeError("KNOWLEDGE_CACHE_INVALID", "知识图谱缓存与冻结来源不一致")
        old_job = db.get(Job, matching.job_id)
        if old_job and old_job.status == "cancelled" and not retry_failed:
            return old_job
        if old_job and matching.status == "succeeded" and matching.raw_response is not None:
            content = validate_extraction_response(matching)
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
                validate_extraction_response(matching)
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
        request_metadata={"request_contract": contract},
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


LOCAL_RECOVERY_VERSION = "knowledge-local-recovery-1"
QUOTE_RECOVERY_VERSION = "knowledge-local-recovery-2"


def _local_recovery_candidate(
    db: Session,
    run: KnowledgeExtractionRun,
    *,
    fresh: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    job = db.get(Job, run.job_id)
    if run.status != "failed" or job is None or job.status != "failed":
        raise KnowledgeError(
            "KNOWLEDGE_LOCAL_RECOVERY_UNAVAILABLE", "仅失败的完整知识响应可本机恢复"
        )
    if run.raw_response is None or (run.request_metadata or {}).get("response_complete") is False:
        raise KnowledgeError(
            "KNOWLEDGE_LOCAL_RECOVERY_UNAVAILABLE", "本任务没有完整响应可供本机恢复"
        )
    if fresh:
        _active_library_paper(db, run)
        revalidate_knowledge_sources(db, run.source_manifest)
    prompt_version = _request_contract(run)["prompt_version"]
    recover_quotes = run.error_code == "KNOWLEDGE_QUOTE_MISMATCH" and prompt_version in {
        LEGACY_PROMPT_VERSION,
        PREVIOUS_PROMPT_VERSION,
    }
    excluded_nodes: list[dict[str, Any]] = []
    if recover_quotes:
        raw, excluded_nodes, excluded_edges = isolate_unmatched_quotes(
            run.raw_response, run.source_manifest
        )
    else:
        raw, excluded_edges = isolate_invalid_knowledge_relations(
            run.raw_response, prompt_version=prompt_version
        )
    # All retained fields, node/edge relations, quotes and source IDs must pass again.
    content = validate_knowledge_response(raw, run.source_manifest, prompt_version=prompt_version)
    kept_nodes = (
        len(content["graph"]["nodes"]) - 1
    )  # Application-owned paper root is not model output.
    kept_edges = sum(e["type"] != "HAS_KNOWLEDGE" for e in content["graph"]["edges"])
    version = QUOTE_RECOVERY_VERSION if recover_quotes else LOCAL_RECOVERY_VERSION
    audit = {
        "version": version,
        "origin_run_id": run.id,
        "original_raw_sha256": text_hash(run.raw_response),
        "source_manifest_hash": digest(run.source_manifest),
        "rule_version": RELATION_RULE_VERSION,
        "excluded_edge_indices": [item["index"] for item in excluded_edges],
        "original_nodes": kept_nodes + len(excluded_nodes),
        "original_edges": kept_edges + len(excluded_edges),
        "kept_nodes": kept_nodes,
        "kept_edges": kept_edges,
        "retained_content_hash": digest(content),
    }
    if recover_quotes:
        audit["excluded_node_indices"] = [item["index"] for item in excluded_nodes]
    fingerprint = digest(audit)
    audit["preview_fingerprint"] = fingerprint
    warning = (
        f"本机部分恢复：已隔离 {len(excluded_nodes)} 个节点和 {len(excluded_edges)} 条关系。"
        "论文摘要未纳入本次恢复。"
        if recover_quotes
        else f"用户显式本机恢复：已隔离 {len(excluded_edges)} 条类型或方向不合法的关系；"
        "保留知识仍须按原文判断。"
    )
    content["coverage"] = {
        **content["coverage"],
        "status": "partial",
        "relation_coverage": "partial",
        "local_recovery": audit,
        "warnings": [*content["coverage"]["warnings"], warning],
    }
    preview = {
        "version": version,
        "available": True,
        "preview_fingerprint": fingerprint,
        "original_nodes": audit["original_nodes"],
        "original_edges": audit["original_edges"],
        "kept_nodes": kept_nodes,
        "kept_edges": kept_edges,
        "excluded_edges": [
            {
                **{
                    key: item[key]
                    for key in (
                        "index",
                        "path",
                        "code",
                        "relation_type",
                        "source_type",
                        "target_type",
                    )
                },
                "reason": item["message"],
            }
            for item in excluded_edges
        ],
        "published_version_id": None,
    }
    if recover_quotes:
        preview["excluded_nodes"] = excluded_nodes
    return preview, content


def local_recovery_preview(db: Session, run: KnowledgeExtractionRun) -> dict[str, Any]:
    """Read-only review: no raw/source text, no writes, publication, or provider access."""
    try:
        preview, _ = _local_recovery_candidate(db, run)
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return {
            "version": LOCAL_RECOVERY_VERSION,
            "available": False,
            "preview_fingerprint": None,
            "original_nodes": 0,
            "original_edges": 0,
            "kept_nodes": 0,
            "kept_edges": 0,
            "excluded_edges": [],
            "published_version_id": None,
            "blocking_diagnostic": diagnostic_for_raw(
                error,
                run.raw_response,
                request_sent=run.request_sent,
                prompt_version=stored_extraction_prompt_version(run.request_metadata or {}),
            ),
        }
    recovery = (run.request_metadata or {}).get("local_recovery")
    if (
        isinstance(recovery, dict)
        and recovery.get("preview_fingerprint") == preview["preview_fingerprint"]
    ):
        version_id = recovery.get("version_id")
        version = db.get(PaperKnowledgeVersion, version_id) if isinstance(version_id, str) else None
        if version is not None:
            try:
                validate_local_recovery_version(db, version)
            except (ValueError, KeyError, TypeError, IndexError) as error:
                preview.update(
                    available=False,
                    blocking_diagnostic=diagnostic_for_raw(
                        error,
                        run.raw_response,
                        request_sent=run.request_sent,
                        prompt_version=stored_extraction_prompt_version(run.request_metadata or {}),
                    ),
                )
                return preview
            preview["available"] = False
            preview["published_version_id"] = version.id
    return preview


def recover_knowledge_locally(
    db: Session,
    run: KnowledgeExtractionRun,
    preview_fingerprint: str,
) -> dict[str, Any]:
    """Publish one reviewed partial version; the original failed task is never rewritten."""
    preview, content = _local_recovery_candidate(db, run)
    if preview["preview_fingerprint"] != preview_fingerprint:
        raise KnowledgeError(
            "KNOWLEDGE_LOCAL_RECOVERY_STALE", "本机恢复预览已变化，请重新检查后确认"
        )
    recovery = (run.request_metadata or {}).get("local_recovery")
    existing = None
    if isinstance(recovery, dict) and recovery.get("preview_fingerprint") == preview_fingerprint:
        identity = recovery.get("version_id")
        existing = db.get(PaperKnowledgeVersion, identity) if isinstance(identity, str) else None
    if existing is not None:
        validate_local_recovery_version(db, existing)
        version = existing  # Replay must not move current_version_id back over a later version.
    else:
        select_as_current = True
        if preview["version"] == QUOTE_RECOVERY_VERSION:
            library_paper = _active_library_paper(db, run)
            current = (
                db.get(PaperKnowledgeVersion, library_paper.current_version_id)
                if (library_paper.current_version_id)
                else None
            )
            if current is not None and current.evidence_status == "grounded":
                select_as_current = (
                    current.created_at < run.created_at
                    and current.content_json.get("coverage", {}).get("status") == "partial"
                )
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
            job_id=run.job_id,
            prompt_version=_request_contract(run)["prompt_version"],
            schema_version=SCHEMA_VERSION,
            select_as_current=select_as_current,
        )
        run.request_metadata = {
            **run.request_metadata,
            "local_recovery": {
                "version": preview["version"],
                "preview_fingerprint": preview_fingerprint,
                "version_id": version.id,
                "content_hash": digest(content),
                "original_raw_sha256": text_hash(run.raw_response or ""),
            },
        }
    preview.update(available=False, published_version_id=version.id)
    return {
        "version_id": version.id,
        "library_paper_id": version.library_paper_id,
        "status": "partial",
        "local_recovery": preview,
    }


def validate_local_recovery_version(
    db: Session,
    version: PaperKnowledgeVersion,
    *,
    fresh: bool = True,
) -> None:
    """Reconstruct from immutable raw and the isolation plan, then run every validator."""
    audit = version.content_json.get("coverage", {}).get("local_recovery")
    if audit is None:
        return
    if not isinstance(audit, dict) or audit.get("version") not in {
        LOCAL_RECOVERY_VERSION,
        QUOTE_RECOVERY_VERSION,
    }:
        raise KnowledgeError("KNOWLEDGE_CHECKPOINT_INVALID", "本机恢复审计版本无效")
    identity = audit.get("origin_run_id")
    run = db.get(KnowledgeExtractionRun, identity) if isinstance(identity, str) else None
    if run is None or run.raw_response is None:
        raise KnowledgeError("KNOWLEDGE_CHECKPOINT_INVALID", "本机恢复缺少原始完整响应")
    if (
        text_hash(run.raw_response) != audit.get("original_raw_sha256")
        or digest(run.source_manifest) != audit.get("source_manifest_hash")
        or run.source_manifest != version.source_snapshot_json
        or run.library_paper_id != version.library_paper_id
        or version.source_paper_id != run.paper_id
    ):
        raise KnowledgeError("KNOWLEDGE_CHECKPOINT_INVALID", "本机恢复原始响应或来源审计不一致")
    _, content = _local_recovery_candidate(db, run, fresh=fresh)
    if content != version.content_json:
        raise KnowledgeError(
            "KNOWLEDGE_CHECKPOINT_INVALID", "本机恢复知识与原始响应及隔离审核不一致"
        )


def _capacity_preflight(
    provider: Provider,
    manifest: dict[str, Any],
    policy: LibrarySettings,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = contract or knowledge_contract()
    prompt, schema = contract["prompt"], contract["schema"]
    capabilities = getattr(provider, "capabilities", None)
    model_input = knowledge_model_input(
        manifest, contract["prompt_version"], contract["relation_rules"]
    )
    serialized = json.dumps(
        {"prompt": prompt, "data": model_input, "schema": schema}, ensure_ascii=False
    )
    estimate = len(serialized.encode())
    token_estimate = estimate_knowledge_input_tokens(prompt, model_input, schema)
    context = getattr(capabilities, "context_window", None)
    output = getattr(capabilities, "max_output_tokens", None)
    if policy.max_input_tokens is not None and token_estimate > policy.max_input_tokens:
        raise KnowledgeError(
            "KNOWLEDGE_INPUT_BUDGET_EXCEEDED",
            f"完整正文估算 {token_estimate} Token，超过知识库单次输入预算 "
            f"{policy.max_input_tokens}；请调高预算或选择无上限后显式重试，未截断或发送",
        )
    minimum_output = MINIMUM_KNOWLEDGE_OUTPUT_TOKENS
    if policy.max_output_tokens is not None and policy.max_output_tokens < minimum_output:
        raise KnowledgeError("KNOWLEDGE_CAPACITY_INSUFFICIENT", "知识库输出预算不足以构建知识图谱")
    if context and token_estimate + minimum_output + 512 > context:
        raise KnowledgeError(
            "KNOWLEDGE_CAPACITY_INSUFFICIENT", "完整正文超出当前模型容量；未截断或发送"
        )
    if output and output < minimum_output:
        raise KnowledgeError(
            "KNOWLEDGE_CAPACITY_INSUFFICIENT", "当前模型输出容量不足以构建知识图谱"
        )
    build = getattr(provider, "_build_body", None)
    if build:
        try:
            build(prompt, model_input, schema)
        except ProviderError as error:
            if error.category == "context_limit":
                raise KnowledgeError(
                    "KNOWLEDGE_CAPACITY_INSUFFICIENT",
                    "完整正文超出当前模型容量；未截断或发送",
                ) from None
            raise
        metadata = getattr(provider, "request_metadata", {})
        actual_estimate = metadata.get("input_token_estimate")
        if type(actual_estimate) is int:
            token_estimate = actual_estimate
            if policy.max_input_tokens is not None and token_estimate > policy.max_input_tokens:
                raise KnowledgeError(
                    "KNOWLEDGE_INPUT_BUDGET_EXCEEDED",
                    f"完整请求估算 {token_estimate} Token，超过知识库单次输入预算 "
                    f"{policy.max_input_tokens}；请调高预算或选择无上限后显式重试，未截断或发送",
                )
            if context and token_estimate + minimum_output + 512 > context:
                raise KnowledgeError(
                    "KNOWLEDGE_CAPACITY_INSUFFICIENT",
                    "完整请求超出当前模型容量；未截断或发送",
                )
        actual_limit = metadata.get("output_limit")
        if actual_limit and actual_limit < minimum_output:
            raise KnowledgeError(
                "KNOWLEDGE_CAPACITY_INSUFFICIENT", "完整正文占用后模型输出容量不足"
            )
    return {
        "input_byte_estimate": estimate,
        "input_token_estimate": token_estimate,
        "input_estimate_method": "text-character-estimate-1",
        "minimum_output_tokens": minimum_output,
        "context_window": context,
        "max_output_tokens": output,
    }


def _publish(db: Session, job: Job, run: KnowledgeExtractionRun) -> None:
    _active_library_paper(db, run)
    revalidate_knowledge_sources(db, run.source_manifest)
    content = validate_extraction_response(run)
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
        prompt_version=_request_contract(run)["prompt_version"],
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


def _require_extraction_authorization(job: Job, policy: LibrarySettings) -> None:
    payload = job.payload or {}
    if payload.get("automatic_revoked") or (
        payload.get("automatic") and not (policy.allow_network and policy.auto_collect)
    ):
        raise KnowledgeError("KNOWLEDGE_POLICY_REVOKED", "自动构建的网络授权已撤销")


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
            contract = _request_contract(run)
            policy = LibrarySettings.model_validate(run.policy_json)
            current_policy = LibrarySettings.model_validate(ensure_library(db).settings_json)
            policy = _effective_policy(current_policy, policy)
            _require_extraction_authorization(job, current_policy)
        if active is None:
            active = from_snapshot(snapshot, data_dir, True)
        if hasattr(active, "task_output_budget"):
            active.task_output_budget = policy.max_output_tokens
        prepare = getattr(active, "prepare", None)
        if prepare:
            await wait_for_model(prepare())
        preflight = _capacity_preflight(active, manifest, policy, contract)
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
            _require_extraction_authorization(job, current_policy)
            policy = _effective_policy(current_policy, policy)
            if hasattr(active, "task_output_budget"):
                active.task_output_budget = policy.max_output_tokens
            preflight = _capacity_preflight(active, manifest, policy, contract)
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
                **run.request_metadata,
                "capacity": preflight,
                "prompt_version": contract["prompt_version"],
                "schema_version": SCHEMA_VERSION,
                "provider": getattr(active, "request_metadata", {}),
            }
            job.status, job.stage, job.updated_at = "running", "generating", now()
        sent_here = True
        raw = await wait_for_model(
            active.complete(
                contract["prompt"],
                knowledge_model_input(
                    manifest, contract["prompt_version"], contract["relation_rules"]
                ),
                contract["schema"],
            )
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
                "response_complete": True,
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
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            run = db.scalar(
                select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
            )
            if run and run.status != "succeeded":
                metadata = deepcopy(getattr(active, "request_metadata", {})) if active else {}
                diagnostic = diagnostic_for_raw(
                    error,
                    run.raw_response,
                    request_sent=run.request_sent,
                    provider_metadata=metadata,
                    prompt_version=stored_extraction_prompt_version(run.request_metadata or {}),
                )
                code = diagnostic["code"]
                run.request_metadata = {
                    **run.request_metadata,
                    **({"provider": metadata} if active else {}),
                    "response_complete": run.raw_response is not None,
                    "knowledge_diagnostic": diagnostic,
                }
                run.status, run.error_code, run.updated_at = (
                    "cancelled" if job and job.status == "cancelled" else "failed",
                    code,
                    now(),
                )
                if sent_here and active:
                    run.usage_json = {**run.usage_json, **_provider_usage(active)}
                    partial = getattr(active, "partial_output", None)
                    if partial and run.raw_response is None:
                        run.request_metadata = {**run.request_metadata, "partial_output": partial}
                if job and job.status != "cancelled":
                    job.result = {**(job.result or {}), "knowledge_diagnostic": diagnostic}
                    job.status, job.stage, job.error, job.updated_at = (
                        "failed",
                        "failed",
                        code,
                        now(),
                    )
        if isinstance(error, asyncio.CancelledError):
            raise
