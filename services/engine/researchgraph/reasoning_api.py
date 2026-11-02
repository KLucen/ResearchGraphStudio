"""P3 read models and job submission; mutations stay in KnowledgeStore."""

from collections.abc import Callable
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Query
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from researchgraph.knowledge_api import Key
from researchgraph.knowledge_contracts import ModelRunView, NodeView
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.knowledge_visibility import production_knowledge
from researchgraph.model_settings import from_snapshot, snapshot_for
from researchgraph.models import Job, Paper, Project, now
from researchgraph.reasoning_context import candidates, node_context, pair_context, require_node
from researchgraph.reasoning_contracts import (
    AttemptView,
    CandidateList,
    CandidateRequest,
    ContextView,
    GraphView,
    InferenceRequest,
    ProposalDetail,
    ProposalView,
    ReasoningHistory,
    SemanticReviewRequest,
    SemanticReviewView,
)
from researchgraph.reasoning_models import (
    AlignmentCandidate,
    ReasoningAttempt,
    RelationAssertion,
    SemanticReview,
)
from researchgraph.reasoning_store import proposal_view
from researchgraph.schemas import JobView


def register_reasoning_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    from researchgraph.app import remember, remembered

    @app.post("/api/v1/knowledge/candidates", response_model=CandidateList)
    def retrieve(body: CandidateRequest) -> CandidateList:
        with Session(engine()) as session:
            return candidates(session, body)

    @app.get("/api/v1/knowledge/nodes/{node_id}/context", response_model=ContextView)
    def context(node_id: str) -> ContextView:
        with Session(engine()) as session:
            return ContextView.model_validate(node_context(session, require_node(session, node_id)))

    @app.post("/api/v1/knowledge/{workflow}/infer", response_model=JobView, status_code=202)
    def infer(
        workflow: Literal["relations", "alignments"], body: InferenceRequest, idempotency_key: Key
    ) -> JobView:
        mode = "relation" if workflow == "relations" else "alignment"
        with Session(engine()) as session, session.begin():
            key = "infer:" + idempotency_key
            request = {**body.model_dump(), "mode": mode}
            previous = remembered(session, key, request)
            if previous:
                return JobView.model_validate(previous)
            snapshot = pair_context(session, body.source_id, body.target_id, mode)
            payload = dict(request)
            if body.provider == "project":
                profile = snapshot_for(session, snapshot["project_id"], "reasoning")
                from_snapshot(profile, Path(str(engine().url.database)).parent, body.allow_network)
                payload["model_snapshot"] = profile
            job = Job(
                id=str(uuid4()),
                project_id=snapshot["project_id"],
                kind="knowledge_reason",
                payload=payload,
                status="queued",
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
            session.add(job)
            result = JobView.model_validate(job)
            remember(session, key, request, result.model_dump())
            return result

    @app.get("/api/v1/knowledge/nodes/{node_id}/reasoning", response_model=ReasoningHistory)
    @app.get("/api/v1/projects/{project_id}/reasoning", response_model=ReasoningHistory)
    def history(node_id: str | None = None, project_id: str | None = None) -> ReasoningHistory:
        with Session(engine()) as session:
            if node_id and session.get(KnowledgeNode, node_id) is None:
                raise KnowledgeError("NODE_NOT_FOUND", "知识节点不存在")
            if project_id and session.get(Project, project_id) is None:
                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            attempts = list(
                session.scalars(
                    select(ReasoningAttempt)
                    .where(
                        or_(
                            ReasoningAttempt.source_id == node_id,
                            ReasoningAttempt.target_id == node_id,
                        )
                        if node_id
                        else ReasoningAttempt.project_id == project_id
                    )
                    .order_by(ReasoningAttempt.created_at.desc(), ReasoningAttempt.id)
                    .limit(50)
                )
            )
            ids = [a.id for a in attempts]
            store = KnowledgeStore(session)
            return ReasoningHistory(
                attempts=[AttemptView.model_validate(a) for a in attempts],
                relations=[
                    proposal_view(store, p)
                    for p in session.scalars(
                        select(RelationAssertion).where(RelationAssertion.attempt_id.in_(ids))
                    )
                ],
                alignments=[
                    proposal_view(store, p)
                    for p in session.scalars(
                        select(AlignmentCandidate).where(AlignmentCandidate.attempt_id.in_(ids))
                    )
                ],
            )

    @app.get("/api/v1/knowledge/{workflow}/{proposal_id}", response_model=ProposalDetail)
    def detail(workflow: Literal["relations", "alignments"], proposal_id: str) -> ProposalDetail:
        with Session(engine()) as session:
            proposal = (
                session.get(RelationAssertion, proposal_id)
                if workflow == "relations"
                else session.get(AlignmentCandidate, proposal_id)
            )
            if proposal is None:
                raise KnowledgeError("PROPOSAL_NOT_FOUND", "候选不存在")
            attempt = session.get(ReasoningAttempt, proposal.attempt_id)
            assert attempt
            runs = [session.get(ModelRun, i) for i in attempt.model_run_ids]
            field = (
                SemanticReview.relation_id
                if workflow == "relations"
                else SemanticReview.alignment_id
            )
            return ProposalDetail(
                proposal=proposal_view(KnowledgeStore(session), proposal),
                attempt=AttemptView.model_validate(attempt),
                runs=[ModelRunView.model_validate(r) for r in runs if r],
                reviews=[
                    SemanticReviewView.model_validate(r)
                    for r in session.scalars(
                        select(SemanticReview)
                        .where(field == proposal_id)
                        .order_by(SemanticReview.created_at)
                    )
                ],
            )

    @app.post("/api/v1/knowledge/semantic-reviews", response_model=ProposalView)
    def review(body: SemanticReviewRequest, idempotency_key: Key) -> ProposalView:
        with Session(engine()) as session, session.begin():
            return ProposalView.model_validate(
                KnowledgeStore(session).review_semantic(body, "semantic-review:" + idempotency_key)
            )

    @app.get("/api/v1/graph/subgraph", response_model=GraphView)
    def graph(
        project_id: str,
        kind: Literal["claim", "concept", "method"] = "claim",
        status: Literal["all", "proposed", "accepted", "rejected"] = "all",
        cursor: str = "",
        limit: int = Query(60, ge=1, le=120),
        focus_id: str = "",
        include_test_data: bool = True,
    ) -> GraphView:
        with Session(engine()) as session:
            if session.get(Project, project_id) is None:
                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            query = (
                select(KnowledgeNode)
                .join(Paper, Paper.id == KnowledgeNode.paper_id)
                .where(Paper.project_id == project_id, KnowledgeNode.kind == kind)
            )
            if not include_test_data:
                query = query.where(production_knowledge())
            # Relation review is independent of the endpoint claims' review state.
            # Keep their nodes visible when filtering accepted/rejected relations.
            if focus_id:
                focus = session.get(KnowledgeNode, focus_id)
                paper = session.get(Paper, focus.paper_id) if focus else None
                if not paper or paper.project_id != project_id:
                    raise KnowledgeError("NODE_NOT_FOUND", "项目中不存在焦点节点")
                edges = session.scalars(
                    select(RelationAssertion)
                    .where(
                        RelationAssertion.project_id == project_id,
                        or_(
                            RelationAssertion.source_id == focus_id,
                            RelationAssertion.target_id == focus_id,
                        ),
                    )
                    .limit(120)
                ).all()
                ids = {focus_id} | {e.source_id for e in edges} | {e.target_id for e in edges}
                query = query.where(KnowledgeNode.id.in_(ids))
            query = (
                query.where(KnowledgeNode.id > cursor).order_by(KnowledgeNode.id).limit(limit + 1)
            )
            rows = list(session.scalars(query))
            next_cursor = rows[limit - 1].id if len(rows) > limit else None
            nodes = rows[:limit]
            ids = {n.id for n in nodes}
            store = KnowledgeStore(session)
            relations = [
                proposal_view(store, p)
                for p in session.scalars(
                    select(RelationAssertion)
                    .where(
                        RelationAssertion.source_id.in_(ids),
                        RelationAssertion.target_id.in_(ids),
                        RelationAssertion.project_id == project_id,
                    )
                    .order_by(RelationAssertion.created_at, RelationAssertion.id)
                    .limit(300)
                )
                if status == "all" or p.review_status == status
            ]
            return GraphView(
                nodes=[NodeView.model_validate(n) for n in nodes],
                relations=relations,
                papers={
                    p.id: p.title
                    for p in session.scalars(
                        select(Paper).where(Paper.id.in_({n.paper_id for n in nodes}))
                    )
                },
                next_cursor=next_cursor,
                graph_revision=store.graph_revision(project_id),
            )
