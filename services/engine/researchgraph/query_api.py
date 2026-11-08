"""Project-scoped retrieval, grounded answers and explicit knowledge saving."""

import base64
import binascii
import json
from collections.abc import Callable
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, Header, Query
from pydantic import Field
from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from researchgraph.knowledge_contracts import StrictModel
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.model_adapters import with_documented_limits
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.model_settings import snapshot_for
from researchgraph.models import Job, now
from researchgraph.query_answer_contracts import QueryAnswerView
from researchgraph.query_browse import QueryBrowseRequest, QueryBrowseView, browse
from researchgraph.query_context import build_context, validate_context
from researchgraph.query_contracts import (
    QueryPreparationView,
    QueryRequest,
    QuerySaveCommand,
    SavedReadingAnnotation,
    SavedReadingRemoval,
)
from researchgraph.query_documents import read_passages
from researchgraph.query_local_access import assert_local_sources
from researchgraph.query_models import QueryOperation, QueryRun
from researchgraph.query_presentation import source_presentation
from researchgraph.query_retrieval import rebuild_index, retrieve, scope_versions
from researchgraph.query_source_scope import query_paper_ids
from researchgraph.schemas import JobView
from researchgraph.storage import read_session

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)]


class QueryRetrievalView(StrictModel):
    status: Literal["empty", "matched", "no_evidence"]
    hits: list[dict[str, Any]]
    graph: dict[str, Any]
    terms: list[str]
    independent_sources: list[str] = Field(default_factory=list)
    ranking_policy: str = "lexical-graph-1"
    scope_coverage: dict[str, Any] | None = None
    presentation: dict[str, Any] = Field(default_factory=dict)


class QueryValidationView(StrictModel):
    valid: bool
    input_hash: str
    reference_count: int
    status: str


class QueryDocumentList(StrictModel):
    items: list[dict[str, Any]]


class QueryGenerateRequest(StrictModel):
    allow_network: Literal[True]
    continue_requested: bool = False


class QueryHistoryItem(StrictModel):
    query_id: str
    question: str
    created_at: str
    status: str
    job_id: str | None = None
    paper_ids: list[str] = Field(default_factory=list)


class QueryHistoryList(StrictModel):
    items: list[QueryHistoryItem]
    next_cursor: str | None = None


def register_query_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    def check_scope(project_id: str, body: QueryRequest) -> None:
        if body.project_id != project_id:
            raise KnowledgeError("QUERY_SCOPE_MISMATCH", "请求项目与路径不一致")

    def search(session: Session, body: QueryRequest) -> dict[str, Any]:
        return retrieve(
            session,
            body.project_id,
            body.question,
            body.paper_ids,
            version_ids=body.document_version_ids,
            include_personal=body.include_personal,
            purpose=body.purpose,
            limit=body.limit,
            source_kinds=body.source_kinds,
            knowledge_kinds=body.knowledge_kinds,
        )

    def view(session: Session, run: QueryRun) -> QueryPreparationView:
        assert_local_sources(
            session,
            run.project_id,
            run.snapshot["retrieval"],
            run.snapshot["context"],
            include_personal=run.request["include_personal"],
        )
        return QueryPreparationView.model_validate(
            dict(
                query_id=run.id,
                status=run.status,
                input_hash=run.input_hash,
                snapshot=run.snapshot,
                error=run.error,
                presentation=source_presentation(
                    session, run.project_id, run.snapshot["retrieval"], run.snapshot["context"]
                ),
            )
        )

    @app.post("/api/v1/projects/{project_id}/query/search", response_model=QueryRetrievalView)
    def search_local(project_id: str, body: QueryRequest) -> QueryRetrievalView:
        check_scope(project_id, body)
        with Session(engine()) as session, session.begin():
            found = search(session, body)
            assert_local_sources(session, project_id, found, include_personal=body.include_personal)
            return QueryRetrievalView.model_validate(
                {**found, "presentation": source_presentation(session, project_id, found)}
            )

    @app.post("/api/v1/projects/{project_id}/query/search/page", response_model=QueryBrowseView)
    def search_page(project_id: str, body: QueryBrowseRequest) -> QueryBrowseView:
        with Session(engine()) as session, session.begin():
            return QueryBrowseView.model_validate(browse(session, project_id, body))

    @app.post("/api/v1/projects/{project_id}/query/index/rebuild")
    def reindex(project_id: str) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            return rebuild_index(session, project_id)

    @app.post("/api/v1/projects/{project_id}/query/prepare", response_model=QueryPreparationView)
    def prepare(project_id: str, body: QueryRequest, idempotency_key: Key) -> QueryPreparationView:
        check_scope(project_id, body)
        request = body.model_dump(mode="json")
        op_key = f"query-prepare:{project_id}:{idempotency_key}"
        with Session(engine()) as session, session.begin():
            remembered = session.get(QueryOperation, op_key)
            if remembered:
                if remembered.request_hash != digest(request):
                    raise KnowledgeError("IDEMPOTENCY_CONFLICT", "同一请求标识不能用于不同查询")
                run = session.get(QueryRun, remembered.response["query_id"])
                if run is None:
                    raise KnowledgeError("QUERY_NOT_FOUND", "查询记录不存在")
                # Cache and retry are permission-bound reads too. Never return a
                # formerly authorized note through an idempotency response.
                validate_context(
                    session,
                    run.snapshot["context"],
                    run.snapshot["retrieval"],
                    model_snapshot=run.snapshot.get("model"),
                )
                return view(session, run)
            sources = scope_versions(session, project_id, body.paper_ids, body.document_version_ids)
            found = search(session, body)
            model = None
            try:
                model = snapshot_for(session, project_id, "reasoning")
                # Freeze effective registered limits without probing the provider
                # or changing the profile/previous query snapshots.
                model["parameters"] = {
                    **model["parameters"],
                    "capabilities": with_documented_limits(
                        model["base_url"],
                        model["model"],
                        ModelCapabilities.model_validate(
                            model["parameters"].get("capabilities") or {}
                        ),
                    ).model_dump(),
                }
            except KnowledgeError as exc:
                if exc.code != "MODEL_NOT_CONFIGURED":
                    raise
            context = build_context(
                session,
                request,
                found,
                model_snapshot=model,
                include_layout=True,
                include_scientific_guidance=True,
            )
            validate_context(session, context, found, model_snapshot=model)
            snapshot = {
                "policy": "query-preparation-1",
                "request": request,
                "retrieval": found,
                "context": context,
                "model": model,
                "prompt": {"name": "query-context-1", "generation_enabled": False},
                "source_scope": [
                    {
                        "id": v.id,
                        "paper_id": v.paper_id,
                        "sha256": v.sha256,
                        "parser_version": v.parser_version,
                    }
                    for v in sources.values()
                ],
            }
            run = QueryRun(
                id=str(uuid4()),
                project_id=project_id,
                request=request,
                snapshot=snapshot,
                input_hash=context["input_hash"],
                status="prepared" if context["status"] == "ready" else "insufficient",
                error=None,
                created_at=now(),
                updated_at=now(),
            )
            session.add(run)
            session.flush()
            session.add(
                QueryOperation(
                    key=op_key, request_hash=digest(request), response={"query_id": run.id}
                )
            )
            KnowledgeStore(session).audit_event(
                project_id,
                "query.prepared",
                {"query_id": run.id, "input_hash": run.input_hash},
                trigger="query",
            )
            return view(session, run)

    def checked_run(session: Session, project_id: str, query_id: str) -> QueryRun:
        run = session.get(QueryRun, query_id)
        if run is None or run.project_id != project_id:
            raise KnowledgeError("QUERY_NOT_FOUND", "项目中不存在该查询")
        validate_context(
            session,
            run.snapshot["context"],
            run.snapshot["retrieval"],
            model_snapshot=run.snapshot.get("model"),
        )
        return run

    @app.get(
        "/api/v1/projects/{project_id}/query/runs/{query_id}", response_model=QueryPreparationView
    )
    def get_run(project_id: str, query_id: str) -> QueryPreparationView:
        with read_session(engine()) as session:
            return view(session, checked_run(session, project_id, query_id))

    @app.post(
        "/api/v1/projects/{project_id}/query/runs/{query_id}/validate",
        response_model=QueryValidationView,
    )
    def validate_run(project_id: str, query_id: str) -> QueryValidationView:
        with read_session(engine()) as session:
            run = checked_run(session, project_id, query_id)
            return QueryValidationView.model_validate(
                validate_context(
                    session,
                    run.snapshot["context"],
                    run.snapshot["retrieval"],
                    model_snapshot=run.snapshot.get("model"),
                )
            )

    @app.get("/api/v1/projects/{project_id}/query/documents", response_model=QueryDocumentList)
    def documents(project_id: str, include_personal: bool = False) -> QueryDocumentList:
        with read_session(engine()) as session:
            scope_versions(session, project_id, [])
            return QueryDocumentList(
                items=read_passages(session, project_id, include_personal=include_personal)
            )

    @app.get("/api/v1/projects/{project_id}/query/runs", response_model=QueryHistoryList)
    def history(
        project_id: str, cursor: str | None = None, limit: int = Query(default=20, ge=1, le=50)
    ) -> QueryHistoryList:
        with read_session(engine()) as session:
            scope_versions(session, project_id, [])
            query = select(QueryRun).where(QueryRun.project_id == project_id)
            if cursor:
                try:
                    if len(cursor) > 500:
                        raise ValueError("cursor too long")
                    data = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
                    if (
                        not isinstance(data, list)
                        or len(data) != 2
                        or not all(isinstance(v, str) and v for v in data)
                    ):
                        raise ValueError("cursor shape")
                    query = query.where(
                        or_(
                            QueryRun.created_at < data[0],
                            and_(QueryRun.created_at == data[0], QueryRun.id < data[1]),
                        )
                    )
                except (ValueError, UnicodeError, binascii.Error):
                    raise KnowledgeError("QUERY_CURSOR_INVALID", "查询历史游标无效") from None
            runs = list(
                session.scalars(
                    query.order_by(QueryRun.created_at.desc(), QueryRun.id.desc()).limit(limit + 1)
                )
            )
            items = []
            jobs = list(
                session.scalars(
                    select(Job)
                    .where(Job.project_id == project_id, Job.kind == "query_answer")
                    .order_by(Job.created_at.desc(), Job.id.desc())
                )
            )
            latest_jobs: dict[str, Job] = {}
            for candidate_job in jobs:
                latest_jobs.setdefault(
                    str((candidate_job.payload or {}).get("query_id", "")), candidate_job
                )
            for run in runs[:limit]:
                job = latest_jobs.get(run.id)
                items.append(
                    QueryHistoryItem(
                        query_id=run.id,
                        question=run.request["question"],
                        created_at=run.created_at,
                        status=job.status if job else run.status,
                        job_id=job.id if job else None,
                        paper_ids=query_paper_ids(session, run),
                    )
                )
            last = runs[limit - 1] if len(runs) > limit else None
            next_cursor = (
                base64.urlsafe_b64encode(json.dumps([last.created_at, last.id]).encode()).decode()
                if last
                else None
            )
            return QueryHistoryList(items=items, next_cursor=next_cursor)

    @app.post(
        "/api/v1/projects/{project_id}/query/runs/{query_id}/generate",
        response_model=JobView,
        status_code=202,
    )
    def generate(
        project_id: str, query_id: str, body: QueryGenerateRequest, idempotency_key: Key
    ) -> JobView:
        from researchgraph.query_answers import enqueue

        with Session(engine()) as session, session.begin():
            return JobView.model_validate(
                enqueue(
                    session,
                    query_id,
                    project_id,
                    idempotency_key,
                    continue_requested=body.continue_requested,
                )
            )

    @app.get(
        "/api/v1/projects/{project_id}/query/runs/{query_id}/answer", response_model=QueryAnswerView
    )
    def answer(project_id: str, query_id: str) -> QueryAnswerView:
        from researchgraph.query_answers import get_answer

        with read_session(engine()) as session:
            run = session.get(QueryRun, query_id)
            if run is None or run.project_id != project_id:
                raise KnowledgeError("QUERY_NOT_FOUND", "项目中不存在该查询")
            assert_local_sources(
                session,
                project_id,
                run.snapshot["retrieval"],
                run.snapshot["context"],
                include_personal=run.request["include_personal"],
            )
            return get_answer(session, project_id, query_id)

    @app.post("/api/v1/projects/{project_id}/query/runs/{query_id}/save")
    def save_answer(
        project_id: str, query_id: str, body: QuerySaveCommand, idempotency_key: Key
    ) -> Any:
        if body.source_query_id != query_id:
            raise KnowledgeError("QUERY_SCOPE_MISMATCH", "保存对象与路径不一致")
        with Session(engine()) as session, session.begin():
            return KnowledgeStore(session).save_query(body, idempotency_key, project_id=project_id)

    @app.get("/api/v1/projects/{project_id}/query/saved")
    def saved(project_id: str, include_personal: bool = False) -> Any:
        from researchgraph.query_save import list_saved

        with read_session(engine()) as session:
            scope_versions(session, project_id, [])
            return {"items": list_saved(session, project_id, include_personal=include_personal)}

    @app.get("/api/v1/projects/{project_id}/query/saved/{saved_id}")
    def saved_detail(project_id: str, saved_id: str, include_personal: bool = False) -> Any:
        from researchgraph.query_save import get_saved

        with read_session(engine()) as session:
            return get_saved(session, project_id, saved_id, include_personal=include_personal)

    @app.put("/api/v1/projects/{project_id}/query/saved/{saved_id}/annotation")
    def annotate_saved(
        project_id: str,
        saved_id: str,
        body: SavedReadingAnnotation,
        idempotency_key: Key,
        include_personal: bool = False,
    ) -> Any:
        with Session(engine()) as session, session.begin():
            return KnowledgeStore(session).annotate_saved_query(
                project_id,
                saved_id,
                body,
                idempotency_key,
                include_personal=include_personal,
            )

    @app.post("/api/v1/projects/{project_id}/query/saved/{saved_id}/remove")
    def remove_saved(
        project_id: str,
        saved_id: str,
        body: SavedReadingRemoval,
        idempotency_key: Key,
        include_personal: bool = False,
    ) -> Any:
        with Session(engine()) as session, session.begin():
            return KnowledgeStore(session).remove_saved_query(
                project_id,
                saved_id,
                body,
                idempotency_key,
                include_personal=include_personal,
            )

    @app.get("/api/v1/projects/{project_id}/query/derived-graph")
    def derived(project_id: str, include_personal: bool = False) -> Any:
        from researchgraph.query_save import derived_graph

        with read_session(engine()) as session:
            return derived_graph(session, project_id, include_personal=include_personal)
