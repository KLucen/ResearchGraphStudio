"""Local-only reading projections. No route here dispatches a Provider."""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Query
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from researchgraph.core import StrictModel
from researchgraph.reading_projection import build_reading_document
from researchgraph.reading_projection_contracts import DocumentReadingView


class ReadingDocumentRefresh(StrictModel):
    document_version_id: str | None = None


def register_reading_document_api(
    app: FastAPI, get_engine: Callable[[], Engine], data_dir: Path
) -> None:
    @app.get("/api/v1/papers/{paper_id}/reading-document", response_model=DocumentReadingView)
    def reading_document(
        paper_id: str, document_version_id: str | None = Query(None)
    ) -> DocumentReadingView:
        # A projection is local derived data, persisted on first read. Raw
        # Chunks, source spans, sections and previous model results stay intact.
        with Session(get_engine()) as session, session.begin():
            return build_reading_document(session, paper_id, document_version_id, data_dir=data_dir)

    @app.post(
        "/api/v1/papers/{paper_id}/reading-document/refresh", response_model=DocumentReadingView
    )
    def refresh_reading_document(
        paper_id: str, body: ReadingDocumentRefresh
    ) -> DocumentReadingView:
        with Session(get_engine()) as session, session.begin():
            return build_reading_document(
                session,
                paper_id,
                body.document_version_id,
                refresh=True,
                data_dir=data_dir,
            )
