"""P01/P02 orchestration. All graph mutations are delegated to KnowledgeStore."""

import asyncio
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.extraction_normalization import reusable_invalid_output
from researchgraph.knowledge_contracts import ExtractionBatch, PaperOutline
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeOperation, ModelRun, Section
from researchgraph.knowledge_store import DOMAIN_VERSION, KnowledgeStore, digest, text_hash
from researchgraph.models import AttachmentRevision, Chunk, Job, now
from researchgraph.providers import Provider, ProviderError, provider_for

PROMPT_DIR = Path(__file__).parent / "prompts"


async def cancellable_call(
    engine: Engine,
    job_id: str,
    provider: Provider,
    prompt: str,
    data: dict[str, Any],
    schema: dict[str, Any],
) -> str:
    task = asyncio.create_task(provider.complete(prompt, data, schema))
    started, last_progress = time.monotonic(), 0.0
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.15)
            with Session(engine) as session:
                job = session.get(Job, job_id)
                if job is None or job.status != "running":
                    raise ValueError("任务已取消，模型结果不会写入知识")
            elapsed = time.monotonic() - started
            if elapsed - last_progress >= 2 and hasattr(provider, "request_metadata"):
                meta = provider.request_metadata
                activity = {
                    key: meta[key]
                    for key in (
                        "first_byte_seconds",
                        "last_byte_seconds",
                        "content_characters",
                        "reasoning_characters",
                        "total_timeout_seconds",
                    )
                    if key in meta
                }
                activity["elapsed_seconds"] = round(elapsed, 1)
                with Session(engine) as session, session.begin():
                    current = session.get(Job, job_id)
                    if current and current.status == "running":
                        current.result = {**(current.result or {}), "model_activity": activity}
                last_progress = elapsed
        return await task
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def stage(engine: Engine, job_id: str, value: str) -> None:
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if job is None or job.status != "running":
            raise ValueError("任务已取消，不再写入知识")
        job.stage, job.updated_at = value, now()


async def call_model(
    engine: Engine,
    job_id: str,
    version_id: str,
    provider: Provider,
    prompt_name: str,
    data: dict[str, Any],
    schema: dict[str, Any],
    input_manifest: dict[str, Any] | None = None,
    *,
    adaptive_timeout: bool = False,
    max_attempts: int = 3,
) -> tuple[str, str]:
    if not 1 <= max_attempts <= 3:
        raise ValueError("模型请求次数必须介于 1 与 3")
    prompt = (PROMPT_DIR / (prompt_name + ".md")).read_text(encoding="utf-8")
    run_id = str(uuid4())
    with Session(engine) as session, session.begin():
        session.add(
            ModelRun(
                id=run_id,
                job_id=job_id,
                document_version_id=version_id,
                provider=provider.name,
                model=provider.model,
                prompt_name=prompt_name,
                prompt_hash=text_hash(prompt),
                schema_version=(
                    "reading-1.0"
                    if prompt_name.startswith(("P02_reading", "P12_reading", "P13_reading"))
                    else "unified-v3.1"
                    if schema.get("title")
                    in {"KnowledgeExtractionBatch", "TranslationRepair", "LocalLinkRepair"}
                    else DOMAIN_VERSION
                ),
                input_hash=digest(data),
                parameters={
                    **getattr(provider, "parameters", {"temperature": 0, "timeout_seconds": 35}),
                    **({"input_manifest": input_manifest} if input_manifest else {}),
                },
                status="running",
                created_at=now(),
            )
        )
    retryable = {"timeout", "network", "rate_limit", "server"}
    attempts: list[dict[str, Any]] = []
    started = time.monotonic()

    def record_attempt(category: str) -> None:
        attempts[-1].update(
            status=category,
            finished_at=now(),
            usage=dict(getattr(provider, "usage", {})),
            request=dict(getattr(provider, "request_metadata", {})),
        )
        usage: dict[str, int] = {}
        for attempt in attempts:
            for key, value in attempt.get("usage", {}).items():
                usage[key] = usage.get(key, 0) + value
        with Session(engine) as session, session.begin():
            recorded = session.get(ModelRun, run_id)
            assert recorded
            recorded.parameters = {
                **recorded.parameters,
                "attempts": list(attempts),
                "duration_seconds": round(time.monotonic() - started, 3),
                "usage": usage,
            }
            current = session.get(Job, job_id)
            if current:
                current.result = {**(current.result or {}), "model_activity": None}

    try:
        raw = ""
        for attempt in range(max_attempts):
            attempts.append({"attempt": attempt + 1, "started_at": now()})
            try:
                raw = await asyncio.wait_for(
                    cancellable_call(engine, job_id, provider, prompt, data, schema),
                    timeout=getattr(
                        provider,
                        "total_timeout",
                        min(getattr(provider, "parameters", {}).get("timeout_seconds", 30), 180),
                    )
                    + 5,
                )
                record_attempt("received")
                break
            except ProviderError as error:
                record_attempt(error.category)
                if (
                    adaptive_timeout
                    and error.category == "timeout"
                    and error.timeout_phase in {"response_headers", "response_body", "total"}
                ):
                    raise
                if error.category not in retryable or attempt == max_attempts - 1:
                    raise
                await asyncio.sleep(min(error.retry_after or 2**attempt, 8))
            except TimeoutError:
                if hasattr(provider, "request_metadata"):
                    provider.request_metadata["timeout_phase"] = "total"
                record_attempt("timeout")
                if adaptive_timeout:
                    raise ProviderError(
                        "timeout",
                        "模型总请求达到时限，已停止本次请求并保留已保存结果",
                        timeout_phase="total",
                    ) from None
                if attempt == max_attempts - 1:
                    raise ProviderError(
                        "timeout", f"模型请求超时，共尝试 {max_attempts} 次"
                    ) from None
                await asyncio.sleep(min(2**attempt, 8))
        if len(raw) > 2_000_000:
            raise ValueError("模型响应超过大小限制")
        with Session(engine) as session, session.begin():
            run = session.get(ModelRun, run_id)
            assert run
            run.raw_output, run.status, run.finished_at = raw, "received", now()
        return run_id, raw
    except BaseException as error:
        with Session(engine) as session, session.begin():
            run = session.get(ModelRun, run_id)
            assert run
            run.status = "cancelled" if isinstance(error, asyncio.CancelledError) else "failed"
            run.error = f"{getattr(error, 'category', 'unknown')}: {error}"
            run.finished_at = now()
            run.raw_output = getattr(provider, "partial_output", None)
        if isinstance(error, ProviderError):
            raise ProviderError(
                error.category,
                f"{error}，"
                + (
                    "可从任务历史重试"
                    if error.category
                    in retryable | {"output_limit", "context_limit", "incomplete_stream"}
                    else "请检查设置或输出后启动新任务"
                ),
                timeout_phase=error.timeout_phase,
            ) from None
        if isinstance(error, TimeoutError):
            raise ValueError("模型调用超时，已重试 3 次，可从任务历史重试") from None
        raise


def mark_run(engine: Engine, run_id: str, status: str, error: str | None = None) -> None:
    with Session(engine) as session, session.begin():
        run = session.get(ModelRun, run_id)
        assert run
        run.status, run.error, run.finished_at = status, error, now()


def reusable_model_run(
    engine: Engine,
    job_id: str,
    provider: Provider,
    prompt_name: str,
    data: dict[str, Any],
    input_manifest: dict[str, Any] | None = None,
    *,
    include_invalid: bool = False,
    validator: Callable[[str], Any] | None = None,
) -> tuple[str, str] | None:
    """Reuse an already received identical model response after a retry."""
    prompt = (PROMPT_DIR / (prompt_name + ".md")).read_text(encoding="utf-8")
    expected_parameters = dict(
        getattr(provider, "parameters", {"temperature": 0, "timeout_seconds": 35})
    )
    if input_manifest:
        expected_parameters["input_manifest"] = input_manifest
    with Session(engine, expire_on_commit=False) as session:
        runs = session.scalars(
            select(ModelRun)
            .where(
                ModelRun.job_id == job_id,
                ModelRun.provider == provider.name,
                ModelRun.model == provider.model,
                ModelRun.prompt_name == prompt_name,
                ModelRun.prompt_hash == text_hash(prompt),
                ModelRun.input_hash == digest(data),
                ModelRun.schema_version
                == (
                    "reading-1.0"
                    if prompt_name.startswith(("P02_reading", "P12_reading", "P13_reading"))
                    else "unified-v3.1"
                    if prompt_name
                    in {
                        "P02_unified_section_extract",
                        "P02_unified_section_extract_v3_2",
                        "P04_label_translation_repair",
                        "P02_local_link_repair",
                    }
                    else DOMAIN_VERSION
                ),
                ModelRun.status.in_(
                    ["received", "succeeded", "validation_failed"]
                    if include_invalid
                    else ["received", "succeeded"]
                ),
            )
            .order_by(ModelRun.created_at.desc())
        ).all()
        # A validator may open its own read transaction. This engine uses BEGIN
        # IMMEDIATE, so release the lookup transaction before invoking callbacks.
        session.commit()
        for run in runs:
            if run.status == "validation_failed" and not (
                validator or prompt_name.startswith(("P02_reading", "P12_reading", "P13_reading"))
            ):
                if not reusable_invalid_output(run.raw_output or ""):
                    continue
            parameters = dict(run.parameters)
            for field in (
                "usage",
                "attempts",
                "duration_seconds",
                "normalization",
                "quarantined_associations",
                "reading_normalization",
                "reading_wire",
                "reading_envelope_normalization",
                "integration_normalization",
                "quarantined_integration_associations",
                "rejected_integration_duplicates",
                "integration_context_quarantine",
                "stage_validation",
            ):
                parameters.pop(field, None)
            if run.raw_output and parameters == expected_parameters:
                from researchgraph.reading_stage_validation import (
                    StageValidationError,
                    validate_stage,
                )

                try:
                    if validator:
                        validator(run.raw_output)
                    elif prompt_name.startswith(("P02_reading", "P12_reading", "P13_reading")):
                        validate_stage(
                            session,
                            "P02"
                            if prompt_name.startswith("P02")
                            else "P12"
                            if prompt_name.startswith("P12")
                            else "P13",
                            run.raw_output,
                            data,
                            input_manifest=input_manifest,
                        )
                except StageValidationError as error:
                    if error.response_invalid:
                        run.status, run.error, run.finished_at = (
                            "validation_failed",
                            str(error),
                            now(),
                        )
                    run.parameters = {
                        **run.parameters,
                        "stage_validation": error.audit(run.raw_output, digest(data)),
                    }
                    # A stale trusted input blocks this reuse; it does not rewrite
                    # the historical model outcome. Keep the reuse audit separate.
                    session.commit()
                    if not error.response_invalid:
                        raise
                    continue
                return run.id, run.raw_output
    return None


def resolve_evidence_aliases(value: Any, aliases: dict[str, str]) -> Any:
    """Resolve only declared evidence fields against a frozen, bijective input manifest."""

    def resolve(key: str) -> str:
        if key not in aliases:
            raise ValueError("模型引用了本批白名单之外的证据编号；未猜测或补全")
        return aliases[key]

    if isinstance(value, list):
        return [resolve_evidence_aliases(v, aliases) for v in value]
    if isinstance(value, dict):
        return {
            key: resolve(item)
            if key == "evidence_span_id"
            else [resolve(i) for i in item]
            if key == "evidence_span_ids"
            else resolve_evidence_aliases(item, aliases)
            for key, item in value.items()
        }
    return value


async def run_extraction(engine: Engine, job_id: str) -> None:
    with Session(engine) as dispatch_session:
        dispatch_job = dispatch_session.get(Job, job_id)
        unified = bool(
            dispatch_job
            and dispatch_job.payload
            and dispatch_job.payload.get("pipeline") == "unified-v3"
        )
    reading = bool(
        dispatch_job
        and dispatch_job.payload
        and dispatch_job.payload.get("pipeline") == "paper-reading-v1"
    )
    if unified or reading:
        from researchgraph.unified_extraction import run_unified_extraction

        await run_unified_extraction(engine, job_id, reading=reading)
        return
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        assert job and job.payload
        payload = job.payload
        version_id = payload["document_version_id"]
        version = session.get(AttachmentRevision, version_id)
        assert version
        paper_id = version.paper_id
        KnowledgeStore(session).ensure_document(version_id)
        spans = session.scalars(
            select(EvidenceSpan)
            .join(Chunk, Chunk.id == EvidenceSpan.paragraph_id)
            .where(EvidenceSpan.document_version_id == version_id)
            .order_by(EvidenceSpan.page_index, Chunk.block_index, EvidenceSpan.start_offset)
        ).all()
        sections = session.scalars(
            select(Section)
            .where(Section.document_version_id == version_id)
            .order_by(Section.ordinal)
        ).all()
        # P02 only receives citable EvidenceSpan IDs. Paragraph/section IDs belong to P01
        # and are not interchangeable with evidence, even when their text is identical.
        evidence_data = [{"id": s.id, "quote": s.quote} for s in spans]
        section_data = [
            {
                "id": s.id,
                "title": s.title,
                # P01 classifies a section from bounded context; P02 still sees every span.
                "paragraph_ids": list(
                    dict.fromkeys(e.paragraph_id for e in spans if e.section_id == s.id)
                )[:4],
                "context": "\n".join(e.quote for e in spans if e.section_id == s.id)[:1200],
            }
            for s in sections
            # A structural parent can have children but no directly citable text.
            # P01 classifies only sections with supplied evidence, not empty containers.
            if any(e.section_id == s.id for e in spans)
        ]
    if not spans:
        raise ValueError("该文献没有可提取文本，不能进行结构化抽取")
    if payload.get("model_snapshot"):
        from researchgraph.model_settings import from_snapshot

        provider = from_snapshot(
            payload["model_snapshot"],
            Path(str(engine.url.database)).parent,
            payload["allow_network"],
        )
    else:
        provider = provider_for(payload["provider"], payload["allow_network"])
    # Cache identity freezes source, schema, templates and model config. No accepted overwrite.
    prompt_hashes = [
        text_hash((PROMPT_DIR / (name + ".md")).read_text(encoding="utf-8"))
        for name in ("P01_paper_outline", "P02_extract_scientific_knowledge")
    ]
    config_hash = digest(
        {
            "version": version_id,
            "provider": provider.name,
            "model": provider.model,
            "endpoint": getattr(provider, "base_url", "offline"),
            "schema": DOMAIN_VERSION,
            "prompts": prompt_hashes,
            "parameters": getattr(provider, "parameters", {}),
            "evidence_input_hash": digest(evidence_data),
            "input_contract": "short-evidence-v1;batch-10000;outline-8",
        }
    )
    groups: list[list[dict[str, Any]]] = []
    for evidence in evidence_data:
        if not groups or sum(len(e["quote"]) for e in groups[-1]) + len(evidence["quote"]) > 10000:
            groups.append([])
        groups[-1].append(evidence)
    batch_states: list[dict[str, Any]] = []
    with Session(engine) as session:
        existing = session.get(Job, job_id)
        if existing and existing.result:
            batch_states = list(existing.result.get("batches", []))
    saved_states = {int(item.get("index", -1)): item for item in batch_states}
    batch_states = [
        {"index": index, "status": saved_states.get(index, {}).get("status", "pending")}
        for index in range(len(groups))
    ]
    # The operation row is the durable source of truth. Job progress can lag a
    # committed batch if the process exits between the two transactions.
    batch_operations: dict[int, dict[str, Any]] = {}
    counted_node_ids: set[str] = set()
    with Session(engine) as session:
        for index in range(len(groups)):
            operation = session.get(KnowledgeOperation, f"extraction:{config_hash}:{index}")
            if operation:
                batch_operations[index] = operation.response
                counted_node_ids.update(operation.response.get("node_ids", []))
                batch_states[index] = {"index": index, "status": "succeeded"}
            elif batch_states[index]["status"] == "succeeded":
                batch_states[index] = {"index": index, "status": "pending"}
    count = len(counted_node_ids)

    def record_batch(index: int, status: str, error: str | None = None) -> None:
        while len(batch_states) <= index:
            batch_states.append({"index": len(batch_states), "status": "pending"})
        state: dict[str, Any] = {"index": index, "status": status}
        if error:
            state["error"] = error
        batch_states[index] = state
        with Session(engine) as session, session.begin():
            current = session.get(Job, job_id)
            if current:
                current.result = {
                    **(current.result or {}),
                    "batches": batch_states,
                    "completed_batches": str(
                        sum(item.get("status") == "succeeded" for item in batch_states)
                    ),
                    "total_batches": str(len(groups)),
                    "knowledge_count": str(len(counted_node_ids)),
                }

    # P01 is also bounded; section references are never invented or used to suppress source text.
    for offset in range(0, len(section_data), 8):
        stage(engine, job_id, "outlining")
        section_group = section_data[offset : offset + 8]
        data: dict[str, Any] = {
            "paper_id": paper_id,
            "sections": section_group,
            "allowed_section_ids": [s["id"] for s in section_group],
            "allowed_paragraph_ids": sorted({p for s in section_group for p in s["paragraph_ids"]}),
        }
        cached_outline = reusable_model_run(engine, job_id, provider, "P01_paper_outline", data)
        if cached_outline:
            try:
                PaperOutline.model_validate_json(cached_outline[1])
            except ValueError:
                cached_outline = None
        if cached_outline:
            run_id, raw = cached_outline
        else:
            run_id, raw = await call_model(
                engine,
                job_id,
                version_id,
                provider,
                "P01_paper_outline",
                data,
                PaperOutline.model_json_schema(),
            )
        try:
            outline = PaperOutline.model_validate_json(raw)
            stage(engine, job_id, "checking")
            with Session(engine) as session, session.begin():
                current = session.get(Job, job_id)
                if current is None or current.status != "running":
                    raise ValueError("任务已取消，不再写入知识")
                KnowledgeStore(session).apply_outline(
                    version_id,
                    outline,
                    set(data["allowed_section_ids"]),
                    set(data["allowed_paragraph_ids"]),
                    run_id,
                )
            mark_run(engine, run_id, "succeeded")
        except BaseException:
            mark_run(engine, run_id, "validation_failed", "章节输出无效或任务已取消")
            raise
    for index, group in enumerate(groups):
        stage(engine, job_id, "extracting")
        operation_key = f"extraction:{config_hash}:{index}"
        if index in batch_operations:
            continue
        aliases = {f"ev{i + 1:04d}": e["id"] for i, e in enumerate(group)}
        data = {
            "paper_id": paper_id,
            "document_version_id": version_id,
            "schema_version": DOMAIN_VERSION,
            "domain_extension": {
                "required_condition_dimensions": ["task_type", "dataset", "metric"]
            },
            "evidence_texts": [
                {"id": alias, "quote": e["quote"]} for alias, e in zip(aliases, group, strict=True)
            ],
            "allowed_evidence_ids": list(aliases),
        }
        try:
            run_id, raw = await call_model(
                engine,
                job_id,
                version_id,
                provider,
                "P02_extract_scientific_knowledge",
                data,
                ExtractionBatch.model_json_schema(),
                {"evidence_aliases": aliases},
            )
        except Exception as error:
            record_batch(index, "failed", str(error))
            raise
        try:
            # Validate shape before resolving IDs; never silently repair model output.
            draft = ExtractionBatch.model_validate_json(raw).model_dump(mode="json")
            batch = resolve_evidence_aliases(draft, aliases)
            stage(engine, job_id, "saving")
            with Session(engine) as session, session.begin():
                current = session.get(Job, job_id)
                if current is None or current.status != "running":
                    raise ValueError("任务已取消，不再写入知识")
                response = KnowledgeStore(session).apply(
                    batch, version_id, set(aliases.values()), run_id, operation_key
                )
                batch_operations[index] = response
                counted_node_ids.update(response["node_ids"])
                count = len(counted_node_ids)
            record_batch(index, "succeeded")
            mark_run(engine, run_id, "succeeded")
        except BaseException as error:
            record_batch(index, "failed", str(error))
            mark_run(
                engine, run_id, "validation_failed", "抽取 Schema、证据或局部引用无效；本批未写入"
            )
            raise
    with Session(engine) as session, session.begin():
        current = session.get(Job, job_id)
        if current and current.status == "running":
            current.status, current.updated_at = "succeeded", now()
            current.result = {
                **(current.result or {}),
                "document_version_id": version_id,
                "knowledge_count": str(count),
                "provider": provider.name,
                "completed_batches": str(
                    sum(item.get("status") == "succeeded" for item in batch_states)
                ),
                "total_batches": str(len(groups)),
                "batches": batch_states,
            }
