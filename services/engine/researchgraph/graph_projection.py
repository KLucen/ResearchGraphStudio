"""Project-scoped, bounded projection and independent optimistic layout persistence."""

import base64
import json
import re
from collections.abc import Callable
from typing import Any, cast

from fastapi import FastAPI
from sqlalchemy import Engine, String, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session

from researchgraph.graph_contracts import (
    GraphProjection,
    LayoutRequest,
    LayoutView,
    ProjectionDetail,
    ProjectionEdge,
    ProjectionNode,
    ProjectionQuery,
    VisualKind,
)
from researchgraph.graph_models import GraphLayout, KnowledgeDisplay, SourceAssertion
from researchgraph.knowledge_contracts import EvidenceView, NodeView
from researchgraph.knowledge_models import (
    EvidenceSpan,
    KnowledgeDependency,
    KnowledgeNode,
    NodeEvidence,
    ZoteroLink,
)
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, validate_evidence
from researchgraph.knowledge_visibility import production_knowledge
from researchgraph.models import AttachmentRevision, Paper, Project, now
from researchgraph.reasoning_models import RelationAssertion
from researchgraph.reasoning_store import proposal_view

KINDS = {
    "concept": "Concept",
    "method": "Method",
    "claim": "Claim",
    "research_question": "ResearchQuestion",
}
RELATIONS = {
    "ABOUT": "涉及",
    "USES_METHOD": "使用方法",
    "INVOLVES_CONCEPT": "涉及概念",
    "STUDIES": "研究",
    "RELATED_TO": "相关",
    "QUESTIONS": "提出问题",
    "HAS_METHOD": "包含方法",
    "REPORTS": "报告",
    "SUPPORTS": "支持",
    "CONTRADICTS": "冲突",
    "QUALIFIES": "限定",
    "EXTENDS": "扩展",
    "RELATED": "相关",
}


def require_project(session: Session, project_id: str) -> None:
    if session.get(Project, project_id) is None:
        raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")


def display_data(session: Session, node: KnowledgeNode) -> dict[str, Any]:
    display = session.get(KnowledgeDisplay, node.id)
    if display and display.source_revision == node.revision:
        return display.data
    payload = node.payload
    zh = str(
        payload.get("statement_zh")
        or payload.get("name_zh")
        or payload.get("canonical_name_zh")
        or ""
    )
    return {
        "label_zh": zh[:28],
        "label_en": node.text[:80],
        "summary_en": node.text,
        "summary_zh": zh,
        "translation_status": "available" if zh else "missing",
    }


class GraphProjectionService:
    def __init__(self, session: Session, project_id: str):
        require_project(session, project_id)
        self.session, self.project_id = session, project_id

    def node_query(self, body: ProjectionQuery) -> Any:
        query = (
            select(KnowledgeNode)
            .join(Paper)
            .where(
                Paper.project_id == self.project_id,
                KnowledgeNode.kind.in_([k for k, v in KINDS.items() if v in body.kinds]),
            )
        )
        if not body.include_test_data:
            query = query.where(production_knowledge())
        if not body.diagnostics:
            query = query.where(
                KnowledgeNode.source_status == "source_verified",
                KnowledgeNode.review_status.not_in(["rejected", "superseded"]),
            )
        if body.paper_id:
            query = query.where(KnowledgeNode.paper_id == body.paper_id)
        if body.search:
            query = query.outerjoin(
                KnowledgeDisplay, KnowledgeDisplay.node_id == KnowledgeNode.id
            ).where(
                or_(
                    KnowledgeNode.text.contains(body.search, autoescape=True),
                    sql_cast(KnowledgeNode.payload, String).contains(body.search, autoescape=True),
                    sql_cast(KnowledgeDisplay.data, String).contains(body.search, autoescape=True),
                    Paper.title.contains(body.search, autoescape=True),
                )
            )
        return query

    def paper_query(self, body: ProjectionQuery) -> Any:
        query = select(Paper).where(Paper.project_id == self.project_id)
        if "Paper" not in body.kinds:
            query = query.where(Paper.id == "")
        if body.paper_id:
            query = query.where(Paper.id == body.paper_id)
        if body.search:
            query = query.where(Paper.title.contains(body.search, autoescape=True))
        return query

    def neighbors(self, frontier: set[str], include_ai: bool, limit: int) -> set[str]:
        result: set[str] = set()
        # Every subsequent read is filtered by the project, even for malformed stored links.
        for model, source, target in [
            (SourceAssertion, SourceAssertion.source_id, SourceAssertion.target_id),
            (KnowledgeDependency, KnowledgeDependency.node_id, KnowledgeDependency.dependee_id),
            (RelationAssertion, RelationAssertion.source_id, RelationAssertion.target_id),
        ]:
            q = select(source, target).where(or_(source.in_(frontier), target.in_(frontier)))
            if model == RelationAssertion:
                q = q.where(
                    RelationAssertion.review_status.in_(
                        ["accepted", "proposed"] if include_ai else ["accepted"]
                    )
                )
            for a, b in self.session.execute(q.order_by(source, target).limit(limit * 4)):
                result.update([a, b])
        result.update(
            self.session.scalars(
                select(KnowledgeNode.paper_id).where(KnowledgeNode.id.in_(frontier))
            )
        )
        result.update(
            self.session.scalars(
                select(KnowledgeNode.id)
                .join(Paper)
                .where(
                    Paper.project_id == self.project_id,
                    KnowledgeNode.paper_id.in_(frontier),
                    KnowledgeNode.kind.in_(KINDS),
                    KnowledgeNode.source_status == "source_verified",
                    KnowledgeNode.review_status.not_in(["rejected", "superseded"]),
                )
                .order_by(KnowledgeNode.id)
                .limit(limit * 2)
            )
        )
        return result

    def project(self, body: ProjectionQuery) -> GraphProjection:
        revision = KnowledgeStore(self.session).graph_revision(self.project_id)
        fingerprint = digest({"project": self.project_id, **body.model_dump(exclude={"cursor"})})
        after = ""
        if body.cursor:
            try:
                cursor = json.loads(base64.urlsafe_b64decode(body.cursor).decode())
                if cursor["scope"] != fingerprint or cursor["revision"] != revision:
                    raise ValueError()
                after = str(cursor["after"])
            except (ValueError, KeyError, TypeError):
                raise KnowledgeError(
                    "REVISION_CONFLICT", "图谱或筛选已变化，请返回第一页"
                ) from None
        nq, pq = self.node_query(body), self.paper_query(body)
        if body.focus_id:
            root = self.session.scalar(
                nq.where(KnowledgeNode.id == body.focus_id)
            ) or self.session.scalar(pq.where(Paper.id == body.focus_id))
            if root is None:
                raise KnowledgeError("NODE_NOT_FOUND", "当前筛选下不存在焦点节点")
            selected: dict[str, Any] = {root.id: root}
            frontier = {root.id}
            more = False
            for _ in range(body.depth):
                candidates = self.neighbors(frontier, body.include_ai_candidates, body.limit)
                values = [
                    *self.session.scalars(
                        nq.where(KnowledgeNode.id.in_(candidates))
                        .order_by(KnowledgeNode.id)
                        .limit(body.limit + 1)
                    ),
                    *self.session.scalars(
                        pq.where(Paper.id.in_(candidates)).order_by(Paper.id).limit(body.limit + 1)
                    ),
                ]
                new = [x for x in sorted(values, key=lambda x: x.id) if x.id not in selected]
                free = body.limit - len(selected)
                more |= len(new) > free
                frontier = {x.id for x in new[:free]}
                selected.update({x.id: x for x in new[:free]})
                if not frontier:
                    break
            rows = list(selected.values())
            next_cursor = None
        else:
            values = [
                *self.session.scalars(
                    nq.where(KnowledgeNode.id > after)
                    .order_by(KnowledgeNode.id)
                    .limit(body.limit + 1)
                ),
                *self.session.scalars(
                    pq.where(Paper.id > after).order_by(Paper.id).limit(body.limit + 1)
                ),
            ]
            rows = sorted(values, key=lambda x: x.id)[: body.limit]
            more = len(values) > body.limit
            next_cursor = (
                base64.urlsafe_b64encode(
                    json.dumps(
                        {"scope": fingerprint, "revision": revision, "after": rows[-1].id}
                    ).encode()
                ).decode()
                if more
                else None
            )
        context_ids: list[str] = []
        if body.include_paper_context and "Paper" in body.kinds:
            parents = {r.paper_id for r in rows if isinstance(r, KnowledgeNode)} - {
                r.id for r in rows
            }
            context = list(
                self.session.scalars(
                    select(Paper)
                    .where(Paper.project_id == self.project_id, Paper.id.in_(parents))
                    .order_by(Paper.id)
                    .limit(24)
                )
            )
            context_ids = [p.id for p in context]
            rows.extend(context)
        nodes: list[ProjectionNode] = []
        for row in rows:
            paper = isinstance(row, Paper)
            data = {} if paper else display_data(self.session, row)
            zh = (
                (row.title if re.search(r"[\u4e00-\u9fff]", row.title) else "")
                if paper
                else str(data.get("label_zh") or "")
            )
            nodes.append(
                ProjectionNode(
                    id=row.id,
                    paper_id=row.id if paper else row.paper_id,
                    kind="Paper" if paper else cast(VisualKind, KINDS[row.kind]),
                    label_zh=zh[:28],
                    label_en=(row.title if paper else str(data.get("label_en") or row.text))[:80],
                    detail_ref=f"/api/v1/projects/{self.project_id}/graph/nodes/{row.id}",
                    source_status="source_document"
                    if paper
                    else (
                        "anchored" if row.source_status == "source_verified" else row.source_status
                    ),
                    review_status="unreviewed" if paper else row.review_status,
                    knowledge_origin="paper_author" if paper else row.origin,
                    badges=[] if paper else [*row.issues, *([] if zh else ["translation_missing"])],
                )
            )
        ids = {n.id for n in nodes}
        edges: list[ProjectionEdge] = []

        def edge(eid: str, a: str, b: str, relation: str, **extra: Any) -> None:
            if a in ids and b in ids:
                edges.append(
                    ProjectionEdge(
                        id=eid,
                        source=a,
                        target=b,
                        relation=relation,
                        label_zh=RELATIONS.get(relation, relation),
                        epistemic_status="source_reported",
                        review_status="unreviewed",
                        is_dashed=False,
                        **extra,
                    )
                )

        for row in rows:
            if isinstance(row, KnowledgeNode):
                edge(f"paper:{row.id}", row.paper_id, row.id, "REPORTS")
        for link in self.session.scalars(
            select(SourceAssertion)
            .where(
                SourceAssertion.project_id == self.project_id,
                SourceAssertion.source_id.in_(ids),
                SourceAssertion.target_id.in_(ids),
            )
            .limit(500)
        ):
            edge(
                link.id,
                link.source_id,
                link.target_id,
                link.relation,
                detail_ref=f"/api/v1/projects/{self.project_id}/graph/nodes/{link.source_id}",
            )
        for dependency in self.session.scalars(
            select(KnowledgeDependency)
            .where(KnowledgeDependency.node_id.in_(ids), KnowledgeDependency.dependee_id.in_(ids))
            .limit(500)
        ):
            if not any(
                e.source == dependency.node_id
                and e.target == dependency.dependee_id
                and e.relation == dependency.role
                for e in edges
            ):
                edge(
                    f"dep:{dependency.node_id}:{dependency.dependee_id}",
                    dependency.node_id,
                    dependency.dependee_id,
                    dependency.role,
                )
        for relation in self.session.scalars(
            select(RelationAssertion)
            .where(
                RelationAssertion.project_id == self.project_id,
                RelationAssertion.source_id.in_(ids),
                RelationAssertion.target_id.in_(ids),
                RelationAssertion.review_status.in_(
                    ["proposed", "accepted"] if body.include_ai_candidates else ["accepted"]
                ),
            )
            .limit(300)
        ):
            proposal = proposal_view(KnowledgeStore(self.session), relation)
            if proposal.stale or relation.relation_type == "NO_DECISION":
                continue
            accepted = relation.review_status == "accepted"
            edges.append(
                ProjectionEdge(
                    id=relation.id,
                    source=relation.source_id,
                    target=relation.target_id,
                    relation=relation.relation_type,
                    label_zh=RELATIONS.get(relation.relation_type, relation.relation_type),
                    epistemic_status="user_confirmed" if accepted else "model_inferred",
                    review_status=relation.review_status,
                    is_dashed=not accepted,
                    detail_ref=f"/api/v1/knowledge/relations/{relation.id}",
                )
            )
        return GraphProjection(
            project_id=self.project_id,
            graph_revision=revision,
            nodes=nodes,
            edges=edges,
            has_more=more,
            next_cursor=next_cursor,
            context_node_ids=context_ids,
        )

    def detail(self, node_id: str) -> ProjectionDetail:
        node = self.session.get(KnowledgeNode, node_id)
        paper = self.session.get(Paper, node.paper_id if node else node_id)
        if not paper or paper.project_id != self.project_id:
            raise KnowledgeError("NODE_NOT_FOUND", "项目中不存在该节点")
        versions = list(
            self.session.scalars(
                select(AttachmentRevision.id)
                .where(AttachmentRevision.paper_id == paper.id)
                .order_by(AttachmentRevision.created_at.desc())
            )
        )
        related_ids = {node_id}
        if node:
            for _ in range(3):
                related_ids.update(
                    self.session.scalars(
                        select(KnowledgeDependency.dependee_id)
                        .where(KnowledgeDependency.node_id.in_(related_ids))
                        .limit(128)
                    )
                )
                related_ids.update(
                    self.session.scalars(
                        select(KnowledgeDependency.node_id)
                        .join(KnowledgeNode, KnowledgeNode.id == KnowledgeDependency.node_id)
                        .where(
                            KnowledgeDependency.dependee_id.in_(related_ids),
                            KnowledgeNode.paper_id == paper.id,
                            KnowledgeNode.kind.in_(["experiment", "finding"]),
                        )
                        .limit(128)
                    )
                )
            query = select(KnowledgeNode).where(
                KnowledgeNode.paper_id == paper.id,
                KnowledgeNode.id.in_(related_ids),
                KnowledgeNode.id != node_id,
            )
        else:
            query = select(KnowledgeNode).where(KnowledgeNode.paper_id == paper.id)
        related = list(
            self.session.scalars(
                query.order_by(KnowledgeNode.created_at, KnowledgeNode.id).limit(128)
            )
        )
        evidence = (
            list(
                self.session.scalars(
                    select(EvidenceSpan)
                    .join(NodeEvidence)
                    .where(NodeEvidence.node_id == node_id)
                    .order_by(EvidenceSpan.page_index, EvidenceSpan.start_offset)
                    .limit(80)
                )
            )
            if node
            else []
        )
        for span in evidence:
            validate_evidence(self.session, span, node.document_version_id)  # type: ignore[union-attr]
        link = self.session.scalar(
            select(ZoteroLink).where(ZoteroLink.paper_id == paper.id).order_by(ZoteroLink.id)
        )
        zotero_url = None
        if link and re.fullmatch(r"[A-Z0-9]{8}", link.item_key):
            library = "library" if link.library_id.startswith("users/") else link.library_id
            if re.fullmatch(r"library|groups/[0-9]+", library):
                zotero_url = f"zotero://select/{library}/items/{link.item_key}"
        counts = dict(
            self.session.execute(
                select(KnowledgeNode.kind, func.count())
                .where(KnowledgeNode.paper_id == paper.id)
                .group_by(KnowledgeNode.kind)
            ).all()
        )
        return ProjectionDetail(
            id=node_id,
            paper_id=paper.id,
            title=paper.title,
            document_version_ids=versions,
            zotero_url=zotero_url,
            node=NodeView.model_validate(node) if node else None,
            display=display_data(self.session, node) if node else {},
            related=[NodeView.model_validate(n) for n in related],
            evidence=[EvidenceView.model_validate(e) for e in evidence],
            counts=counts,
            graph_revision=KnowledgeStore(self.session).graph_revision(self.project_id),
        )


def register_graph_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    @app.post("/api/v1/projects/{project_id}/graph/projection", response_model=GraphProjection)
    def projection(project_id: str, body: ProjectionQuery) -> GraphProjection:
        with Session(engine()) as session:
            return GraphProjectionService(session, project_id).project(body)

    @app.get("/api/v1/projects/{project_id}/graph/nodes/{node_id}", response_model=ProjectionDetail)
    def detail(project_id: str, node_id: str) -> ProjectionDetail:
        with Session(engine()) as session:
            return GraphProjectionService(session, project_id).detail(node_id)

    @app.get("/api/v1/projects/{project_id}/graph/layout", response_model=LayoutView)
    def layout(project_id: str) -> LayoutView:
        with Session(engine()) as session:
            require_project(session, project_id)
            row = session.get(GraphLayout, (project_id, "main"))
            return LayoutView(version=row.version, **row.data) if row else LayoutView()

    @app.post("/api/v1/projects/{project_id}/graph/layout", response_model=LayoutView)
    def save_layout(project_id: str, body: LayoutRequest) -> LayoutView:
        with Session(engine()) as session, session.begin():
            require_project(session, project_id)
            row = session.get(GraphLayout, (project_id, "main"))
            if body.expected_version != (row.version if row else 0):
                raise KnowledgeError("REVISION_CONFLICT", "布局已由其他窗口更新，请重新加载布局")
            ids = {p.node_id for p in body.positions}
            allowed = set(
                session.scalars(
                    select(KnowledgeNode.id)
                    .join(Paper)
                    .where(Paper.project_id == project_id, KnowledgeNode.id.in_(ids))
                )
            )
            allowed.update(
                session.scalars(
                    select(Paper.id).where(Paper.project_id == project_id, Paper.id.in_(ids))
                )
            )
            if allowed != ids:
                raise KnowledgeError("NODE_NOT_FOUND", "布局包含不属于项目的节点")
            positions = {p["node_id"]: p for p in row.data["positions"]} if row else {}
            positions.update({p.node_id: p.model_dump() for p in body.positions})
            if len(positions) > 2000:
                raise KnowledgeError("LAYOUT_TOO_LARGE", "布局超过 2000 个节点限制")
            data = {
                "positions": list(positions.values()),
                "zoom": body.zoom,
                "pan_x": body.pan_x,
                "pan_y": body.pan_y,
            }
            if row is None:
                row = GraphLayout(
                    project_id=project_id, view_id="main", version=0, data={}, updated_at=now()
                )
                session.add(row)
            row.version += 1
            row.data, row.updated_at = data, now()
            return LayoutView.model_validate({"version": row.version, **data})
