"""P01/P02 orchestration. All graph mutations are delegated to KnowledgeStore."""

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.knowledge_contracts import ExtractionBatch, PaperOutline
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeOperation, ModelRun, Section
from researchgraph.knowledge_store import DOMAIN_VERSION, KnowledgeStore, digest, text_hash
from researchgraph.models import AttachmentRevision, Chunk, Job, now
from researchgraph.providers import Provider, provider_for

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
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.15)
            with Session(engine) as session:
                job = session.get(Job, job_id)
                if job is None or job.status != "running":
                    raise ValueError("任务已取消，模型结果不会写入知识")
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
) -> tuple[str, str]:
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
                schema_version=DOMAIN_VERSION,
                input_hash=digest(data),
                parameters={"temperature": 0, "timeout_seconds": 35},
                status="running",
                created_at=now(),
            )
        )
    try:
        raw = await asyncio.wait_for(
            cancellable_call(engine, job_id, provider, prompt, data, schema), timeout=35
        )
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
            run.error = (
                "模型调用超时" if isinstance(error, TimeoutError) else "模型调用失败或已中断"
            )
            run.finished_at = now()
        if isinstance(error, TimeoutError):
            raise ValueError("模型调用超时，可从任务历史重试") from None
        raise


def mark_run(engine: Engine, run_id: str, status: str, error: str | None = None) -> None:
    with Session(engine) as session, session.begin():
        run = session.get(ModelRun, run_id)
        assert run
        run.status, run.error, run.finished_at = status, error, now()


async def run_extraction(engine: Engine, job_id: str) -> None:
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
        evidence_data = [
            {
                "id": s.id,
                "quote": s.quote,
                "paragraph_id": s.paragraph_id,
                "section_id": s.section_id,
            }
            for s in spans
        ]
        section_data = [
            {
                "id": s.id,
                "title": s.title,
                "paragraph_ids": sorted({e.paragraph_id for e in spans if e.section_id == s.id}),
            }
            for s in sections
        ]
    if not spans:
        raise ValueError("该文献没有可提取文本，不能进行结构化抽取")
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
            "temperature": 0,
            "evidence_input_hash": digest(evidence_data),
        }
    )
    groups: list[list[dict[str, Any]]] = []
    for evidence in evidence_data:
        if not groups or sum(len(e["quote"]) for e in groups[-1]) + len(evidence["quote"]) > 16000:
            groups.append([])
        groups[-1].append(evidence)
    count = 0
    # P01 is also bounded; section references are never invented or used to suppress source text.
    for offset in range(0, len(section_data), 30):
        stage(engine, job_id, "outlining")
        section_group = section_data[offset : offset + 30]
        data: dict[str, Any] = {
            "paper_id": paper_id,
            "sections": section_group,
            "allowed_section_ids": [s["id"] for s in section_group],
            "allowed_paragraph_ids": sorted({p for s in section_group for p in s["paragraph_ids"]}),
        }
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
        with Session(engine) as session:
            previous = session.get(KnowledgeOperation, operation_key)
            if previous:
                count += len(previous.response["node_ids"])
                continue
        data = {
            "paper_id": paper_id,
            "document_version_id": version_id,
            "schema_version": DOMAIN_VERSION,
            "domain_extension": {
                "required_condition_dimensions": ["task_type", "dataset", "metric"]
            },
            "evidence_texts": group,
            "allowed_evidence_ids": [e["id"] for e in group],
        }
        run_id, raw = await call_model(
            engine,
            job_id,
            version_id,
            provider,
            "P02_extract_scientific_knowledge",
            data,
            ExtractionBatch.model_json_schema(),
        )
        try:
            batch = json.loads(raw)
            stage(engine, job_id, "saving")
            with Session(engine) as session, session.begin():
                current = session.get(Job, job_id)
                if current is None or current.status != "running":
                    raise ValueError("任务已取消，不再写入知识")
                response = KnowledgeStore(session).apply(
                    batch, version_id, set(data["allowed_evidence_ids"]), run_id, operation_key
                )
                count += len(response["node_ids"])
                current.result = {
                    "document_version_id": version_id,
                    "completed_batches": str(index + 1),
                    "total_batches": str(len(groups)),
                }
            mark_run(engine, run_id, "succeeded")
        except BaseException:
            mark_run(
                engine, run_id, "validation_failed", "抽取 Schema、证据或局部引用无效；本批未写入"
            )
            raise
    with Session(engine) as session, session.begin():
        current = session.get(Job, job_id)
        if current and current.status == "running":
            current.status, current.updated_at = "succeeded", now()
            current.result = {
                "document_version_id": version_id,
                "knowledge_count": str(count),
                "provider": provider.name,
                "completed_batches": str(len(groups)),
                "total_batches": str(len(groups)),
            }
