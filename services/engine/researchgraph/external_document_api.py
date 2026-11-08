"""Explicitly register external Markdown; local reading and model use stay separate."""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from researchgraph.external_document_contracts import (
    ExternalDocumentPreview,
    ExternalDocumentRegister,
)
from researchgraph.external_documents import (
    ExternalDocumentMutations,
    list_external_documents,
    preview_external_document,
    read_external_document,
)
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.storage import read_session

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)]


def register_external_document_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    @app.post("/api/v1/projects/{project_id}/external-documents/preview")
    def preview(
        project_id: str, body: ExternalDocumentPreview, include_personal: bool = False
    ) -> dict[str, Any]:
        with read_session(engine()) as session:
            return preview_external_document(
                session,
                project_id,
                body.root_id,
                body.relative_path,
                include_personal=include_personal,
            )

    @app.post("/api/v1/projects/{project_id}/external-documents")
    def register(
        project_id: str,
        body: ExternalDocumentRegister,
        idempotency_key: Key,
        include_personal: bool = False,
    ) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            return ExternalDocumentMutations(KnowledgeStore(session)).register(
                project_id, body, idempotency_key, include_personal=include_personal
            )

    @app.get("/api/v1/projects/{project_id}/external-documents")
    def documents(project_id: str, include_personal: bool = False) -> dict[str, Any]:
        with read_session(engine()) as session:
            return list_external_documents(session, project_id, include_personal=include_personal)

    @app.get("/api/v1/projects/{project_id}/external-documents/{document_id}")
    def document(
        project_id: str,
        document_id: str,
        version_id: str | None = None,
        include_personal: bool = False,
        purpose: Literal["local", "model"] = "local",
    ) -> dict[str, Any]:
        with read_session(engine()) as session:
            return read_external_document(
                session,
                project_id,
                document_id,
                version_id,
                include_personal=include_personal,
                purpose=purpose,
                require_local=True,
            )
