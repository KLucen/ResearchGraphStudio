"""Zotero selection and local PDF import routes."""

from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import FastAPI, Query
from pydantic import Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError, StrictModel
from researchgraph.integrations import ZoteroAdapter
from researchgraph.models import Job, Project, now
from researchgraph.schemas import JobView


class CollectionBrowse(StrictModel):
    library: str = "users/0"
    collection_key: str = Field(pattern=r"^[A-Z0-9]{8}$")
    search: str = Field(default="", max_length=120)
    start: int = Field(default=0, ge=0, le=10000)


class AttachmentChoice(StrictModel):
    item_key: str = Field(pattern=r"^[A-Z0-9]{8}$")
    attachment_key: str = Field(pattern=r"^[A-Z0-9]{8}$")


class BatchImport(StrictModel):
    library: str = "users/0"
    collection_key: str = Field(pattern=r"^[A-Z0-9]{8}$")
    selections: list[AttachmentChoice] = Field(min_length=1, max_length=50)
    mode: Literal["reference", "managed"] = "reference"


class PdfChoice(StrictModel):
    key: str
    title: str
    filename: str
    available: bool


class ZoteroPaper(StrictModel):
    key: str
    title: str
    item_type: str
    attachments: list[PdfChoice]


class CollectionPage(StrictModel):
    items: list[ZoteroPaper]
    next_start: int | None


class ZoteroStatus(StrictModel):
    connected: bool
    error: str | None = None


class ImportStatus(StrictModel):
    job: JobView
    item_key: str
    attachment_key: str
    collection_key: str
    library: str


def read_collection(body: CollectionBrowse) -> CollectionPage:
    adapter = ZoteroAdapter()
    prefix = "/" + adapter.library(body.library)
    items = adapter.get(
        f"{prefix}/collections/{body.collection_key}/items/top?"
        + urlencode(
            {"limit": 10, "start": body.start, "q": body.search, "qmode": "titleCreatorYear"}
        )
    )
    if not isinstance(items, list):
        raise KnowledgeError("ZOTERO_INVALID_RESPONSE", "Zotero 分类响应无效")
    papers = []
    for item in items:
        key = adapter.key(str(item.get("key", "")))
        data = item.get("data", {})
        children = adapter.get(f"{prefix}/items/{key}/children?limit=100")
        attachments = []
        for child in children if isinstance(children, list) else []:
            value = child.get("data", {})
            if (
                value.get("itemType") != "attachment"
                or value.get("contentType") != "application/pdf"
            ):
                continue
            akey = adapter.key(str(child.get("key", "")))
            try:
                available = adapter.attachment_path(body.library, akey).is_file()
            except KnowledgeError:
                available = False
            attachments.append(
                PdfChoice(
                    key=akey,
                    title=value.get("title", "PDF"),
                    filename=value.get("filename", ""),
                    available=available,
                )
            )
        papers.append(
            ZoteroPaper(
                key=key,
                title=data.get("title", key),
                item_type=data.get("itemType", "unknown"),
                attachments=attachments,
            )
        )
    return CollectionPage(
        items=papers, next_start=body.start + len(papers) if len(papers) == 10 else None
    )


def status(job: Job) -> ImportStatus:
    payload = job.payload or {}
    return ImportStatus(
        job=JobView.model_validate(job),
        item_key=payload.get("item_key", ""),
        attachment_key=payload.get("attachment_key", ""),
        collection_key=payload.get("collection_key", ""),
        library=payload.get("library", "users/0"),
    )


def register_zotero_batch_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    from researchgraph.app import Key, remember, remembered

    @app.get("/api/v1/integrations/zotero/status", response_model=ZoteroStatus)
    def zotero_status(library: str = Query(default="users/0")) -> ZoteroStatus:
        """Probe the read-only local API without transmitting an API key."""
        adapter = ZoteroAdapter()
        value = adapter.library(library)
        try:
            response = adapter.get(f"/{value}/collections?limit=1")
            if not isinstance(response, list):
                raise KnowledgeError("ZOTERO_INVALID_RESPONSE", "Zotero 列表响应无效")
        except KnowledgeError as error:
            return ZoteroStatus(connected=False, error=str(error))
        return ZoteroStatus(connected=True)

    @app.get("/api/v1/integrations/zotero/collections", response_model=list[dict[str, Any]])
    def collections(
        library: str = Query(default="users/0"),
        start: int = Query(default=0, ge=0, le=10000),
    ) -> list[dict[str, Any]]:
        """Return raw collection records used by the desktop picker."""
        adapter = ZoteroAdapter()
        records = adapter.browse(library, "collections", start)
        if not all(isinstance(record, dict) for record in records):
            raise KnowledgeError("ZOTERO_INVALID_RESPONSE", "Zotero 分类响应无效")
        return records

    @app.post("/api/v1/integrations/zotero/browse", response_model=CollectionPage)
    def browse(body: CollectionBrowse) -> CollectionPage:
        return read_collection(body)

    @app.post(
        "/api/v1/projects/{project_id}/zotero-imports",
        response_model=list[ImportStatus],
        status_code=202,
    )
    def submit(project_id: str, body: BatchImport, idempotency_key: Key) -> list[ImportStatus]:
        ZoteroAdapter.library(body.library)
        request = {"project_id": project_id, **body.model_dump()}
        with Session(engine()) as session, session.begin():
            if session.get(Project, project_id) is None:
                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            previous = remembered(session, "zotero-batch:" + idempotency_key, request)
            if previous:
                return [ImportStatus.model_validate(x) for x in previous["items"]]
            jobs = []
            seen = set()
            for choice in body.selections:
                identity = (
                    body.library,
                    body.collection_key,
                    body.mode,
                    choice.item_key,
                    choice.attachment_key,
                )
                if identity in seen:
                    continue
                seen.add(identity)
                payload = {
                    "library": body.library,
                    "collection_key": body.collection_key,
                    "mode": body.mode,
                    **choice.model_dump(),
                }
                existing = session.scalar(
                    select(Job).where(
                        Job.project_id == project_id,
                        Job.kind == "zotero_import",
                        Job.status.in_(["queued", "running"]),
                        Job.payload["library"].as_string() == body.library,
                        Job.payload["collection_key"].as_string() == body.collection_key,
                        Job.payload["mode"].as_string() == body.mode,
                        Job.payload["item_key"].as_string() == choice.item_key,
                        Job.payload["attachment_key"].as_string() == choice.attachment_key,
                    )
                )
                job = existing or Job(
                    id=str(uuid4()),
                    project_id=project_id,
                    kind="zotero_import",
                    payload=payload,
                    status="queued",
                    attempt=0,
                    created_at=now(),
                    updated_at=now(),
                )
                if existing is None:
                    session.add(job)
                    session.flush()
                jobs.append(status(job))
            response = {"items": [x.model_dump() for x in jobs]}
            remember(session, "zotero-batch:" + idempotency_key, request, response)
            return jobs

    @app.get("/api/v1/projects/{project_id}/zotero-imports", response_model=list[ImportStatus])
    def history(project_id: str) -> list[ImportStatus]:
        with Session(engine()) as session:
            return [
                status(j)
                for j in session.scalars(
                    select(Job)
                    .where(Job.project_id == project_id, Job.kind == "zotero_import")
                    .order_by(Job.created_at.desc(), Job.id)
                    .limit(100)
                )
            ]
