"""Resumable section-level v3 extraction; old P01/P02 remains an explicit baseline."""

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.extraction import PROMPT_DIR, call_model, mark_run, reusable_model_run, stage
from researchgraph.extraction_repair import validate_or_repair, validation_message
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeOperation, ModelRun, Section
from researchgraph.knowledge_store import KnowledgeStore, digest, text_hash
from researchgraph.models import AttachmentRevision, Chunk, Job, Paper, now
from researchgraph.providers import ConfiguredProvider, ProviderError, provider_for
from researchgraph.unified_contracts import KnowledgeExtractionBatch

LEGACY_PROMPT = "P02_unified_section_extract"
PROMPT = "P02_unified_section_extract_v3_2"


def resolve(value: Any, aliases: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [resolve(v, aliases) for v in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == "evidence_ids":
                if not set(item) <= aliases.keys():
                    raise ValueError("UNKNOWN_EVIDENCE：模型引用了本批之外的证据编号")
                result[key] = [aliases[i] for i in item]
            else:
                result[key] = resolve(item, aliases)
        return result
    return value


def plan_sections(
    spans: list[EvidenceSpan],
    *,
    legacy: bool = False,
    budget: int = 12000,
    max_evidence: int | None = None,
) -> list[list[dict[str, str]]]:
    """Pack adjacent paragraphs without treating every fallback page as a chapter.

    Evidence IDs and text remain intact. A large paragraph is never silently cut.
    The legacy planner is only for recovering an existing immutable task.
    """
    groups: list[list[dict[str, str]]] = []
    for span in spans:
        if (
            not groups
            or (max_evidence is not None and len(groups[-1]) >= max_evidence)
            or (legacy and groups[-1][0]["section"] != span.section_id)
            or sum(len(s["text"]) for s in groups[-1]) + len(span.quote)
            > (6000 if legacy else budget)
        ):
            groups.append([])
        groups[-1].append({"id": span.id, "text": span.quote, "section": span.section_id})
    return groups


def split_group(group: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    """Balance source characters while retaining every complete evidence span."""
    target = sum(len(e["text"]) for e in group) / 2
    prefix = 0
    candidates = []
    for i, entry in enumerate(group[:-1], 1):
        prefix += len(entry["text"])
        candidates.append((abs(prefix - target), i))
    middle = min(candidates)[1]
    return [group[:middle], group[middle:]]


async def run_unified_extraction(engine: Engine, job_id: str, *, reading: bool = False) -> None:
    from researchgraph.reading_contracts import KnowledgeExtractionBatch as ReadingBatch

    schema_type = ReadingBatch if reading else KnowledgeExtractionBatch
    operation_prefix = "reading-extract" if reading else "unified"
    if reading:
        stage(engine, job_id, "indexing")
    with Session(engine, expire_on_commit=False) as session, session.begin():
        job = session.get(Job, job_id)
        assert job and job.payload
        payload = dict(job.payload)
        version_id = payload["document_version_id"]
        version = session.get(AttachmentRevision, version_id)
        assert version
        paper = session.get(Paper, version.paper_id)
        assert paper
        paper_id, title = paper.id, paper.title
        KnowledgeStore(session).ensure_document(version_id)
        spans = list(
            session.scalars(
                select(EvidenceSpan)
                .join(Chunk, Chunk.id == EvidenceSpan.paragraph_id)
                .where(EvidenceSpan.document_version_id == version_id)
                .order_by(EvidenceSpan.page_index, Chunk.block_index, EvidenceSpan.start_offset)
            )
        )
        sections = {
            s.id: s.title
            for s in session.scalars(
                select(Section).where(Section.document_version_id == version_id)
            )
        }
        previous_result = dict(job.result or {})
    if not spans:
        raise ValueError("该文献没有可用原文证据")
    if payload.get("model_snapshot"):
        from researchgraph.model_settings import from_snapshot

        provider = from_snapshot(
            payload["model_snapshot"],
            Path(str(engine.url.database)).parent,
            payload["allow_network"],
        )
    else:
        provider = provider_for(payload["provider"], payload["allow_network"])
    if isinstance(provider, ConfiguredProvider):
        await provider.prepare()
    if reading and payload.get("reading_only"):
        from researchgraph.reading_pipeline import finish_reading

        await finish_reading(engine, job_id, provider)
        return
    legacy = bool(previous_result.get("batches")) and not payload.get("unified_plan")
    plan = payload.get("unified_plan")
    prompt_name = (
        plan.get("prompt_name", LEGACY_PROMPT) if plan else LEGACY_PROMPT if legacy else PROMPT
    )
    if reading:
        prompt_name = "P02_reading_extract"
    if prompt_name not in {PROMPT, LEGACY_PROMPT, "P02_reading_extract"}:
        raise ValueError("抽取计划使用未知 Prompt 版本，拒绝继续")
    limit = getattr(getattr(provider, "capabilities", None), "max_output_tokens", None)
    base_budget = 6000 if reading else 8000 if prompt_name == PROMPT else 12000
    budget = min(base_budget, max(1500, limit)) if limit else base_budget
    groups = plan_sections(
        spans,
        legacy=legacy,
        budget=budget,
        max_evidence=48 if reading else 64 if prompt_name == PROMPT else None,
    )
    config = digest(
        {
            "document_version_id": version_id,
            "input": groups,
            "model": provider.model,
            "provider": provider.name,
            "endpoint": getattr(provider, "base_url", "offline"),
            "parameters": getattr(provider, "parameters", {}),
            "schema": schema_type.model_json_schema(),
            "prompt": text_hash((PROMPT_DIR / (prompt_name + ".md")).read_text(encoding="utf-8")),
            "planner": "reading-adjacent-6000-48-v1"
            if reading
            else "section-6000-v1"
            if legacy
            else "adjacent-8000-64-v3"
            if prompt_name == PROMPT
            else "adjacent-12000-v2",
        }
    )
    signature = digest(
        {
            "provider": provider.name,
            "model": provider.model,
            "endpoint": getattr(provider, "base_url", "offline"),
            "parameters": getattr(provider, "parameters", {}),
            "schema": schema_type.model_json_schema(),
            "prompt": text_hash((PROMPT_DIR / (prompt_name + ".md")).read_text(encoding="utf-8")),
        }
    )
    states: list[dict[str, Any]]
    if plan:
        if plan.get("signature", signature) != signature:
            raise ValueError("模型、Prompt 或 Schema 已变化；请创建新任务，旧批次仍然保留")
        config = plan["config"]
        by_id = {s.id: {"id": s.id, "text": s.quote, "section": s.section_id} for s in spans}
        groups = [[by_id[eid] for eid in leaf["ids"]] for leaf in plan["leaves"]]
        states = [dict(s) for s in plan["leaves"]]
        if any(digest(g) != s["chunk_id"] for g, s in zip(groups, states, strict=True)):
            raise ValueError("原文证据已改变，无法继续旧抽取计划")
    else:
        states = [
            {
                "index": i,
                "key": str(i),
                "depth": 0,
                "status": "pending",
                "ids": [e["id"] for e in g],
                "chunk_id": digest(g),
            }
            for i, g in enumerate(groups)
        ]
        if legacy:
            # Adopt a failed old job without calling already committed page batches.
            for state, old in zip(states, previous_result["batches"], strict=True):
                if (
                    old.get("error_code") in {"output_limit", "context_limit"}
                    and len(state["ids"]) > 1
                ):
                    state["split_required"] = True
    saved: set[str] = set()
    batch_warnings: list[str] = []
    with Session(engine) as session:
        # Split markers are shared by identical runs; no successful child is recalled.
        i = 0
        while i < len(states):
            split = session.get(
                KnowledgeOperation, f"{operation_prefix}:{config}:{states[i]['key']}:split"
            )
            if split:
                planned_children = [dict(c) for c in split.response["children"]]
                evidence = {e["id"]: e for e in groups[i]}
                groups[i : i + 1] = [[evidence[eid] for eid in c["ids"]] for c in planned_children]
                states[i : i + 1] = planned_children
            else:
                i += 1
        for i, state in enumerate(states):
            state["index"] = i
            operation = session.get(
                KnowledgeOperation, f"{operation_prefix}:{config}:{state['key']}"
            )
            if operation:
                states[i]["status"] = "succeeded"
                saved.update(operation.response["node_ids"])
                batch_warnings.extend(operation.response.get("warnings", []))
            elif (
                state.get("error_code") == "timeout" and state["depth"] == 0 and len(groups[i]) > 1
            ):
                # Old clients already retried the same request three times. Only
                # adopt that evidence when repeated timeout attempts are recorded.
                for failed in session.scalars(
                    select(ModelRun).where(ModelRun.job_id == job_id, ModelRun.status == "failed")
                ):
                    aliases = failed.parameters.get("input_manifest", {}).get(
                        "evidence_aliases", {}
                    )
                    attempts = failed.parameters.get("attempts", [])
                    if (
                        set(aliases.values()) == set(state["ids"])
                        and len(attempts) >= 3
                        and all(
                            a.get("status") == "timeout"
                            and a.get("request", {}).get("timeout_phase")
                            in {None, "response_headers", "response_body", "total"}
                            for a in attempts
                        )
                    ):
                        state["split_required"] = "timeout"
                        break

    def progress(
        index: int | None = None, status: str | None = None, error: str | None = None
    ) -> None:
        if index is not None:
            states[index].update(status=status, error=error)
            if status == "succeeded":
                states[index].pop("error_code", None)
                states[index].pop("retryable", None)
        with Session(engine) as session, session.begin():
            current = session.get(Job, job_id)
            assert current
            runs = list(session.scalars(select(ModelRun).where(ModelRun.job_id == job_id)))
            usage: dict[str, int] = {}
            for run in runs:
                for key, value in run.parameters.get("usage", {}).items():
                    if isinstance(value, int):
                        usage[key] = usage.get(key, 0) + value
            current.payload = {
                **(current.payload or {}),
                "unified_plan": {
                    "config": config,
                    "signature": signature,
                    "prompt_name": prompt_name,
                    "leaves": [dict(s) for s in states],
                },
            }
            current.result = {
                **(current.result or {}),
                "pipeline": "paper-reading-v1" if reading else "unified-v3",
                "document_version_id": version_id,
                "total_batches": str(len(groups)),
                "completed_batches": str(sum(s["status"] == "succeeded" for s in states)),
                "knowledge_count": str(len(saved)),
                "batches": [{k: v for k, v in s.items() if k != "ids"} for s in states],
                "coverage_gaps": list(dict.fromkeys(batch_warnings)) if reading else [],
                "usage": usage,
                "model_calls": sum(len(r.parameters.get("attempts", [{}])) for r in runs),
                "model": provider.model,
                "cost": None,
                "cost_status": "provider_not_reported",
            }
            current.updated_at = now()

    progress()
    index = 0
    while index < len(groups):
        group = groups[index]
        if states[index]["status"] == "succeeded":
            index += 1
            continue
        stage(engine, job_id, "extracting")
        progress(index, "running")
        aliases = {f"ev{i + 1:04d}": e["id"] for i, e in enumerate(group)}
        manifest = {
            "evidence_aliases": aliases,
            "pipeline": "paper-reading-v1" if reading else "unified-v3",
            "schema_hash": digest(schema_type.model_json_schema()),
        }
        data = {
            "document_version_id": version_id,
            "chunk_id": digest(group),
            "paper_metadata": {"title": title},
            "section": " / ".join(dict.fromkeys(sections[e["section"]] for e in group)),
            "domain_vocabulary": [],
            "max_items_hint": min(16, max(4, (sum(len(e["text"]) for e in group) + 749) // 750))
            if prompt_name == PROMPT
            else states[index].get("max_items_hint", 16),
            "allowed_evidence": [
                {"id": alias, "text": entry["text"]}
                for alias, entry in zip(aliases, group, strict=True)
            ],
        }
        if reading:
            data = {
                "contract_version": "reading-extraction-1.0",
                "document_version_id": version_id,
                "chunk_id": digest(group),
                "paper_type": payload.get("paper_type", "unknown"),
                "section": data["section"],
                "vocabulary": [],
                "max_items_hint": data["max_items_hint"],
                "allowed_evidence": [
                    {
                        **e,
                        "context_group": group[i]["section"],
                        "context_complete": not any(
                            w in e["text"].lower() for w in ["table", "表格"]
                        ),
                    }
                    for i, e in enumerate(data["allowed_evidence"])
                ],
            }
        run_id = None
        try:
            split_required = states[index].pop("split_required", False)
            if split_required:
                category = "timeout" if split_required == "timeout" else "output_limit"
                raise ProviderError(
                    category,
                    "继续拆分上次失败的未完成批次",
                    timeout_phase="total" if category == "timeout" else None,
                )
            cached = reusable_model_run(
                engine, job_id, provider, prompt_name, data, manifest, include_invalid=True
            )
            if cached:
                run_id, raw = cached
            else:
                run_id, raw = await call_model(
                    engine,
                    job_id,
                    version_id,
                    provider,
                    prompt_name,
                    data,
                    schema_type.model_json_schema(),
                    manifest,
                    adaptive_timeout=True,
                )
            validated: Any
            if reading:
                from researchgraph.reading_validation import validate_batch

                validated, quarantined = validate_batch(raw, set(aliases))
                if quarantined:
                    with Session(engine) as session, session.begin():
                        run = session.get(ModelRun, run_id)
                        assert run
                        run.parameters = {**run.parameters, "quarantined_associations": quarantined}
            else:
                run_id, validated = await validate_or_repair(
                    engine, job_id, provider, run_id, raw, data, manifest
                )
            candidate = resolve(validated.model_dump(mode="json"), aliases)
            stage(engine, job_id, "saving")
            with Session(engine) as session, session.begin():
                current = session.get(Job, job_id)
                if not current or current.status != "running":
                    raise ValueError("任务已取消，已收到结果保留供恢复")
                store = KnowledgeStore(session)
                apply_batch = store.reading().apply_candidates if reading else store.apply_unified
                response = apply_batch(
                    candidate=candidate,
                    version_id=version_id,
                    paper_id=paper_id,
                    chunk_id=data["chunk_id"],
                    allowed=set(aliases.values()),
                    run_id=run_id,
                    key=f"{operation_prefix}:{config}:{states[index]['key']}",
                )
                saved.update(response["node_ids"])
                batch_warnings.extend(response.get("warnings", []))
                # Operation, ModelRun and progress are committed together for successful batches.
                run = session.get(ModelRun, run_id)
                assert run
                run.status, run.finished_at = "succeeded", now()
                run.error = None
                states[index]["status"] = "succeeded"
                current.result = {
                    **(current.result or {}),
                    "batches": list(states),
                    "completed_batches": str(sum(s["status"] == "succeeded" for s in states)),
                    "knowledge_count": str(len(saved)),
                }
            progress(index, "succeeded")
            index += 1
        except Exception as error:
            if run_id:
                # Cancellation can reuse the received response; invalid DTOs cannot.
                with Session(engine) as session:
                    current = session.get(Job, job_id)
                    cancelled = current is None or current.status != "running"
                    recorded = session.get(ModelRun, run_id)
                    received = recorded is not None and recorded.status == "received"
                if not cancelled and received:
                    mark_run(
                        engine,
                        run_id,
                        "validation_failed",
                        validation_message(error),
                    )
            category = getattr(error, "category", "validation" if run_id else "unknown")
            timeout_split = category == "timeout" and getattr(error, "timeout_phase", None) in {
                "response_headers",
                "response_body",
                "total",
            }
            if category in {"output_limit", "context_limit"} or timeout_split:
                state = states[index]
                if len(group) > 1 and state["depth"] < (1 if timeout_split else 3):
                    children = split_group(group)
                    replacements = [
                        {
                            "key": f"{state['key']}.{part}",
                            "depth": state["depth"] + 1,
                            "status": "pending",
                            "ids": [e["id"] for e in child],
                            "chunk_id": digest(child),
                            "split_reason": category,
                            "source_characters": sum(len(e["text"]) for e in child),
                            "max_items_hint": min(
                                16, max(4, (sum(len(e["text"]) for e in child) + 749) // 750)
                            ),
                        }
                        for part, child in enumerate(children)
                    ]
                    with Session(engine) as session, session.begin():
                        marker = f"{operation_prefix}:{config}:{state['key']}:split"
                        if not session.get(KnowledgeOperation, marker):
                            session.add(
                                KnowledgeOperation(
                                    key=marker,
                                    request_hash=digest(group),
                                    response={"children": replacements},
                                )
                            )
                    groups[index : index + 1] = children
                    states[index : index + 1] = replacements
                    with Session(engine) as session:
                        for child in replacements:
                            operation = session.get(
                                KnowledgeOperation, f"{operation_prefix}:{config}:{child['key']}"
                            )
                            if operation:
                                child["status"] = "succeeded"
                                saved.update(operation.response["node_ids"])
                    for i, s in enumerate(states):
                        s["index"] = i
                    progress()
                    continue
                # A bounded split cannot repair a single span or provider reasoning exhaustion.
                error = ProviderError(
                    category,
                    "缩小后的批次仍响应超时，本次已停止自动重发；已保存批次保留，可稍后继续。超时请求的供应商费用未知"
                    if timeout_split
                    else "模型持续截断：已达到最小证据块或 3 层拆分上限；"
                    "已保存批次保留，请检查模型服务的输出/推理预算",
                )
            states[index].update(
                error_code=category,
                retryable=category in {"timeout", "network", "rate_limit", "server"},
            )
            message = validation_message(error)
            progress(index, "failed", message)
            raise ValueError(message) from None
    progress()
    if reading:
        from researchgraph.reading_pipeline import finish_reading

        await finish_reading(engine, job_id, provider)
    else:
        with Session(engine) as session, session.begin():
            job = session.get(Job, job_id)
            if job and job.status == "running":
                job.status, job.stage, job.updated_at = "succeeded", "saving", now()
