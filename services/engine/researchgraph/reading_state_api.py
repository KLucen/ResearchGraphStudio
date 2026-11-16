"""Local reading-state service. No provider is imported or invoked here."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError
from researchgraph.models import AttachmentRevision, Chunk, EvidenceSpan, Paper, Section, now
from researchgraph.paper_overview_models import PaperOverviewResult
from researchgraph.reading_state_contracts import (
    ConceptUnderstandingPut,
    ConceptUnderstandingView,
    ReaderContext,
    ReadingStatePut,
    ReadingStateView,
)
from researchgraph.reading_state_models import ConceptUnderstanding, ReadingState


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def node_fingerprint(node: dict[str, Any]) -> str:
    """An ID alone is insufficient: refreshed n1 may mean a different concept."""
    return _hash({key: value for key, value in node.items() if key != "id"})


def _revision(session: Session, paper_id: str, revision_id: str | None) -> AttachmentRevision:
    if session.get(Paper, paper_id) is None:
        raise KnowledgeError("PAPER_NOT_FOUND", "论文不存在")
    revision = (
        session.get(AttachmentRevision, revision_id)
        if revision_id
        else session.scalar(
            select(AttachmentRevision)
            .where(AttachmentRevision.paper_id == paper_id)
            .order_by(AttachmentRevision.created_at.desc(), AttachmentRevision.id.desc())
            .limit(1)
        )
    )
    if revision is None or revision.paper_id != paper_id:
        raise KnowledgeError("DOCUMENT_VERSION_NOT_FOUND", "论文尚未解析该 PDF 版本")
    return revision


def _scope(
    session: Session, paper_id: str, revision_id: str | None, section_id: str
) -> tuple[AttachmentRevision, Section, str, set[str]]:
    revision = _revision(session, paper_id, revision_id)
    section = session.get(Section, section_id)
    if section is None or section.document_version_id != revision.id:
        raise KnowledgeError("SECTION_NOT_FOUND", "章节不属于当前论文版本")
    paragraphs = session.execute(
        select(Chunk.id, Chunk.text, EvidenceSpan.id, EvidenceSpan.quote)
        .join(EvidenceSpan, EvidenceSpan.paragraph_id == Chunk.id)
        .where(
            EvidenceSpan.section_id == section_id,
            EvidenceSpan.document_version_id == revision.id,
            Chunk.revision_id == revision.id,
        )
        .order_by(Chunk.page_index, Chunk.block_index, EvidenceSpan.start_offset)
    ).all()
    source_hash = _hash(
        {
            "pdf_hash": revision.sha256,
            "section_id": section_id,
            "paragraphs": [list(p) for p in paragraphs],
        }
    )
    return revision, section, source_hash, {item[0] for item in paragraphs}


def current_overview(
    session: Session, paper_id: str, revision_id: str
) -> PaperOverviewResult | None:
    """Match the visible latest result; pending/failed refreshes never lend IDs."""
    row = session.scalar(
        select(PaperOverviewResult)
        .where(
            PaperOverviewResult.paper_id == paper_id,
            PaperOverviewResult.document_version_id == revision_id,
        )
        .order_by(PaperOverviewResult.updated_at.desc(), PaperOverviewResult.id.desc())
        .limit(1)
    )
    revision = session.get(AttachmentRevision, revision_id)
    if (
        row is None
        or row.status != "COMPLETED"
        or not isinstance(row.graph_json, dict)
        or revision is None
        or row.pdf_hash != revision.sha256
    ):
        return None
    return row


def _nodes(overview: PaperOverviewResult | None) -> dict[str, dict[str, Any]]:
    if overview is None:
        return {}
    return {
        str(node["id"]): node
        for node in (overview.graph_json or {}).get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }


def _current_node(
    row: ConceptUnderstanding, revision_id: str, nodes: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    node = nodes.get(row.graph_node_id)
    if (
        row.document_version_id == revision_id
        and node
        and node_fingerprint(node) == row.node_fingerprint
    ):
        return node
    return None


def _related_sections(
    session: Session, paper_id: str, revision_id: str, node_id: str, fingerprint: str
) -> list[dict[str, str]]:
    # A reliable, local term match supplies navigation without creating evidence
    # relationships or reading a previous section's complete model history.
    related: list[dict[str, str]] = []
    overview = current_overview(session, paper_id, revision_id)
    node = _nodes(overview).get(node_id)
    if node is None or node_fingerprint(node) != fingerprint:
        return []
    terms = [str(node.get("label_en") or ""), str(node.get("label_zh") or "")]
    linked_section_ids = set()
    for state in session.scalars(
        select(ReadingState).where(
            ReadingState.paper_id == paper_id,
            ReadingState.document_version_id == revision_id,
        )
    ).all():
        reference = (state.graph_reference_json or {}).get(node_id)
        if (
            node_id in (state.unresolved_concept_ids or [])
            and isinstance(reference, dict)
            and reference.get("fingerprint") == fingerprint
        ):
            linked_section_ids.add(state.section_id)
    # Only current, source-validated A02 associations may add navigation links.
    # This reads cached local data; it never runs A02 or extracts a new graph.
    from researchgraph.close_reading_api import _row_is_stale
    from researchgraph.close_reading_models import SectionCloseReadingResult

    for reading in session.scalars(
        select(SectionCloseReadingResult).where(
            SectionCloseReadingResult.paper_id == paper_id,
            SectionCloseReadingResult.document_version_id == revision_id,
            SectionCloseReadingResult.status.in_(["COMPLETED", "INCOMPLETE"]),
        )
    ).all():
        if (reading.request_metadata or {}).get("overview_result_id") != (
            overview.id if overview else None
        ):
            continue
        if _row_is_stale(session, reading):
            continue
        if any(
            node_id in paragraph.get("related_graph_node_ids", [])
            for paragraph in (reading.analysis_json or {}).get("paragraphs", [])
            if isinstance(paragraph, dict)
        ):
            linked_section_ids.add(reading.section_id)
    for section, text in session.execute(
        select(Section, Chunk.text)
        .join(EvidenceSpan, EvidenceSpan.section_id == Section.id)
        .join(Chunk, Chunk.id == EvidenceSpan.paragraph_id)
        .where(
            Section.document_version_id == revision_id,
            Section.excluded.is_(False),
            Chunk.revision_id == revision_id,
        )
        .order_by(Section.ordinal)
    ).all():
        if (
            section.id in linked_section_ids or any(_term_present(term, text) for term in terms)
        ) and not any(item["section_id"] == section.id for item in related):
            related.append({"section_id": section.id, "title": section.title})
    return related


def _has_unresolved_question(
    session: Session, paper_id: str, revision_id: str, node_id: str, fingerprint: str
) -> bool:
    for state in session.scalars(
        select(ReadingState).where(
            ReadingState.paper_id == paper_id,
            ReadingState.document_version_id == revision_id,
        )
    ).all():
        reference = (state.graph_reference_json or {}).get(node_id)
        if (
            node_id in (state.unresolved_concept_ids or [])
            and isinstance(reference, dict)
            and reference.get("fingerprint") == fingerprint
        ):
            return True
    return False


def _state_row(
    session: Session, paper_id: str, revision_id: str, section_id: str
) -> ReadingState | None:
    return session.scalar(
        select(ReadingState).where(
            ReadingState.paper_id == paper_id,
            ReadingState.document_version_id == revision_id,
            ReadingState.section_id == section_id,
        )
    )


def get_state_snapshot(
    session: Session, paper_id: str, revision_id: str, section_id: str
) -> dict[str, Any]:
    revision, _section, source_hash, _ids = _scope(session, paper_id, revision_id, section_id)
    overview = current_overview(session, paper_id, revision.id)
    nodes = _nodes(overview)
    row = _state_row(session, paper_id, revision.id, section_id)
    linked, unlinked = [], []
    if row is not None:
        references = row.graph_reference_json or {}
        for node_id in row.unresolved_concept_ids or []:
            reference = references.get(node_id)
            node = nodes.get(node_id)
            if (
                node
                and isinstance(reference, dict)
                and reference.get("fingerprint") == node_fingerprint(node)
            ):
                linked.append(node_id)
            else:
                unlinked.append(node_id)
    return ReadingStateView(
        paper_id=paper_id,
        document_version_id=revision.id,
        section_id=section_id,
        progress=cast(Any, row.progress) if row else "NOT_STARTED",
        self_assessment=cast(Any, row.self_assessment) if row else "UNSET",
        unresolved_concept_ids=linked,
        questions=cast(Any, row.questions) if row else [],
        updated_at=row.updated_at if row else None,
        source_hash=source_hash,
        source_changed=row is not None and row.source_hash != source_hash,
        overview_result_id=overview.id if overview else None,
        unresolved_unlinked_ids=unlinked,
    ).model_dump()


def list_concept_understanding(
    session: Session, paper_id: str, revision_id: str
) -> list[ConceptUnderstandingView]:
    overview = current_overview(session, paper_id, revision_id)
    nodes = _nodes(overview)
    rows = list(
        session.scalars(
            select(ConceptUnderstanding)
            .where(ConceptUnderstanding.paper_id == paper_id)
            .order_by(ConceptUnderstanding.updated_at.desc(), ConceptUnderstanding.id)
        ).all()
    )
    current_used: set[str] = set()
    views = []
    for row in rows:
        node = _current_node(row, revision_id, nodes)
        is_current = node is not None and row.graph_node_id not in current_used
        if is_current:
            current_used.add(row.graph_node_id)
        snapshot = node if node is not None and is_current else row.node_snapshot
        views.append(
            ConceptUnderstandingView(
                id=row.id,
                paper_id=paper_id,
                document_version_id=row.document_version_id,
                overview_result_id=overview.id
                if is_current and overview
                else row.overview_result_id,
                graph_node_id=row.graph_node_id,
                node_label_zh=str(snapshot.get("label_zh") or row.graph_node_id),
                node_label_en=snapshot.get("label_en"),
                self_level=cast(Any, row.self_level),
                last_check_result=cast(Any, row.last_check_result),
                note_zh=row.note_zh,
                last_check_note_zh=row.last_check_note_zh,
                updated_at=row.updated_at,
                association_status="CURRENT" if is_current else "NEEDS_RELINK",
                has_unresolved_question=is_current
                and _has_unresolved_question(
                    session, paper_id, revision_id, row.graph_node_id, row.node_fingerprint
                ),
                related_sections=cast(
                    Any,
                    _related_sections(
                        session, paper_id, revision_id, row.graph_node_id, row.node_fingerprint
                    ),
                )
                if is_current
                else [],
            )
        )
    for node_id, node in nodes.items():
        if node_id in current_used:
            continue
        views.append(
            ConceptUnderstandingView(
                paper_id=paper_id,
                document_version_id=revision_id,
                overview_result_id=overview.id if overview else None,
                graph_node_id=node_id,
                node_label_zh=str(node.get("label_zh") or node_id),
                node_label_en=node.get("label_en"),
                association_status="CURRENT",
                has_unresolved_question=_has_unresolved_question(
                    session, paper_id, revision_id, node_id, node_fingerprint(node)
                ),
                related_sections=cast(
                    Any,
                    _related_sections(
                        session, paper_id, revision_id, node_id, node_fingerprint(node)
                    ),
                ),
            )
        )
    return views


def _require_graph(
    session: Session,
    paper_id: str,
    revision_id: str,
    overview_result_id: str | None,
    node_ids: list[str],
) -> tuple[PaperOverviewResult, dict[str, dict[str, Any]]]:
    overview = current_overview(session, paper_id, revision_id)
    nodes = _nodes(overview)
    if (
        overview is None
        or overview.id != overview_result_id
        or any(item not in nodes for item in node_ids)
    ):
        raise KnowledgeError("CONCEPT_GRAPH_CHANGED", "当前图谱已变化，请刷新后重新选择概念")
    return overview, nodes


def _get_or_create_concept(
    session: Session,
    paper_id: str,
    revision_id: str,
    overview: PaperOverviewResult,
    node: dict[str, Any],
) -> ConceptUnderstanding:
    fingerprint = node_fingerprint(node)
    rows = session.scalars(
        select(ConceptUnderstanding)
        .where(
            ConceptUnderstanding.paper_id == paper_id,
            ConceptUnderstanding.document_version_id == revision_id,
            ConceptUnderstanding.graph_node_id == node["id"],
            ConceptUnderstanding.node_fingerprint == fingerprint,
        )
        .order_by(ConceptUnderstanding.updated_at.desc())
    ).all()
    if rows:
        return rows[0]
    conflicting = session.scalar(
        select(ConceptUnderstanding.id).where(
            ConceptUnderstanding.paper_id == paper_id,
            ConceptUnderstanding.overview_result_id == overview.id,
            ConceptUnderstanding.graph_node_id == node["id"],
        )
    )
    if conflicting is not None:
        raise KnowledgeError("CONCEPT_GRAPH_CHANGED", "当前概念内容已变化，请重新生成论文概览")
    row = ConceptUnderstanding(
        id=str(uuid4()),
        paper_id=paper_id,
        document_version_id=revision_id,
        overview_result_id=overview.id,
        graph_node_id=node["id"],
        node_fingerprint=fingerprint,
        node_snapshot=node,
        self_level="UNSET",
        last_check_result="NOT_CHECKED",
        note_zh="",
        last_check_note_zh="",
        updated_at=now(),
    )
    session.add(row)
    return row


def apply_check_result(
    session: Session,
    paper_id: str,
    revision_id: str,
    graph_node_ids: list[str],
    result: str,
    note_zh: str,
    *,
    overview_result_id: str | None,
) -> None:
    if result not in {"ADEQUATE", "PARTIAL", "MISCONCEPTION", "UNCERTAIN"}:
        raise KnowledgeError("CHECK_RESULT_INVALID", "理解检查结果无效")
    if not graph_node_ids:
        return
    overview, nodes = _require_graph(
        session, paper_id, revision_id, overview_result_id, graph_node_ids
    )
    for node_id in dict.fromkeys(graph_node_ids):
        row = _get_or_create_concept(session, paper_id, revision_id, overview, nodes[node_id])
        row.last_check_result = result
        row.last_check_note_zh = note_zh[:1600]
        row.updated_at = now()


def _term_present(term: str, text: str) -> bool:
    term = " ".join(term.split()).strip()
    if len(term) < 2 or (term.isascii() and len(term) < 3):
        return False
    if term.isascii():
        return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.IGNORECASE) is not None
    return term.casefold() in text.casefold()


def build_reader_context(
    session: Session, paper_id: str, revision_id: str, section_id: str, section_text: str
) -> dict[str, Any] | None:
    overview = current_overview(session, paper_id, revision_id)
    nodes = _nodes(overview)
    unresolved = set()
    for state in session.scalars(
        select(ReadingState).where(
            ReadingState.paper_id == paper_id,
            ReadingState.document_version_id == revision_id,
        )
    ).all():
        for node_id in state.unresolved_concept_ids or []:
            reference = (state.graph_reference_json or {}).get(node_id)
            node = nodes.get(node_id)
            if (
                node
                and isinstance(reference, dict)
                and reference.get("fingerprint") == node_fingerprint(node)
            ):
                unresolved.add(node_id)
    candidates = []
    for view in list_concept_understanding(session, paper_id, revision_id):
        if view.association_status != "CURRENT":
            continue
        if not any(
            _term_present(term or "", section_text)
            for term in (view.node_label_en, view.node_label_zh)
        ):
            continue
        if view.last_check_result == "MISCONCEPTION":
            priority, strategy = 0, "REVISIT_DEFINITIONS"
        elif view.self_level == "UNSURE" or view.graph_node_id in unresolved:
            priority, strategy = 1, "BRIDGE_GAPS"
        elif view.self_level == "PARTIAL" or view.last_check_result == "PARTIAL":
            priority, strategy = 2, "CONNECT_ARGUMENT"
        elif view.last_check_result == "ADEQUATE":
            priority, strategy = 3, "CRITICAL_READING"
        else:
            continue
        candidates.append((priority, strategy, view))
    candidates.sort(key=lambda item: (item[0], item[2].graph_node_id))
    selected = candidates[:3]
    if not selected:
        return None
    strategy = selected[0][1]
    focus = {
        "REVISIT_DEFINITIONS": "回顾相关定义并说明与本节论证的关系，提示需回看的原文位置。",
        "BRIDGE_GAPS": "优先澄清与本节相关的困惑概念，再介绍本节重点。",
        "CONNECT_ARGUMENT": "突出本节方法、假设与结果之间的逻辑关系。",
        "CRITICAL_READING": "减少基础术语说明，关注适用条件和需要核查的阅读问题。",
    }[strategy]
    return ReaderContext(
        strategy=cast(Any, strategy),
        unresolved_concepts=[item[2].node_label_zh for item in selected],
        prior_misunderstanding_summary="相关概念的先前理解检查提示需要回看定义。"
        if strategy == "REVISIT_DEFINITIONS"
        else "",
        preferred_focus=focus,
    ).model_dump()


def _http_error(exc: KnowledgeError) -> HTTPException:
    return HTTPException(
        404 if exc.code in {"PAPER_NOT_FOUND", "SECTION_NOT_FOUND"} else 409,
        {"code": exc.code, "message": str(exc)},
    )


def register_reading_state_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    @app.get(
        "/api/v1/papers/{paper_id}/sections/{section_id}/reading-state",
        response_model=ReadingStateView,
    )
    def get_state(
        paper_id: str, section_id: str, document_version_id: str | None = Query(None)
    ) -> ReadingStateView:
        try:
            with Session(engine()) as session:
                revision = _revision(session, paper_id, document_version_id)
                return ReadingStateView.model_validate(
                    get_state_snapshot(session, paper_id, revision.id, section_id)
                )
        except KnowledgeError as exc:
            raise _http_error(exc) from exc

    @app.put(
        "/api/v1/papers/{paper_id}/sections/{section_id}/reading-state",
        response_model=ReadingStateView,
    )
    def put_state(paper_id: str, section_id: str, body: ReadingStatePut) -> ReadingStateView:
        try:
            with Session(engine()) as session, session.begin():
                revision, _section, source_hash, paragraph_ids = _scope(
                    session, paper_id, body.document_version_id, section_id
                )
                if any(
                    q.paragraph_id is not None and q.paragraph_id not in paragraph_ids
                    for q in body.questions
                ):
                    raise KnowledgeError("READING_PARAGRAPH_INVALID", "疑问关联段落不属于当前小节")
                references = {}
                if body.unresolved_concept_ids:
                    _overview, nodes = _require_graph(
                        session,
                        paper_id,
                        revision.id,
                        body.overview_result_id,
                        body.unresolved_concept_ids,
                    )
                    references = {
                        node_id: {
                            "fingerprint": node_fingerprint(nodes[node_id]),
                            "overview_result_id": body.overview_result_id,
                        }
                        for node_id in body.unresolved_concept_ids
                    }
                row = _state_row(session, paper_id, revision.id, section_id)
                if row is None:
                    row = ReadingState(
                        id=str(uuid4()),
                        paper_id=paper_id,
                        document_version_id=revision.id,
                        section_id=section_id,
                        source_hash=source_hash,
                    )
                    session.add(row)
                row.source_hash, row.progress, row.self_assessment = (
                    source_hash,
                    body.progress,
                    body.self_assessment,
                )
                row.unresolved_concept_ids, row.graph_reference_json = (
                    body.unresolved_concept_ids,
                    references,
                )
                row.questions = [
                    question.model_dump(exclude_none=True) for question in body.questions
                ]
                row.updated_at = now()
                session.flush()
                return ReadingStateView.model_validate(
                    get_state_snapshot(session, paper_id, revision.id, section_id)
                )
        except KnowledgeError as exc:
            raise _http_error(exc) from exc

    @app.get(
        "/api/v1/papers/{paper_id}/concept-understanding",
        response_model=list[ConceptUnderstandingView],
    )
    def get_concepts(
        paper_id: str,
        document_version_id: str | None = Query(None),
        overview_result_id: str | None = Query(None),
    ) -> list[ConceptUnderstandingView]:
        try:
            with Session(engine()) as session:
                revision = _revision(session, paper_id, document_version_id)
                if overview_result_id is not None:
                    _require_graph(session, paper_id, revision.id, overview_result_id, [])
                return list_concept_understanding(session, paper_id, revision.id)
        except KnowledgeError as exc:
            raise _http_error(exc) from exc

    @app.put(
        "/api/v1/papers/{paper_id}/concept-understanding/{graph_node_id}",
        response_model=ConceptUnderstandingView,
    )
    def put_concept(
        paper_id: str, graph_node_id: str, body: ConceptUnderstandingPut
    ) -> ConceptUnderstandingView:
        try:
            with Session(engine()) as session, session.begin():
                revision = _revision(session, paper_id, body.document_version_id)
                overview, nodes = _require_graph(
                    session, paper_id, revision.id, body.overview_result_id, [graph_node_id]
                )
                row = _get_or_create_concept(
                    session, paper_id, revision.id, overview, nodes[graph_node_id]
                )
                row.self_level, row.note_zh, row.updated_at = body.self_level, body.note_zh, now()
                session.flush()
                return next(
                    view
                    for view in list_concept_understanding(session, paper_id, revision.id)
                    if view.id == row.id
                )
        except KnowledgeError as exc:
            raise _http_error(exc) from exc
