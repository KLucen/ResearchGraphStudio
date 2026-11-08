"""Complete, paginated local results, independent of frozen model contexts."""

from typing import Any, Literal

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.graph_contracts import ProjectionQuery
from researchgraph.graph_projection import GraphProjectionService
from researchgraph.knowledge_contracts import StrictModel
from researchgraph.knowledge_models import EvidenceSpan, NodeEvidence
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import Paper
from researchgraph.query_contracts import QueryRequest
from researchgraph.query_local_access import assert_local_sources
from researchgraph.query_presentation import source_presentation
from researchgraph.query_retrieval import retrieve
from researchgraph.reading_projection import collect_backbone


class QueryBrowseRequest(StrictModel):
    request: QueryRequest
    page: int = Field(default=1, ge=1)
    page_size: Literal[10] = 10
    display_paper_ids: list[str] = Field(default_factory=list)
    expected_result_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def distinct_papers(self) -> "QueryBrowseRequest":
        if len(set(self.display_paper_ids)) != len(self.display_paper_ids) or any(
            not value.strip() for value in self.display_paper_ids
        ):
            raise ValueError("display papers must contain distinct nonempty IDs")
        return self


class QueryBrowseView(StrictModel):
    status: Literal["empty", "matched", "no_evidence"]
    hits: list[dict[str, Any]]
    presentation: dict[str, Any]
    total: int
    page: int
    page_size: Literal[10] = 10
    total_pages: int
    result_hash: str
    graph_node_count: int
    independent_sources: list[str] = Field(default_factory=list)
    scope_coverage: dict[str, Any] | None = None


def graph_membership(session: Session, project_id: str) -> tuple[dict[str, str], int]:
    """Collect the full default backbone once, before its canvas pagination."""
    service = GraphProjectionService(session, project_id)
    body = ProjectionQuery(view="paper_backbone", limit=120)
    nodes, _, _, _, _ = collect_backbone(service, body)
    return (
        {node.id: node.graph_role for node in nodes.values()},
        KnowledgeStore(session).graph_revision(project_id),
    )


def browse(session: Session, project_id: str, body: QueryBrowseRequest) -> dict[str, Any]:
    if body.request.project_id != project_id:
        raise KnowledgeError("QUERY_SCOPE_MISMATCH", "请求项目与路径不一致")
    papers = {p.id for p in session.scalars(select(Paper).where(Paper.project_id == project_id))}
    if set(body.display_paper_ids) - papers:
        raise KnowledgeError("QUERY_SCOPE_MISMATCH", "显示论文不属于本项目")
    request = body.request
    # No result-count cap here. The separate prepare endpoint keeps its original
    # frozen limit and complete graph/evidence context, unaffected by UI pages.
    found = retrieve(
        session,
        project_id,
        request.question,
        request.paper_ids,
        version_ids=request.document_version_ids,
        include_personal=request.include_personal,
        purpose=request.purpose,
        limit=None,
        source_kinds=request.source_kinds,
        knowledge_kinds=request.knowledge_kinds,
        include_comparison=False,
    )
    assert_local_sources(session, project_id, found, include_personal=request.include_personal)
    presentation = source_presentation(session, project_id, found)
    members, graph_revision = graph_membership(session, project_id)
    evidence_nodes: dict[str, set[str]] = {}
    chunk_nodes: dict[str, set[str]] = {}
    for link, span in session.execute(
        select(NodeEvidence, EvidenceSpan)
        .join(EvidenceSpan, EvidenceSpan.id == NodeEvidence.evidence_id)
        .where(NodeEvidence.node_id.in_(members))
    ):
        evidence_nodes.setdefault(link.evidence_id, set()).add(link.node_id)
        chunk_nodes.setdefault(span.paragraph_id, set()).add(link.node_id)
    for hit in found["hits"]:
        kind, oid = hit["source_kind"], hit["object_id"]
        mapped: set[str] = set()
        representation: str | None = None
        state = "retrieval_only"
        if kind in {"knowledge", "paper"}:
            if oid in members:
                state, representation, mapped = "in_graph", "node", {oid}
        elif kind in {"chunk", "evidence"}:
            mapped = (chunk_nodes if kind == "chunk" else evidence_nodes).get(oid, set())
            if mapped:
                state, representation = "in_graph", "evidence"
        else:
            state = "not_applicable"
        presentation["hits"][hit["entry_id"]]["graph_presence"] = {
            "state": state,
            "representation": representation,
            "node_ids": sorted(mapped),
            "graph_roles": sorted({members[nid] for nid in mapped}),
            "graph_revision": graph_revision,
        }
    # Include all current ranked content and membership before display filtering.
    # Permission revocation or a changed source cannot silently shift later pages.
    result_hash = digest(
        {
            "policy": "query-browse-1",
            "request": request.model_dump(mode="json"),
            "retrieval": found,
            "presentation": presentation,
            "display_paper_ids": sorted(body.display_paper_ids),
        }
    )
    if body.expected_result_hash and body.expected_result_hash != result_hash:
        raise KnowledgeError("QUERY_RESULTS_CHANGED", "检索来源或图谱已变化，请刷新后从第一页查看")
    wanted = set(body.display_paper_ids)
    hits = found["hits"]
    if wanted:
        hits = [h for h in hits if wanted & set(presentation["hits"][h["entry_id"]]["paper_ids"])]
    total = len(hits)
    total_pages = max(1, (total + 9) // 10)
    if body.page > total_pages:
        raise KnowledgeError("QUERY_PAGE_INVALID", "检索页码超出范围，请返回第一页")
    page_hits = hits[(body.page - 1) * 10 : body.page * 10]
    return {
        "status": found["status"]
        if hits
        else "empty"
        if not request.question.strip()
        else "no_evidence",
        "hits": page_hits,
        "presentation": {
            "hits": {h["entry_id"]: presentation["hits"][h["entry_id"]] for h in page_hits},
            "references": {},
        },
        "total": total,
        "page": body.page,
        "page_size": 10,
        "total_pages": total_pages,
        "result_hash": result_hash,
        "graph_node_count": len(found["graph"]["nodes"]),
        "independent_sources": found.get("independent_sources", []),
        "scope_coverage": found.get("scope_coverage"),
    }
