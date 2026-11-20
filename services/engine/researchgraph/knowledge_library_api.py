"""Read, collect, organize and export the local research knowledge library."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, Header, Query
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError
from researchgraph.knowledge_connection_models import KnowledgeConnectionReport
from researchgraph.knowledge_library import (
    PERSONAL_LIBRARY_ID,
    collect_overview,
    collection_view,
    ensure_library,
    library_error,
    library_view,
    paper_view,
    version_view,
)
from researchgraph.knowledge_library_contracts import (
    CollectionCreate,
    CollectionList,
    CollectionView,
    CollectOverview,
    KnowledgeVersionView,
    LibraryActionResult,
    LibraryExport,
    LibraryLayoutView,
    LibraryPaperList,
    LibraryPaperUpdate,
    LibraryPaperView,
    LibrarySettings,
    LibraryView,
)
from researchgraph.knowledge_library_models import (
    KnowledgeCollection,
    KnowledgeCollectionMember,
    KnowledgeLibrary,
    KnowledgeLibraryView,
    LibraryPaper,
    LibraryPaperSourceLink,
    PaperKnowledgeVersion,
)
from researchgraph.models import Idempotency, now
from researchgraph.storage import read_session

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)]


def _replay(db: Session, key: str, body: dict[str, Any]) -> dict[str, Any] | None:
    row = db.get(Idempotency, key)
    if row is None:
        return None
    request_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if row.request_hash != request_hash:
        raise library_error(409, "IDEMPOTENCY_CONFLICT", "同一操作标识不能用于不同内容")
    return row.response


def _remember(db: Session, key: str, body: dict[str, Any], response: dict[str, Any]) -> None:
    db.add(
        Idempotency(
            key=key,
            request_hash=hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
            response=response,
        )
    )


def _paper(db: Session, library_paper_id: str) -> LibraryPaper:
    result = db.get(LibraryPaper, library_paper_id)
    if result is None or result.library_id != PERSONAL_LIBRARY_ID:
        raise library_error(404, "LIBRARY_PAPER_NOT_FOUND", "知识库论文不存在")
    return result


def _collection(db: Session, collection_id: str) -> KnowledgeCollection:
    result = db.get(KnowledgeCollection, collection_id)
    if result is None or result.library_id != PERSONAL_LIBRARY_ID:
        raise library_error(404, "COLLECTION_NOT_FOUND", "知识专题不存在")
    return result


def _backup(engine: Engine, directory: Path | Callable[[], Path] | None) -> None:
    source = engine.url.database
    if not source or source == ":memory:":
        return
    root = directory() if callable(directory) else directory or Path(source).parent
    backups = root / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    with (
        sqlite3.connect(source) as current,
        sqlite3.connect(backups / f"before-knowledge-purge-{uuid4()}.sqlite3") as target,
    ):
        current.backup(target)


def register_knowledge_library_api(
    app: FastAPI,
    engine: Callable[[], Engine],
    data_dir: Path | Callable[[], Path] | None = None,
    *_compatibility: Any,
) -> None:
    prefix = "/api/v1/knowledge"

    @app.get(prefix + "/library", response_model=LibraryView)
    def get_library() -> LibraryView:
        with read_session(engine()) as db:
            return library_view(db.get(KnowledgeLibrary, PERSONAL_LIBRARY_ID))

    @app.patch(prefix + "/library", response_model=LibraryView)
    def update_library(body: LibrarySettings, idempotency_key: Key) -> LibraryView:
        payload = body.model_dump()
        key = "knowledge-settings:" + idempotency_key
        with Session(engine()) as db, db.begin():
            previous = _replay(db, key, payload)
            if previous:
                return LibraryView.model_validate(previous)
            if body.scope == "collection":
                _collection(db, body.collection_id or "")
            library = ensure_library(db)
            library.settings_json = payload
            library.updated_at = now()
            response = library_view(library)
            _remember(db, key, payload, response.model_dump())
            return response

    @app.get(prefix + "/papers", response_model=LibraryPaperList)
    def list_papers(
        project_id: str | None = None,
        collection_id: str | None = None,
        search: str = Query(default="", max_length=300),
        include_archived: bool = False,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> LibraryPaperList:
        with read_session(engine()) as db:
            query = select(LibraryPaper).where(LibraryPaper.library_id == PERSONAL_LIBRARY_ID)
            if not include_archived:
                query = query.where(LibraryPaper.archived.is_(False))
            if project_id:
                query = query.where(
                    LibraryPaper.id.in_(
                        select(LibraryPaperSourceLink.library_paper_id).where(
                            LibraryPaperSourceLink.project_id == project_id
                        )
                    )
                )
            if collection_id:
                query = query.where(
                    LibraryPaper.id.in_(
                        select(KnowledgeCollectionMember.library_paper_id).where(
                            KnowledgeCollectionMember.collection_id == collection_id
                        )
                    )
                )
            if search.strip():
                # instr treats %, _ and quotes as literal text, not SQL wildcards.
                query = query.where(
                    (func.instr(func.lower(LibraryPaper.title), search.strip().lower()) > 0)
                    | (func.instr(func.lower(LibraryPaper.note), search.strip().lower()) > 0)
                )
            total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
            rows = db.scalars(
                query.order_by(LibraryPaper.updated_at.desc(), LibraryPaper.id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return LibraryPaperList(items=[paper_view(db, paper) for paper in rows], total=total)

    @app.post(prefix + "/papers/collect", response_model=LibraryPaperView)
    def collect(body: CollectOverview, idempotency_key: Key) -> LibraryPaperView:
        payload = body.model_dump()
        key = "knowledge-collect:" + idempotency_key
        with Session(engine()) as db, db.begin():
            previous = _replay(db, key, payload)
            if previous:
                # Replays validate current visibility instead of reviving an
                # explicitly deleted collection snapshot from an idempotency row.
                return paper_view(db, _paper(db, previous["id"]))
            paper = collect_overview(db, body)
            response = paper_view(db, paper)
            _remember(db, key, payload, response.model_dump())
            return response

    @app.get(prefix + "/papers/{library_paper_id}", response_model=LibraryPaperView)
    def get_paper(library_paper_id: str) -> LibraryPaperView:
        with read_session(engine()) as db:
            return paper_view(db, _paper(db, library_paper_id))

    @app.patch(prefix + "/papers/{library_paper_id}", response_model=LibraryPaperView)
    def update_paper(
        library_paper_id: str, body: LibraryPaperUpdate, idempotency_key: Key
    ) -> LibraryPaperView:
        payload = {"library_paper_id": library_paper_id, **body.model_dump(exclude_unset=True)}
        key = "knowledge-paper-update:" + idempotency_key
        with Session(engine()) as db, db.begin():
            previous = _replay(db, key, payload)
            if previous:
                return paper_view(db, _paper(db, library_paper_id))
            paper = _paper(db, library_paper_id)
            if body.current_version_id is not None:
                version = db.get(PaperKnowledgeVersion, body.current_version_id)
                if version is None or version.library_paper_id != paper.id:
                    raise library_error(
                        409, "KNOWLEDGE_VERSION_MISMATCH", "知识版本不属于该论文条目"
                    )
                paper.current_version_id = version.id
            for field in ("title", "note", "archived"):
                value = getattr(body, field)
                if value is not None:
                    if field == "title" and not value.strip():
                        raise library_error(422, "INVALID_LIBRARY_TITLE", "知识论文题名不能为空")
                    setattr(paper, field, value)
            paper.updated_at = now()
            response = paper_view(db, paper)
            _remember(db, key, payload, response.model_dump())
            return response

    @app.delete(prefix + "/papers/{library_paper_id}", response_model=LibraryActionResult)
    def delete_paper(library_paper_id: str, idempotency_key: Key) -> LibraryActionResult:
        payload = {"library_paper_id": library_paper_id}
        key = "knowledge-paper-purge:" + idempotency_key
        with read_session(engine()) as check:
            if _replay(check, key, payload):
                return LibraryActionResult()
            _paper(check, library_paper_id)
        _backup(engine(), data_dir)
        with Session(engine()) as db, db.begin():
            if _replay(db, key, payload):
                return LibraryActionResult()
            paper = _paper(db, library_paper_id)
            from researchgraph.knowledge_connections import cleanup_library_paper

            cleanup_library_paper(db, paper.id)
            version_ids = list(
                db.scalars(
                    select(PaperKnowledgeVersion.id).where(
                        PaperKnowledgeVersion.library_paper_id == paper.id
                    )
                )
            )
            # Remembered mutation DTOs contain knowledge text. Explicit purge
            # removes them too, so retained idempotency data is only a tombstone.
            identities = {paper.id, *version_ids}
            for entry in db.scalars(select(Idempotency).where(Idempotency.key.like("knowledge-%"))):
                encoded = json.dumps(entry.response, ensure_ascii=False)
                if any(identity in encoded for identity in identities):
                    db.delete(entry)
            db.delete(paper)
            db.flush()
            _remember(db, key, payload, LibraryActionResult().model_dump())
            return LibraryActionResult()

    @app.get(prefix + "/versions/{version_id}", response_model=KnowledgeVersionView)
    def get_version(version_id: str) -> KnowledgeVersionView:
        with read_session(engine()) as db:
            version = db.get(PaperKnowledgeVersion, version_id)
            if version is None:
                raise library_error(404, "KNOWLEDGE_VERSION_NOT_FOUND", "知识版本不存在")
            _paper(db, version.library_paper_id)
            return version_view(version)

    @app.get(prefix + "/collections", response_model=CollectionList)
    def list_collections() -> CollectionList:
        with read_session(engine()) as db:
            rows = db.scalars(
                select(KnowledgeCollection)
                .where(KnowledgeCollection.library_id == PERSONAL_LIBRARY_ID)
                .order_by(KnowledgeCollection.name, KnowledgeCollection.id)
            )
            return CollectionList(items=[collection_view(row) for row in rows])

    @app.post(prefix + "/collections", response_model=CollectionView)
    def create_collection(body: CollectionCreate, idempotency_key: Key) -> CollectionView:
        payload = body.model_dump()
        key = "knowledge-collection:" + idempotency_key
        with Session(engine()) as db, db.begin():
            previous = _replay(db, key, payload)
            if previous:
                return collection_view(_collection(db, previous["id"]))
            ensure_library(db)
            name = body.name.strip()
            if not name:
                raise library_error(422, "INVALID_COLLECTION_NAME", "专题名称不能为空")
            if db.scalar(
                select(KnowledgeCollection.id).where(
                    KnowledgeCollection.library_id == PERSONAL_LIBRARY_ID,
                    KnowledgeCollection.name == name,
                )
            ):
                raise library_error(409, "COLLECTION_EXISTS", "已存在同名专题")
            collection = KnowledgeCollection(
                id=str(uuid4()),
                library_id=PERSONAL_LIBRARY_ID,
                name=name,
                description=body.description,
                created_at=now(),
            )
            db.add(collection)
            db.flush()
            response = collection_view(collection)
            _remember(db, key, payload, response.model_dump())
            return response

    @app.delete(prefix + "/collections/{collection_id}", response_model=LibraryActionResult)
    def delete_collection(collection_id: str, idempotency_key: Key) -> LibraryActionResult:
        key = "knowledge-collection-delete:" + idempotency_key
        payload = {"collection_id": collection_id}
        with Session(engine()) as db, db.begin():
            if _replay(db, key, payload):
                return LibraryActionResult()
            collection = _collection(db, collection_id)
            library = db.get(KnowledgeLibrary, PERSONAL_LIBRARY_ID)
            if library:
                settings = LibrarySettings.model_validate(library.settings_json)
                if settings.collection_id == collection_id:
                    library.settings_json = settings.model_copy(
                        update={"scope": "project", "collection_id": None, "auto_connect": False}
                    ).model_dump()
                    library.updated_at = now()
            db.delete(collection)
            _remember(db, key, payload, LibraryActionResult().model_dump())
            return LibraryActionResult()

    def membership(
        collection_id: str, library_paper_id: str, add: bool, idempotency_key: str
    ) -> LibraryActionResult:
        key = "knowledge-membership:" + idempotency_key
        payload = {"collection_id": collection_id, "library_paper_id": library_paper_id, "add": add}
        with Session(engine()) as db, db.begin():
            if _replay(db, key, payload):
                return LibraryActionResult()
            _collection(db, collection_id)
            _paper(db, library_paper_id)
            current = db.get(KnowledgeCollectionMember, (collection_id, library_paper_id))
            if add and current is None:
                db.add(
                    KnowledgeCollectionMember(
                        collection_id=collection_id,
                        library_paper_id=library_paper_id,
                        created_at=now(),
                    )
                )
            elif not add and current is not None:
                db.delete(current)
            _remember(db, key, payload, LibraryActionResult().model_dump())
            return LibraryActionResult()

    @app.put(
        prefix + "/collections/{collection_id}/papers/{library_paper_id}",
        response_model=LibraryActionResult,
    )
    def add_member(
        collection_id: str, library_paper_id: str, idempotency_key: Key
    ) -> LibraryActionResult:
        return membership(collection_id, library_paper_id, True, idempotency_key)

    @app.delete(
        prefix + "/collections/{collection_id}/papers/{library_paper_id}",
        response_model=LibraryActionResult,
    )
    def remove_member(
        collection_id: str, library_paper_id: str, idempotency_key: Key
    ) -> LibraryActionResult:
        return membership(collection_id, library_paper_id, False, idempotency_key)

    @app.get(prefix + "/layout", response_model=LibraryLayoutView)
    def get_layout(
        view_key: str = Query(default="all", min_length=1, max_length=120),
    ) -> LibraryLayoutView:
        with read_session(engine()) as db:
            row = db.get(KnowledgeLibraryView, PERSONAL_LIBRARY_ID + ":" + view_key)
            return (
                LibraryLayoutView.model_validate(row.layout_json)
                if row
                else LibraryLayoutView(view_key=view_key)
            )

    @app.put(prefix + "/layout", response_model=LibraryLayoutView)
    def save_layout(body: LibraryLayoutView, idempotency_key: Key) -> LibraryLayoutView:
        payload = body.model_dump()
        key = "knowledge-layout:" + idempotency_key
        with Session(engine()) as db, db.begin():
            if _replay(db, key, payload):
                return body
            ensure_library(db)
            identity = PERSONAL_LIBRARY_ID + ":" + body.view_key
            row = db.get(KnowledgeLibraryView, identity)
            if row is None:
                row = KnowledgeLibraryView(
                    view_key=identity,
                    library_id=PERSONAL_LIBRARY_ID,
                    layout_json=payload,
                    updated_at=now(),
                )
                db.add(row)
            else:
                row.layout_json, row.updated_at = payload, now()
            _remember(db, key, payload, payload)
            return body

    @app.get(prefix + "/export", response_model=LibraryExport)
    def export_library() -> LibraryExport:
        from researchgraph.knowledge_connections import report_view

        with read_session(engine()) as db:
            papers = list(
                db.scalars(
                    select(LibraryPaper)
                    .where(LibraryPaper.library_id == PERSONAL_LIBRARY_ID)
                    .order_by(LibraryPaper.created_at, LibraryPaper.id)
                )
            )
            collections = db.scalars(
                select(KnowledgeCollection)
                .where(KnowledgeCollection.library_id == PERSONAL_LIBRARY_ID)
                .order_by(KnowledgeCollection.created_at, KnowledgeCollection.id)
            )
            try:
                reports = [
                    report_view(db, report)
                    for report in db.scalars(
                        select(KnowledgeConnectionReport).order_by(
                            KnowledgeConnectionReport.created_at, KnowledgeConnectionReport.id
                        )
                    )
                ]
            except KnowledgeError as error:
                raise library_error(409, error.code, str(error)) from None
            return LibraryExport(
                library=library_view(db.get(KnowledgeLibrary, PERSONAL_LIBRARY_ID)),
                papers=[paper_view(db, paper) for paper in papers],
                collections=[collection_view(collection) for collection in collections],
                reports=reports,
                layouts=[
                    LibraryLayoutView.model_validate(row.layout_json)
                    for row in db.scalars(
                        select(KnowledgeLibraryView)
                        .where(KnowledgeLibraryView.library_id == PERSONAL_LIBRARY_ID)
                        .order_by(KnowledgeLibraryView.view_key)
                    )
                ],
            )
