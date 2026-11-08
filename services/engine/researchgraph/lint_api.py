"""Explicit deterministic Lint scans. Reading reports never advances or calls models."""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header, Query
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.external_documents import lint_document_metadata
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.lint_contracts import (
    LintAdvance,
    LintDocumentPage,
    LintIssuePage,
    LintRequest,
    LintRunPage,
    LintRunView,
)
from researchgraph.lint_service import dependencies, get_run, list_issues, list_runs
from researchgraph.models import Project
from researchgraph.query_documents import validate_dependencies
from researchgraph.query_models import QueryDocument, QueryDocumentVersion, QueryPassage
from researchgraph.storage import read_session

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def register_lint_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    @app.get("/api/v1/projects/{project_id}/lint/documents", response_model=LintDocumentPage)
    def documents(
        project_id: str,
        page: Page = 1,
        page_size: PageSize = 10,
        include_personal: bool = False,
    ) -> dict[str, Any]:
        # Inspection must also offer broken and unsaved documents. The Query adapter
        # intentionally omits those and cannot serve as the Lint scope catalogue.
        with read_session(engine()) as session:
            if not session.get(Project, project_id):
                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            items = []
            for document in session.scalars(
                select(QueryDocument)
                .where(QueryDocument.project_id == project_id)
                .order_by(QueryDocument.created_at.desc(), QueryDocument.id.desc())
            ):
                if document.kind == "external":
                    # External sources have a separate authorization-aware catalogue.
                    continue
                versions = list(
                    session.scalars(
                        select(QueryDocumentVersion)
                        .where(QueryDocumentVersion.document_id == document.id)
                        .order_by(QueryDocumentVersion.revision.desc())
                    )
                )
                version = versions[0] if versions else None
                passages = list(
                    session.scalars(
                        select(QueryPassage).where(
                            QueryPassage.version_id.in_([v.id for v in versions])
                        )
                    )
                )
                permitted = True
                for passage in passages:
                    personal = passage.attribution == "user_view" or any(
                        dependency.get("type") in {"note", "annotation", "external"}
                        for dependency in passage.dependencies
                    )
                    if personal and not include_personal:
                        permitted = False
                        break
                    state = validate_dependencies(
                        session, project_id, passage.dependencies, include_personal, "local"
                    )
                    if any("NOT_AUTHORIZED" in issue for issue in state["issues"]):
                        permitted = False
                        break
                if not permitted:
                    continue
                items.append(
                    {
                        "id": document.id,
                        "title": document.title,
                        "kind": document.kind,
                        "status": version.state if version else "missing_version",
                        "current_version_id": document.current_version_id,
                        "latest_version_id": version.id if version else None,
                    }
                )
            items.extend(lint_document_metadata(session, project_id, include_personal))
            offset = (page - 1) * page_size
            return {
                "items": items[offset : offset + page_size],
                "total": len(items),
                "page": page,
                "page_size": page_size,
            }

    @app.post("/api/v1/projects/{project_id}/lint/runs", response_model=LintRunView)
    def start(project_id: str, body: LintRequest, idempotency_key: Key) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            return KnowledgeStore(session).lint().start(project_id, body, idempotency_key)

    @app.get("/api/v1/projects/{project_id}/lint/runs", response_model=LintRunPage)
    def history(project_id: str, page: Page = 1, page_size: PageSize = 10) -> dict[str, Any]:
        with read_session(engine()) as session, session.begin():
            return list_runs(session, project_id, page=page, page_size=page_size)

    @app.get("/api/v1/projects/{project_id}/lint/runs/{run_id}", response_model=LintRunView)
    def report(project_id: str, run_id: str) -> dict[str, Any]:
        with read_session(engine()) as session, session.begin():
            return get_run(session, project_id, run_id)

    @app.get(
        "/api/v1/projects/{project_id}/lint/runs/{run_id}/issues", response_model=LintIssuePage
    )
    def issues(
        project_id: str,
        run_id: str,
        page: Page = 1,
        page_size: PageSize = 10,
        severity: Literal["error", "warning", "info"] | None = None,
        category: str | None = None,
        lifecycle: Literal["new", "persistent", "resolved", "input_stale"] | None = None,
        code: str | None = None,
        paper_id: str | None = None,
    ) -> dict[str, Any]:
        with read_session(engine()) as session, session.begin():
            return list_issues(
                session,
                project_id,
                run_id,
                page=page,
                page_size=page_size,
                severity=severity,
                category=category,
                lifecycle=lifecycle,
                code=code,
                paper_id=paper_id,
            )

    @app.post(
        "/api/v1/projects/{project_id}/lint/runs/{run_id}/advance", response_model=LintRunView
    )
    def advance(
        project_id: str, run_id: str, body: LintAdvance, idempotency_key: Key
    ) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            return (
                KnowledgeStore(session)
                .lint()
                .advance(project_id, run_id, body.max_items, idempotency_key)
            )

    @app.post("/api/v1/projects/{project_id}/lint/runs/{run_id}/cancel", response_model=LintRunView)
    def cancel(project_id: str, run_id: str, idempotency_key: Key) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            return KnowledgeStore(session).lint().cancel(project_id, run_id, idempotency_key)

    @app.post("/api/v1/projects/{project_id}/dependencies/rebuild")
    @app.post("/api/v1/projects/{project_id}/lint/dependencies/rebuild")
    def rebuild(project_id: str, idempotency_key: Key) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            return KnowledgeStore(session).lint().rebuild_dependencies(project_id, idempotency_key)

    @app.get("/api/v1/projects/{project_id}/dependencies")
    @app.get("/api/v1/projects/{project_id}/lint/dependencies")
    def dependency_list(
        project_id: str,
        object_type: str | None = None,
        object_id: str | None = None,
        direction: Literal["dependents", "dependencies"] = "dependents",
        page: Page = 1,
        page_size: PageSize = 10,
    ) -> dict[str, Any]:
        with read_session(engine()) as session, session.begin():
            return dependencies(
                session,
                project_id,
                object_type=object_type,
                object_id=object_id,
                direction=direction,
                page=page,
                page_size=page_size,
            )
