"""Backend-owned backbone projection with closed edges and stable snapshot cursors."""

import base64
import json
from typing import cast

from sqlalchemy import select

from researchgraph.graph_contracts import (
    GraphProjection,
    ProjectionEdge,
    ProjectionNode,
    ProjectionQuery,
    VisualKind,
)
from researchgraph.graph_projection import GraphProjectionService, display_data
from researchgraph.knowledge_models import KnowledgeNode
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.knowledge_visibility import production_knowledge
from researchgraph.models import Paper
from researchgraph.reasoning_models import RelationAssertion


def project(service: GraphProjectionService, body: ProjectionQuery) -> GraphProjection:
    session, project_id = service.session, service.project_id
    reading = KnowledgeStore(session).reading()
    papers = list(
        session.scalars(select(Paper).where(Paper.project_id == project_id).order_by(Paper.id))
    )
    if body.paper_id:
        papers = [p for p in papers if p.id == body.paper_id]
        if not papers:
            raise KnowledgeError("PAPER_NOT_FOUND", "项目中不存在该论文")
    all_nodes: dict[str, ProjectionNode] = {}
    all_edges: dict[str, ProjectionEdge] = {}
    selections: dict[str, int] = {}
    gaps: list[str] = []
    query = select(KnowledgeNode.id).join(Paper).where(Paper.project_id == project_id)
    if not body.include_test_data:
        query = query.where(production_knowledge())
    production = set(session.scalars(query))

    def edge(eid: str, source: str, target: str, relation: str, label: str) -> None:
        all_edges[eid] = ProjectionEdge(
            id=eid,
            source=source,
            target=target,
            relation=relation,
            label_zh=label,
            epistemic_status="navigation",
            review_status="not_applicable",
            is_dashed=False,
        )

    for paper in papers:
        current = reading.current(paper.id)
        all_nodes[paper.id] = ProjectionNode(
            id=paper.id,
            paper_id=paper.id,
            kind="Paper",
            label_zh=paper.title,
            label_en=paper.title,
            detail_ref=f"/api/v1/projects/{project_id}/graph/nodes/{paper.id}",
            source_status="source_verified",
            review_status="not_applicable",
            knowledge_origin="source",
            badges=[],
            graph_role="paper",
        )
        if not current:
            gaps.append(f"{paper.id}: 尚未生成分层图谱，可基于已有候选整合")
            continue
        selections[paper.id] = current.revision
        gaps.extend(current.data["coverage_gaps"])
        nodes = {n.id: n for n in reading.nodes(current.document_version_id)}
        roles = {e["candidate_id"]: e["graph_role"] for e in current.data["entries"]}
        for unit in current.data["units"]:
            root = unit["root_claim_id"]
            if root not in production or not reading.source_valid(nodes[root]):
                gaps.append("部分核心来源已失效或属于隐藏测试数据，未在当前主图展示")
                continue
            ids = [root]
            if unit["id"] in body.expanded_unit_ids:
                ids += [m["member_id"] for m in unit["memberships"]]
            for nid in ids:
                if nid not in production or not reading.source_valid(nodes[nid]):
                    gaps.append("部分支撑来源失效，已保留历史并从主图隐藏")
                    continue
                node = nodes[nid]
                display = display_data(session, node)
                if nid not in all_nodes:
                    all_nodes[nid] = ProjectionNode(
                        id=nid,
                        paper_id=paper.id,
                        kind=cast(
                            VisualKind,
                            "ResearchQuestion"
                            if node.kind == "research_question"
                            else node.kind.title(),
                        ),
                        label_zh=str(display.get("label_zh", "")),
                        label_en=str(display.get("label_en", node.text)),
                        detail_ref=f"/api/v1/projects/{project_id}/graph/nodes/{nid}",
                        source_status=node.source_status,
                        review_status="not_applicable",
                        knowledge_origin=node.origin,
                        badges=list(unit.get("caveats", [])),
                        graph_role=roles[nid],
                        unit_ids=[],
                    )
                all_nodes[nid].unit_ids.append(unit["id"])
                if nid != root:
                    edge(f"member:{unit['id']}:{nid}", root, nid, "UNIT_MEMBER", "结论支撑")
            edge(f"core:{root}", paper.id, root, "HAS_CORE_CLAIM", "核心结论")
    if body.include_ai_candidates:
        for relation in session.scalars(
            select(RelationAssertion).where(RelationAssertion.project_id == project_id)
        ):
            if relation.source_id not in all_nodes or relation.target_id not in all_nodes:
                continue
            if relation.relation_type == "NO_DECISION" or relation.review_status in {
                "rejected",
                "superseded",
            }:
                continue
            all_edges[relation.id] = ProjectionEdge(
                id=relation.id,
                source=relation.source_id,
                target=relation.target_id,
                relation=relation.relation_type,
                label_zh=relation.relation_type,
                epistemic_status="model_inferred",
                review_status="not_applicable",
                is_dashed=True,
                detail_ref=f"/api/v1/knowledge/relations/{relation.id}",
            )
    primary = [
        n
        for n in all_nodes.values()
        if n.kind in body.kinds
        and (not body.search or body.search.casefold() in (n.label_en + n.label_zh).casefold())
    ]
    if body.focus_id:
        reached = {body.focus_id}
        for _ in range(body.depth):
            reached |= {e.target for e in all_edges.values() if e.source in reached} | {
                e.source for e in all_edges.values() if e.target in reached
            }
        primary = [n for n in primary if n.id in reached]
    primary.sort(key=lambda n: (n.paper_id, n.graph_role != "paper", n.id))
    signature = digest(
        [
            project_id,
            body.model_dump(exclude={"cursor"}),
            selections,
            [(n.id, n.unit_ids) for n in primary],
        ]
    )
    offset = 0
    if body.cursor:
        try:
            cursor = json.loads(base64.urlsafe_b64decode(body.cursor))
            if cursor["signature"] != signature or not isinstance(cursor["offset"], int):
                raise ValueError()
            offset = cursor["offset"]
            if not 0 <= offset <= len(primary):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise KnowledgeError("CURSOR_STALE", "图谱快照已改变，请重新分页") from None
    page = primary[offset : offset + body.limit]
    visible = {n.id for n in page}
    context = set()
    for _ in range(3):
        parents = {
            e.source
            for e in all_edges.values()
            if e.target in visible and e.epistemic_status == "navigation"
        }
        context |= parents - visible
        visible |= parents
    more = offset + body.limit < len(primary)
    cursor_out = (
        base64.urlsafe_b64encode(
            json.dumps({"signature": signature, "offset": offset + body.limit}).encode()
        ).decode()
        if more
        else None
    )
    return GraphProjection(
        contract_version="reading-projection-2.0",
        project_id=project_id,
        graph_revision=KnowledgeStore(session).graph_revision(project_id),
        selections=selections,
        nodes=page + [all_nodes[nid] for nid in sorted(context)],
        edges=[e for e in all_edges.values() if e.source in visible and e.target in visible],
        has_more=more,
        next_cursor=cursor_out,
        context_node_ids=sorted(context),
        coverage_gaps=list(dict.fromkeys(gaps)),
        build_state="partial" if gaps else "complete",
    )
