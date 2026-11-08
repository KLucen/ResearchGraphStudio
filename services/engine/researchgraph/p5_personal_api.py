"""Metadata/preview catalog and independent annotation-comment model consent."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import FastAPI, Header, Query
from pydantic import Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from researchgraph.knowledge_contracts import StrictModel
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.p5_personal import personal_catalog, set_annotation_grant
from researchgraph.storage import read_session


class AnnotationGrantRequest(StrictModel):
    allow_model: bool
    allow_local: bool | None = None
    expected_revision: int = Field(ge=0, strict=True)


def register_p5_personal_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    base = "/api/v1/projects/{project_id}/p5"

    @app.get(base + "/personal-sources")
    def catalog(
        project_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)
    ) -> dict[str, Any]:
        with read_session(engine()) as session:
            return personal_catalog(session, project_id, page=page, page_size=page_size)

    @app.post(base + "/annotations/{annotation_id}/grant")
    def grant(
        project_id: str,
        annotation_id: str,
        body: AnnotationGrantRequest,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=8, max_length=120)
        ],
    ) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            return set_annotation_grant(
                KnowledgeStore(session),
                project_id,
                annotation_id,
                body.allow_model,
                body.expected_revision,
                idempotency_key,
                allow_local=body.allow_local,
            )
