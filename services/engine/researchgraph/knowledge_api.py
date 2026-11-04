"""Compatibility API for P1 sources and P2 Paper & Reading."""

import base64
import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, Header, Query
from pydantic import Field, ValidationError
from sqlalchemy import Engine, select, true
from sqlalchemy.orm import Session

from researchgraph.integrations import ZoteroAdapter, safe_root
from researchgraph.knowledge_contracts import (
    DocumentStructure,
    EvidenceView,
    ExtractionRequest,
    KnowledgeList,
    ModelRunView,
    NodeDetail,
    NodeView,
    ReviewRequest,
    ReviewView,
    SectionView,
    StrictModel,
)
from researchgraph.knowledge_models import (
    Annotation,
    AuthorizedRoot,
    EvidenceSpan,
    KnowledgeNode,
    ModelRun,
    NodeEvidence,
    NoteSnapshot,
    ReviewDecision,
    Section,
    ZoteroLink,
)
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, validate_evidence
from researchgraph.models import AttachmentRevision, Chunk, Job, Paper, PaperSource, Project, now
from researchgraph.providers import ConfiguredProvider, provider_for
from researchgraph.schemas import JobView

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)]


class RootRequest(StrictModel):
    project_id: str
    path: str = Field(min_length=1, max_length=4096)


class ZoteroRequest(StrictModel):
    document_version_id: str
    library: str = "users/0"
    item_key: str
    attachment_key: str


class Preview(StrictModel):
    data_url: str
    page_index: int
    precision: str = "block"


def register_knowledge_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    from researchgraph.app import remember, remembered

    @app.exception_handler(ValidationError)
    async def invalid_candidate(request: Any, error: ValidationError) -> Any:
        from fastapi.responses import JSONResponse

        fields = [".".join(str(p) for p in item["loc"]) for item in error.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "SCHEMA_INVALID",
                    "message": "内容未通过领域校验：" + ", ".join(fields)[:300],
                    "request_id": getattr(request.state, "request_id", ""),
                }
            },
        )

    @app.get("/api/v1/revisions/{version_id}/structure", response_model=DocumentStructure)
    def structure(version_id: str) -> DocumentStructure:
        from researchgraph.document_structure import current_structure

        with Session(engine()) as session:
            if session.get(AttachmentRevision, version_id) is None:
                raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
            artifact = current_structure(session, version_id)
            return DocumentStructure(
                document_version_id=version_id,
                structured_document=artifact.data if artifact else None,
                sections=[
                    SectionView.model_validate(s)
                    for s in session.scalars(
                        select(Section)
                        .where(Section.document_version_id == version_id)
                        .order_by(Section.ordinal)
                    )
                ],
                evidence=[
                    EvidenceView.model_validate(e)
                    for e in session.scalars(
                        select(EvidenceSpan)
                        .join(Chunk, Chunk.id == EvidenceSpan.paragraph_id)
                        .where(EvidenceSpan.document_version_id == version_id)
                        .order_by(
                            EvidenceSpan.page_index,
                            Chunk.block_index,
                            EvidenceSpan.start_offset,
                        )
                    )
                ],
            )

    @app.get("/api/v1/evidence/{evidence_id}", response_model=EvidenceView)
    def evidence_detail(evidence_id: str) -> EvidenceView:
        with Session(engine()) as session:
            span = session.get(EvidenceSpan, evidence_id)
            if span is None:
                raise KnowledgeError("EVIDENCE_NOT_FOUND", "证据不存在")
            validate_evidence(session, span, span.document_version_id)
            return EvidenceView.model_validate(span)

    @app.get("/api/v1/evidence/{evidence_id}/preview", response_model=Preview)
    def preview(evidence_id: str) -> Preview:
        with Session(engine()) as session:
            span = session.get(EvidenceSpan, evidence_id)
            if span is None:
                raise KnowledgeError("EVIDENCE_NOT_FOUND", "证据不存在")
            validate_evidence(session, span, span.document_version_id)
            version = session.get(AttachmentRevision, span.document_version_id)
            assert version
            sources = session.scalars(
                select(PaperSource).where(PaperSource.paper_id == version.paper_id)
            ).all()
            content: bytes | None = None
            for source in sources:
                for value in [source.managed_path, source.path]:
                    if not value:
                        continue
                    try:
                        with Path(value).open("rb") as stream:
                            raw = stream.read(50 * 1024 * 1024 + 1)
                        if (
                            len(raw) <= 50 * 1024 * 1024
                            and hashlib.sha256(raw).hexdigest() == version.sha256
                        ):
                            content = raw
                            break
                    except OSError:
                        continue
                if content:
                    break
            if content is None:
                raise KnowledgeError(
                    "SOURCE_UNAVAILABLE",
                    "该版本 PDF 不可用或已变化，解析原文仍可查看；请重新定位来源",
                )
            import pymupdf

            with pymupdf.open(stream=content, filetype="pdf") as document:
                page = document[span.page_index]
                for bbox in span.bbox_list:
                    page.draw_rect(
                        pymupdf.Rect(bbox),
                        color=(0.9, 0.55, 0),
                        fill=(1, 0.85, 0.2),
                        fill_opacity=0.2,
                        overlay=True,
                    )
                scale = min(1.3, 1600 / max(page.rect.width, page.rect.height))
                image = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale)).tobytes("png")
            return Preview(
                data_url="data:image/png;base64," + base64.b64encode(image).decode(),
                page_index=span.page_index,
            )

    @app.get("/api/v1/revisions/{version_id}/knowledge", response_model=KnowledgeList)
    def knowledge(
        version_id: str, include_test_data: bool = True, current_schema_only: bool = False
    ) -> KnowledgeList:
        from researchgraph.knowledge_visibility import production_knowledge
        from researchgraph.reading_scope import current_nodes

        with Session(engine()) as session:
            version = session.get(AttachmentRevision, version_id)
            paper = session.get(Paper, version.paper_id) if version else None
            if paper is None:
                raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
            current_ids = (
                {n.id for n in current_nodes(session, version_id)} if current_schema_only else None
            )
            return KnowledgeList(
                items=[
                    NodeView.model_validate(n)
                    for n in session.scalars(
                        select(KnowledgeNode)
                        .where(KnowledgeNode.document_version_id == version_id)
                        .where(true() if include_test_data else production_knowledge())
                        .order_by(KnowledgeNode.created_at, KnowledgeNode.id)
                    )
                    if current_ids is None or n.id in current_ids
                ],
                graph_revision=KnowledgeStore(session).graph_revision(paper.project_id),
            )

    @app.get("/api/v1/knowledge/nodes/{node_id}", response_model=NodeDetail)
    def node_detail(node_id: str) -> NodeDetail:
        with Session(engine()) as session:
            node = session.get(KnowledgeNode, node_id)
            if node is None:
                raise KnowledgeError("NODE_NOT_FOUND", "知识对象不存在")
            paper = session.get(Paper, node.paper_id)
            assert paper
            run = session.get(ModelRun, node.model_run_id) if node.model_run_id else None
            return NodeDetail(
                node=NodeView.model_validate(node),
                evidence=[
                    EvidenceView.model_validate(e)
                    for e in session.scalars(
                        select(EvidenceSpan)
                        .join(NodeEvidence, NodeEvidence.evidence_id == EvidenceSpan.id)
                        .where(NodeEvidence.node_id == node_id)
                    )
                ],
                reviews=[
                    ReviewView.model_validate(r)
                    for r in session.scalars(
                        select(ReviewDecision)
                        .where(ReviewDecision.node_id == node_id)
                        .order_by(ReviewDecision.created_at)
                    )
                ],
                model_run=ModelRunView.model_validate(run) if run else None,
                graph_revision=KnowledgeStore(session).graph_revision(paper.project_id),
            )

    @app.post("/api/v1/knowledge/extract", response_model=JobView, status_code=202)
    def extract(body: ExtractionRequest, idempotency_key: Key) -> JobView:
        try:
            if body.provider != "project":
                provider_for(body.provider, body.allow_network)
        except ValueError as error:
            raise KnowledgeError("PROVIDER_NOT_CONFIGURED", str(error)) from None
        with Session(engine()) as session, session.begin():
            request_body = body.model_dump(
                exclude=(
                    {"pipeline", "density", "paper_type"}
                    if body.pipeline == "legacy-v2"
                    else {"density", "paper_type"}
                    if body.pipeline == "unified-v3"
                    else set()
                )
            )
            previous = remembered(session, "extract:" + idempotency_key, request_body)
            if previous:
                return JobView.model_validate(previous)
            version = session.get(AttachmentRevision, body.document_version_id)
            paper = session.get(Paper, version.paper_id) if version else None
            if paper is None:
                raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
            payload = body.model_dump()
            if body.pipeline == "paper-reading-v1":
                from researchgraph.reading_finish_wire import POLICY

                payload["reading_flow_policy"] = POLICY
            if body.provider == "project":
                from researchgraph.model_settings import from_snapshot, snapshot_for

                snapshot = snapshot_for(session, paper.project_id, "extraction")
                from_snapshot(snapshot, Path(str(engine().url.database)).parent, body.allow_network)
                payload["model_snapshot"] = snapshot
            job = Job(
                id=str(uuid4()),
                project_id=paper.project_id,
                kind="knowledge_extract",
                payload=payload,
                status="queued",
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
            session.add(job)
            response = JobView.model_validate(job)
            remember(session, "extract:" + idempotency_key, request_body, response.model_dump())
            return response

    @app.post("/api/v1/knowledge/reviews", response_model=NodeView)
    def review(body: ReviewRequest, idempotency_key: Key) -> NodeView:
        with Session(engine()) as session, session.begin():
            return KnowledgeStore(session).review(body, "review:" + idempotency_key)

    @app.get("/api/v1/revisions/{version_id}/runs", response_model=list[ModelRunView])
    def runs(version_id: str) -> list[ModelRunView]:
        with Session(engine()) as session:
            return [
                ModelRunView.model_validate(r)
                for r in session.scalars(
                    select(ModelRun)
                    .where(ModelRun.document_version_id == version_id)
                    .order_by(ModelRun.created_at.desc())
                )
            ]

    @app.get("/api/v1/providers")
    def providers() -> dict[str, Any]:
        try:
            provider = ConfiguredProvider()
            configured, model = True, provider.model
        except ValueError:
            configured, model = False, None
        return {
            "mock": "离线原文摘录，仅用于流程验证",
            "configured": configured,
            "model": model,
            "transmitted_data": "当前论文解析片段、证据 ID 与输出 Schema；不含私人笔记",
        }

    @app.get("/api/v1/integrations/zotero/status")
    def zotero_status() -> dict[str, Any]:
        try:
            ZoteroAdapter().browse("users/0", "items")
            return {"connected": True, "read_only": True}
        except KnowledgeError as error:
            return {"connected": False, "read_only": True, "error": str(error)}

    @app.get("/api/v1/integrations/zotero/{kind}")
    def zotero_browse(
        kind: str, library: str = "users/0", start: int = Query(0, ge=0, le=10000)
    ) -> list[dict[str, Any]]:
        if kind not in {"items", "collections"}:
            raise KnowledgeError("NOT_FOUND", "Zotero 只读操作不存在")
        return ZoteroAdapter().browse(library, kind, start)

    @app.post("/api/v1/integrations/zotero/annotations")
    def zotero_annotations(body: ZoteroRequest, idempotency_key: Key) -> dict[str, Any]:
        with Session(engine()) as session:
            previous = remembered(session, "annotations:" + idempotency_key, body.model_dump())
            if previous:
                return previous
        metadata, annotations, path = ZoteroAdapter().read_annotations(
            body.library, body.item_key, body.attachment_key
        )
        with Session(engine()) as session, session.begin():
            previous = remembered(session, "annotations:" + idempotency_key, body.model_dump())
            if previous:
                return previous
            result = KnowledgeStore(session).import_annotations(
                body.document_version_id,
                body.library,
                body.item_key,
                body.attachment_key,
                metadata,
                annotations,
                path,
            )
            remember(session, "annotations:" + idempotency_key, body.model_dump(), result)
            return result

    @app.get("/api/v1/revisions/{version_id}/annotations")
    def annotations(version_id: str) -> list[dict[str, Any]]:
        with Session(engine()) as session:
            result = []
            for annotation in session.scalars(
                select(Annotation).where(Annotation.document_version_id == version_id)
            ):
                link = session.get(ZoteroLink, annotation.link_id)
                assert link
                result.append(
                    {
                        "id": annotation.id,
                        "text": annotation.text,
                        "comment": annotation.comment,
                        "type": annotation.annotation_type,
                        "source_position": annotation.source_position,
                        "source_item_key": link.item_key,
                        "annotation_key": annotation.annotation_key,
                        "anchor_status": annotation.anchor_status,
                        "evidence_id": annotation.evidence_id,
                    }
                )
            return result

    @app.post("/api/v1/integrations/obsidian/roots")
    def authorize_root(body: RootRequest, idempotency_key: Key) -> dict[str, Any]:
        path = safe_root(Path(body.path))
        with Session(engine()) as session, session.begin():
            previous = remembered(session, "root:" + idempotency_key, body.model_dump())
            if previous:
                return previous
            if session.get(Project, body.project_id) is None:
                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            root = session.scalar(
                select(AuthorizedRoot).where(
                    AuthorizedRoot.project_id == body.project_id, AuthorizedRoot.path == str(path)
                )
            )
            if root is None:
                root = AuthorizedRoot(
                    id=str(uuid4()),
                    project_id=body.project_id,
                    path=str(path),
                    active=True,
                    created_at=now(),
                )
                session.add(root)
            root.active = True
            response = {"id": root.id, "path": root.path, "active": True}
            KnowledgeStore(session).event(
                body.project_id, "NOTES_AUTHORIZED", {"root_id": root.id}, actor="user"
            )
            remember(session, "root:" + idempotency_key, body.model_dump(), response)
            return response

    @app.get("/api/v1/projects/{project_id}/note-roots")
    def roots(project_id: str) -> list[dict[str, Any]]:
        with Session(engine()) as session:
            return [
                {"id": r.id, "path": r.path, "active": r.active}
                for r in session.scalars(
                    select(AuthorizedRoot).where(AuthorizedRoot.project_id == project_id)
                )
            ]

    @app.post("/api/v1/integrations/obsidian/{root_id}/{action}")
    def scan_notes(root_id: str, action: str, idempotency_key: Key) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            body = {"root_id": root_id, "action": action}
            previous = remembered(session, "notes:" + idempotency_key, body)
            if previous:
                return previous
            root = session.get(AuthorizedRoot, root_id)
            if root is None:
                raise KnowledgeError("ROOT_NOT_AUTHORIZED", "笔记目录未授权")
            if action == "revoke":
                root.active = False
                KnowledgeStore(session).event(
                    root.project_id, "NOTES_REVOKED", {"root_id": root_id}, actor="user"
                )
                result: dict[str, Any] = {"active": False}
            elif action == "scan":
                result = KnowledgeStore(session).scan_notes(root_id)
            else:
                raise KnowledgeError("NOT_FOUND", "笔记操作不存在")
            remember(session, "notes:" + idempotency_key, body, result)
            return result

    @app.get("/api/v1/integrations/obsidian/{root_id}/notes")
    def notes(root_id: str) -> list[dict[str, Any]]:
        with Session(engine()) as session:
            root = session.get(AuthorizedRoot, root_id)
            if root is None or not root.active:
                raise KnowledgeError("ROOT_NOT_AUTHORIZED", "笔记授权已撤销")
            return [
                {
                    "id": n.id,
                    "relative_path": n.relative_path,
                    "sha256": n.sha256,
                    "text": n.text,
                    "authorship": "user",
                }
                for n in session.scalars(
                    select(NoteSnapshot).where(NoteSnapshot.root_id == root_id)
                )
            ]
