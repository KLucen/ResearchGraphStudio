"""Explicit save/export APIs. Model materialization is owned by the validated workflow API."""

import hmac
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header, Query
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.models import Project
from researchgraph.storage import read_session
from researchgraph.wiki_contracts import WikiPublishCommand, WikiRootCommand, WikiSaveCommand
from researchgraph.wiki_models import WikiPage, WikiPublication, WikiWriteRoot
from researchgraph.wiki_publish import (
    WikiPublisher,
    authorize_root,
    inspect_file,
    publication_view,
    revoke_root,
    root_view,
)
from researchgraph.wiki_store import WikiMutations, read_page

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)]


def register_wiki_api(
    app: FastAPI,
    engine: Callable[[], Engine],
    native_token: Callable[[], str] | None = None,
) -> None:
    @app.get("/api/v1/projects/{project_id}/wiki/pages")
    def pages(
        project_id: str,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=10, ge=1, le=100),
        include_personal: bool = False,
    ) -> dict[str, Any]:
        from researchgraph.query_models import QueryDocument

        with read_session(engine()) as session:
            if not session.get(Project, project_id):
                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            ids = list(
                session.scalars(
                    select(WikiPage.document_id)
                    .join(QueryDocument, QueryDocument.id == WikiPage.document_id)
                    .where(QueryDocument.project_id == project_id)
                    .order_by(WikiPage.created_at.desc(), WikiPage.document_id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            total = (
                session.scalar(
                    select(func.count())
                    .select_from(WikiPage)
                    .join(QueryDocument, QueryDocument.id == WikiPage.document_id)
                    .where(QueryDocument.project_id == project_id)
                )
                or 0
            )
            items = []
            for page_id in ids:
                view = read_page(session, project_id, page_id, include_personal=include_personal)
                items.append(
                    {
                        k: view[k]
                        for k in (
                            "page_id",
                            "title",
                            "head_version_id",
                            "saved_version_id",
                            "published_version_id",
                            "content_hash",
                            "content_state",
                            "state",
                            "file_state",
                        )
                    }
                )
            return {"items": items, "total": total, "offset": offset, "limit": limit}

    @app.get("/api/v1/projects/{project_id}/wiki/pages/{page_id}")
    def page(
        project_id: str,
        page_id: str,
        version_id: str | None = None,
        include_personal: bool = False,
        purpose: Literal["local", "model"] = "local",
    ) -> dict[str, Any]:
        with read_session(engine()) as session:
            return read_page(
                session,
                project_id,
                page_id,
                version_id,
                include_personal=include_personal,
                purpose=purpose,
                require_local=True,
            )

    @app.post("/api/v1/projects/{project_id}/wiki/pages/{page_id}/save")
    def save(
        project_id: str, page_id: str, body: WikiSaveCommand, idempotency_key: Key
    ) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            result = WikiMutations(KnowledgeStore(session)).save_draft(
                project_id, page_id, body, idempotency_key
            )
            return read_page(session, project_id, page_id, result["version_id"])

    @app.get("/api/v1/projects/{project_id}/wiki/roots")
    def roots(project_id: str) -> dict[str, Any]:
        with read_session(engine()) as session:
            return {
                "items": [
                    root_view(root)
                    for root in session.scalars(
                        select(WikiWriteRoot)
                        .where(WikiWriteRoot.project_id == project_id)
                        .order_by(WikiWriteRoot.created_at, WikiWriteRoot.id)
                    )
                ]
            }

    @app.post("/api/v1/projects/{project_id}/wiki/roots")
    def grant(
        project_id: str,
        body: WikiRootCommand,
        native: Annotated[str | None, Header(alias="X-ResearchGraph-Native-Token")] = None,
    ) -> dict[str, Any]:
        expected = native_token() if native_token else ""
        if not expected or not native or not hmac.compare_digest(expected, native):
            raise KnowledgeError(
                "WIKI_NATIVE_AUTHORIZATION_REQUIRED", "请使用原生目录选择器单独授权Wiki输出目录"
            )
        with Session(engine()) as session, session.begin():
            return authorize_root(KnowledgeStore(session), project_id, body.path)

    @app.post("/api/v1/projects/{project_id}/wiki/roots/{root_id}/revoke")
    def revoke(project_id: str, root_id: str, idempotency_key: Key) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            return revoke_root(KnowledgeStore(session), project_id, root_id)

    @app.post("/api/v1/projects/{project_id}/wiki/pages/{page_id}/publish")
    def publish(
        project_id: str, page_id: str, body: WikiPublishCommand, idempotency_key: Key
    ) -> dict[str, Any]:
        return WikiPublisher(engine()).publish(project_id, page_id, body, idempotency_key)

    @app.get("/api/v1/projects/{project_id}/wiki/publications")
    def publications(
        project_id: str,
        page_id: str | None = None,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=10, ge=1, le=100),
    ) -> dict[str, Any]:
        with read_session(engine()) as session:
            query = select(WikiPublication).where(WikiPublication.project_id == project_id)
            if page_id:
                query = query.where(WikiPublication.document_id == page_id)
            total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
            items = session.scalars(
                query.order_by(WikiPublication.created_at.desc(), WikiPublication.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return {
                "items": [publication_view(p) for p in items],
                "total": total,
                "offset": offset,
                "limit": limit,
            }

    @app.post("/api/v1/projects/{project_id}/wiki/publications/{operation_id}/recover")
    def recover(project_id: str, operation_id: str, idempotency_key: Key) -> dict[str, Any]:
        return WikiPublisher(engine()).recover(project_id, operation_id)

    @app.post("/api/v1/projects/{project_id}/wiki/pages/{page_id}/inspect-file")
    def inspect(project_id: str, page_id: str, idempotency_key: Key) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            return inspect_file(KnowledgeStore(session), project_id, page_id)
