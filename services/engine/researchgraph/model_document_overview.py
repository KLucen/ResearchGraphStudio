"""Project model-derived sections onto the shared PaperCard/LightGraph contract.

The parser source and output history stay in the model-document tables.  No
legacy PDF revision or chunk is fabricated to make an overview visible.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from researchgraph.core import StrictModel, stable_id
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.model_document_models import (
    LlmDocumentOutput,
    LlmDocumentParse,
    LlmDocumentSegment,
)
from researchgraph.model_document_overview_models import (
    ModelOverviewGraphLayout,
    ModelOverviewGraphViewport,
)
from researchgraph.models import Job, Paper, now
from researchgraph.paper_overview_api import SYSTEM_PROMPT, overview_schema
from researchgraph.paper_overview_contracts import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    GraphPosition,
    GraphViewport,
    LayoutInput,
    LayoutReset,
    LayoutView,
    LightGraph,
    OverviewGenerate,
    OverviewUsage,
    OverviewView,
    PaperCard,
    normalized_label,
    validate_response,
)
from researchgraph.storage import read_session

MODEL_OVERVIEW_PROMPT = SYSTEM_PROMPT


class ModelOverviewResult(StrictModel):
    """Persisted, expanded graph IDs; the wire contract uses local n/e IDs."""

    schema_version: Literal["paper_overview_graph.v1"]
    paper_card: PaperCard
    graph: LightGraph


def model_overview_schema() -> dict[str, Any]:
    return overview_schema()


def model_document_paper(db: Session, parse: LlmDocumentParse) -> Paper | None:
    source = db.get(ImportSession, parse.import_session_id)
    if source is None:
        return None
    paper_id = source.source_snapshot.get("paper_id")
    if not paper_id:
        item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == source.id,
                ImportPlanItem.item_kind == "document_parse",
            )
        )
        job = db.get(Job, item.job_id) if item and item.job_id else None
        paper_id = (job.payload or {}).get("paper_id") if job else None
    paper = db.get(Paper, paper_id) if isinstance(paper_id, str) and paper_id else None
    return paper if paper and paper.project_id == source.project_id else None


def build_model_overview_context(db: Session, parse: LlmDocumentParse) -> dict[str, Any]:
    paper = model_document_paper(db, parse)
    if paper is None or parse.status != "succeeded":
        raise ValueError("模型章节与论文归属无效，不能生成概览")
    segments = db.scalars(
        select(LlmDocumentSegment)
        .where(LlmDocumentSegment.parse_id == parse.id)
        .order_by(
            LlmDocumentSegment.chapter_order,
            LlmDocumentSegment.ordinal,
            LlmDocumentSegment.id,
        )
    ).all()
    chapters: list[dict[str, Any]] = []
    by_ref: dict[str, dict[str, Any]] = {}
    excluded_level: int | None = None
    for segment in segments:
        if segment.chapter_ref not in by_ref:
            title = re.sub(r"^\s*(?:\d+[.)]?\s*)?", "", segment.chapter_title).strip()
            references = bool(
                re.fullmatch(r"references?|bibliography|参考文献|參考文獻", title, flags=re.I)
            )
            if excluded_level is not None and segment.chapter_level <= excluded_level:
                excluded_level = None
            if references:
                excluded_level = segment.chapter_level
            chapter: dict[str, Any] = {
                "chapter_ref": segment.chapter_ref,
                "title": segment.chapter_title,
                "level": segment.chapter_level,
                "excluded": excluded_level is not None,
                "segments": [],
            }
            by_ref[segment.chapter_ref] = chapter
            chapters.append(chapter)
        chapter = by_ref[segment.chapter_ref]
        if not chapter["excluded"]:
            chapter["segments"].append(
                {
                    "kind": segment.kind,
                    "text": segment.text,
                    "latex": segment.latex,
                    "mathml": segment.mathml,
                    "raw_table_text": segment.raw_table_text,
                    "table_data": segment.table_data,
                    "status": segment.status,
                }
            )
    readable = [
        {key: value for key, value in chapter.items() if key != "excluded"}
        for chapter in chapters
        if not chapter["excluded"] and chapter["segments"]
    ]
    if not readable:
        raise ValueError("模型解析没有可用于概览的正文、公式或表格材料")
    return {
        "title": paper.title,
        "paper_id": paper.id,
        "document_version_id": parse.id,
        "source": "model_document",
        "chapters": readable,
    }


def validate_model_overview(raw: str | dict[str, Any], paper_id: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        saved = ModelOverviewResult.model_validate(raw, strict=True)
        if saved.graph.nodes and all(
            re.fullmatch(r"n[1-9][0-9]*", node.id) for node in saved.graph.nodes
        ):
            # User JSON/repair DTOs can retain wire IDs; the application owns
            # the conversion into persistent identities.
            raw = json.dumps(raw, ensure_ascii=False)
        else:
            for node in saved.graph.nodes:
                expected = stable_id(
                    "light-node", f"{paper_id}/{node.type}/{normalized_label(node.label_zh)}"
                )
                if node.id != expected:
                    raise ValueError("概览节点身份与当前论文不匹配")
            for edge in saved.graph.edges:
                expected = stable_id(
                    "light-edge", f"{paper_id}/{edge.source}/{edge.type}/{edge.target}"
                )
                if edge.id != expected:
                    raise ValueError("概览关系身份与当前论文不匹配")
            return saved.model_dump()
    card, graph = validate_response(raw, paper_id)
    return ModelOverviewResult(
        schema_version="paper_overview_graph.v1", paper_card=card, graph=graph
    ).model_dump()


def _latest_output(db: Session, parse_id: str) -> LlmDocumentOutput | None:
    return db.scalar(
        select(LlmDocumentOutput)
        .where(
            LlmDocumentOutput.parse_id == parse_id,
            LlmDocumentOutput.item_kind == "paper_overview",
        )
        .order_by(LlmDocumentOutput.created_at.desc(), LlmDocumentOutput.id.desc())
        .limit(1)
    )


def model_overview_view(
    db: Session, parse: LlmDocumentParse, output: LlmDocumentOutput
) -> OverviewView | None:
    paper = model_document_paper(db, parse)
    if (
        paper is None
        or output.parse_id != parse.id
        or output.import_session_id != parse.import_session_id
        or output.item_kind != "paper_overview"
    ):
        raise ValueError("概览结果与模型章节归属不匹配")
    result: ModelOverviewResult | None = None
    if output.status == "succeeded":
        if (
            not isinstance(output.output_json, dict)
            or output.output_json.get("schema_version") != SCHEMA_VERSION
        ):
            # Old summary-only outputs are history, not empty or invented graphs.
            return None
        result = ModelOverviewResult.model_validate(
            validate_model_overview(output.output_json, paper.id), strict=True
        )
    item = db.scalar(
        select(ImportPlanItem).where(
            ImportPlanItem.session_id == parse.import_session_id,
            ImportPlanItem.item_kind == "paper_overview",
        )
    )
    usage = output.usage or {}
    raw_receipts = usage.get("requests")
    receipts = {
        (entry["job_id"], entry["attempt"], entry["purpose"]): entry
        for entry in (raw_receipts if isinstance(raw_receipts, list) else [])
        if isinstance(entry, dict)
        and isinstance(entry.get("job_id"), str)
        and type(entry.get("attempt")) is int
        and entry["attempt"] >= 0
        and entry.get("purpose") in {"generate", "repair"}
        and entry.get("status") in {"sent", "received", "failed"}
    }

    def token(*keys: str) -> int | None:
        for key in keys:
            value = usage.get(key)
            if type(value) is int and value >= 0:
                return value
        return None

    inp, out = token("prompt_tokens", "input_tokens"), token("completion_tokens", "output_tokens")
    return OverviewView(
        id=output.id,
        paper_id=paper.id,
        document_version_id=parse.id,
        # A model-only import has no legacy PDF digest/revision.  These empty
        # compatibility fields never serve as a source identity or prerequisite.
        pdf_hash="",
        input_hash="",
        schema_version=SCHEMA_VERSION,
        prompt_version=PROMPT_VERSION,
        provider_id=output.provider_id or "",
        model_id=output.model_id or "",
        status=(
            "COMPLETED"
            if output.status == "succeeded"
            else "PENDING"
            if output.status in {"pending", "running"}
            else "FAILED"
        ),
        graph_status="READY" if result and result.graph.nodes else "NOT_ENOUGH_INFO",
        paper_card=result.paper_card if result else None,
        graph=result.graph if result else None,
        usage=OverviewUsage(
            input_tokens=inp,
            output_tokens=out,
            total_tokens=token("total_tokens"),
            calls=len(receipts),
            retry_count=sum(
                entry["purpose"] == "repair" or entry["attempt"] > 1 for entry in receipts.values()
            ),
            usage_source="provider" if inp is not None and out is not None else "unknown",
        ),
        generated_at=output.updated_at,
        job_id=item.job_id if item else None,
        error_code="SOURCE_CHANGED" if output.status == "stale" else output.error_code,
        error=(
            "章节内容已修改，请明确允许后重新生成概览。"
            if output.status == "stale"
            else output.error
        ),
    )


def model_overview_with_previous(
    db: Session, parse: LlmDocumentParse, output: LlmDocumentOutput
) -> OverviewView | None:
    """Keep a current-source successful draft visible during a failed refresh."""
    current = model_overview_view(db, parse, output)
    if current is None or current.status == "COMPLETED":
        return current
    previous = db.scalars(
        select(LlmDocumentOutput)
        .where(
            LlmDocumentOutput.parse_id == parse.id,
            LlmDocumentOutput.item_kind == "paper_overview",
            LlmDocumentOutput.status == "succeeded",
            LlmDocumentOutput.id != output.id,
        )
        .order_by(LlmDocumentOutput.created_at.desc(), LlmDocumentOutput.id.desc())
    ).all()
    for candidate in previous:
        if (candidate.usage or {}).get("source_updated_at") != parse.updated_at:
            continue
        try:
            valid = model_overview_view(db, parse, candidate)
        except ValueError:
            continue
        if valid is not None and valid.paper_card is not None and valid.graph is not None:
            return current.model_copy(
                update={
                    "paper_card": valid.paper_card,
                    "graph": valid.graph,
                    "graph_status": valid.graph_status,
                    "display_result_id": valid.id,
                }
            )
    return current


def register_model_overview_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    def source(db: Session, paper_id: str, parse_id: str) -> LlmDocumentParse:
        parse = db.get(LlmDocumentParse, parse_id)
        paper = model_document_paper(db, parse) if parse else None
        if parse is None or paper is None or paper.id != paper_id or parse.status != "succeeded":
            raise HTTPException(404, "未找到本篇论文的已完成模型章节")
        return parse

    def result(db: Session, paper_id: str, result_id: str) -> ModelOverviewResult:
        output = db.get(LlmDocumentOutput, result_id)
        parse = source(db, paper_id, output.parse_id) if output else None
        if output is None or parse is None:
            raise HTTPException(404, "模型概览不存在")
        view = model_overview_view(db, parse, output)
        if view is None or view.status != "COMPLETED" or output.output_json is None:
            raise HTTPException(409, "模型概览尚未完成")
        return ModelOverviewResult.model_validate(output.output_json, strict=True)

    def layout(db: Session, paper_id: str, result_id: str) -> LayoutView:
        result(db, paper_id, result_id)
        rows = db.scalars(
            select(ModelOverviewGraphLayout)
            .where(ModelOverviewGraphLayout.overview_result_id == result_id)
            .order_by(ModelOverviewGraphLayout.node_id)
        ).all()
        viewport = db.get(ModelOverviewGraphViewport, result_id)
        return LayoutView(
            overview_result_id=result_id,
            positions=[
                GraphPosition(node_id=row.node_id, x=row.x, y=row.y, pinned=row.pinned)
                for row in rows
            ],
            viewport=(
                GraphViewport(x=viewport.x, y=viewport.y, zoom=viewport.zoom) if viewport else None
            ),
        )

    @app.get("/api/v1/papers/{paper_id}/model-overview", response_model=OverviewView | None)
    def get_overview(paper_id: str, parse_id: str = Query(min_length=1)) -> OverviewView | None:
        with read_session(engine()) as db:
            parse = source(db, paper_id, parse_id)
            output = _latest_output(db, parse.id)
            return model_overview_with_previous(db, parse, output) if output else None

    @app.post("/api/v1/papers/{paper_id}/model-overview/generate", response_model=OverviewView)
    def generate(paper_id: str, body: OverviewGenerate) -> OverviewView:
        from researchgraph.model_document_api import queue_model_document_output

        if not body.allow_network:
            raise HTTPException(409, "生成论文概览前请明确允许一次模型调用")
        with Session(engine()) as db, db.begin():
            parse = source(db, paper_id, body.document_version_id or "")
            output = _latest_output(db, parse.id)
            view = model_overview_with_previous(db, parse, output) if output else None
            if view and (
                view.status == "PENDING"
                or (view.status == "COMPLETED" and not body.force_regenerate)
                or (view.status == "FAILED" and not body.retry_failed and not body.force_regenerate)
            ):
                return view
            # Validate the source before queueing; opening the panel never queues.
            build_model_overview_context(db, parse)
            job = queue_model_document_output(
                db,
                parse.import_session_id,
                "paper_overview",
                allow_network=True,
                translation_mode="none",
                force_regenerate=True,
                parse_id=parse.id,
            )
            # Queueing and the PENDING read model are published atomically so
            # polling cannot briefly return null between these two states.
            output = _latest_output(db, parse.id)
            if output is None or output.status not in {"pending", "running"}:
                timestamp = now()
                output = LlmDocumentOutput(
                    id=str(uuid4()),
                    import_session_id=parse.import_session_id,
                    parse_id=parse.id,
                    item_kind="paper_overview",
                    status="pending",
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                db.add(output)
                db.flush()
            queued = model_overview_with_previous(db, parse, output)
            assert queued is not None
            return queued.model_copy(update={"job_id": job.id})

    @app.get("/api/v1/papers/{paper_id}/model-overview/graph/layout", response_model=LayoutView)
    def get_layout(paper_id: str, overview_result_id: str) -> LayoutView:
        with read_session(engine()) as db:
            return layout(db, paper_id, overview_result_id)

    @app.post("/api/v1/papers/{paper_id}/model-overview/graph/layout", response_model=LayoutView)
    def save_layout(paper_id: str, body: LayoutInput) -> LayoutView:
        with Session(engine()) as db, db.begin():
            semantic = result(db, paper_id, body.overview_result_id)
            allowed = {node.id for node in semantic.graph.nodes}
            if any(position.node_id not in allowed for position in body.positions):
                raise HTTPException(422, "布局包含不属于当前概览的节点")
            db.execute(
                delete(ModelOverviewGraphLayout).where(
                    ModelOverviewGraphLayout.overview_result_id == body.overview_result_id
                )
            )
            db.add_all(
                ModelOverviewGraphLayout(
                    id=str(uuid4()),
                    paper_id=paper_id,
                    overview_result_id=body.overview_result_id,
                    node_id=position.node_id,
                    x=position.x,
                    y=position.y,
                    pinned=position.pinned,
                )
                for position in body.positions
            )
            if body.viewport is not None:
                viewport = db.get(ModelOverviewGraphViewport, body.overview_result_id)
                if viewport is None:
                    db.add(
                        ModelOverviewGraphViewport(
                            overview_result_id=body.overview_result_id,
                            **body.viewport.model_dump(),
                        )
                    )
                else:
                    viewport.x, viewport.y, viewport.zoom = (
                        body.viewport.x,
                        body.viewport.y,
                        body.viewport.zoom,
                    )
                    viewport.updated_at = now()
            db.flush()
            return layout(db, paper_id, body.overview_result_id)

    @app.post(
        "/api/v1/papers/{paper_id}/model-overview/graph/layout/reset", response_model=LayoutView
    )
    def reset_layout(paper_id: str, body: LayoutReset) -> LayoutView:
        with Session(engine()) as db, db.begin():
            result(db, paper_id, body.overview_result_id)
            for table in (ModelOverviewGraphLayout, ModelOverviewGraphViewport):
                db.execute(delete(table).where(table.overview_result_id == body.overview_result_id))
            return LayoutView(
                overview_result_id=body.overview_result_id, positions=[], viewport=None
            )
