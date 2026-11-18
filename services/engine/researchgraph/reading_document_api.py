"""Local-only reading projections. No route here dispatches a Provider."""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError, StrictModel
from researchgraph.document_structure import current_structure
from researchgraph.reading_projection import (
    _scan_pdf,
    _scope,
    build_reading_document,
    prepare_reading_document,
    publish_reading_document,
)
from researchgraph.reading_projection_contracts import DocumentReadingView
from researchgraph.storage import database_busy, read_session
from researchgraph.structure_upgrade import ensure_structure_v2, local_content_was_cleared


class ReadingDocumentRefresh(StrictModel):
    document_version_id: str | None = None


def register_reading_document_api(
    app: FastAPI, get_engine: Callable[[], Engine], data_dir: Path
) -> None:
    @app.get("/api/v1/papers/{paper_id}/reading-document", response_model=DocumentReadingView)
    def reading_document(
        paper_id: str, document_version_id: str | None = Query(None)
    ) -> DocumentReadingView:
        # Upgrade legacy chapter trees before assembling the persisted reading
        # view, so the first ordinary open also fixes the outline.
        ensure_structure_v2(get_engine(), paper_id, document_version_id, data_dir)
        # Prepare against a committed read snapshot. Warm archives need no
        # writer; cold/old archives are assembled solely from stored blocks.
        engine = get_engine()
        with read_session(engine) as session:
            revision, _chunks, _sections, _spans = _scope(session, paper_id, document_version_id)
            if local_content_was_cleared(revision):
                raise HTTPException(
                    409,
                    {
                        "code": "LOCAL_CONTENT_CLEARED",
                        "message": "旧本地解析内容已清理；普通读取不会自动重新生成。",
                    },
                )
            prepared = prepare_reading_document(session, paper_id, document_version_id)
            artifact = current_structure(session, prepared.view.document_version_id)
            legacy_pending = bool(
                artifact is not None and not artifact.parser_version.endswith(";structure-v2")
            )
        if prepared.needs_write:
            try:
                # Archiving is optional for this response. A concurrent writer
                # must not turn a successful local read into DATABASE_BUSY.
                with (
                    Session(engine.execution_options(sqlite_busy_timeout_ms=0)) as session,
                    session.begin(),
                ):
                    publish_reading_document(session, prepared)
            except OperationalError as error:
                if not database_busy(error):
                    raise
        if legacy_pending:
            view = prepared.view.model_copy(deep=True)
            view.warnings = list(
                dict.fromkeys(
                    [
                        *view.warnings,
                        (
                            "当前文献仍使用旧章节解析；请检查已登记的原始 PDF，"
                            "系统将在下次读取时继续尝试本地升级。"
                        ),
                    ]
                )
            )
            return view
        return prepared.view

    @app.post(
        "/api/v1/papers/{paper_id}/reading-document/refresh", response_model=DocumentReadingView
    )
    def refresh_reading_document(
        paper_id: str, body: ReadingDocumentRefresh
    ) -> DocumentReadingView:
        # PDF I/O and parsing can take seconds. Keep them out of the writer
        # transaction; publish only after rechecking the selected source.
        with read_session(get_engine()) as session:
            revision, _chunks, _sections, _spans = _scope(
                session, paper_id, body.document_version_id
            )
            selected_id, source_hash = revision.id, revision.sha256
            fresh_scan = _scan_pdf(session, revision, data_dir)
        with Session(get_engine()) as session, session.begin():
            revision, _chunks, _sections, _spans = _scope(
                session, paper_id, body.document_version_id
            )
            if revision.id != selected_id or revision.sha256 != source_hash:
                raise KnowledgeError("READING_SOURCE_CHANGED", "文献版本已变化，请重新整理")
            return build_reading_document(
                session,
                paper_id,
                body.document_version_id,
                refresh=True,
                data_dir=data_dir,
                fresh_scan=fresh_scan,
            )
