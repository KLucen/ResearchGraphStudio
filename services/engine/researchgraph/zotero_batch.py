"""Selection-based read-only Zotero ingestion into the existing PDF job pipeline."""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import FastAPI
from pydantic import Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.integrations import ZoteroAdapter
from researchgraph.knowledge_contracts import StrictModel
from researchgraph.knowledge_store import KnowledgeError
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
    extract_after_parse: bool = False
    provider: Literal["mock", "project"] = "project"
    allow_network: bool = False


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


class ImportStatus(StrictModel):
    job: JobView
    item_key: str
    attachment_key: str
    collection_key: str
    library: str


def read_collection(body: CollectionBrowse) -> CollectionPage:
    adapter = ZoteroAdapter()
    prefix = "/" + adapter.library(body.library)
    route = f"{prefix}/collections/{body.collection_key}/items/top?" + urlencode(
        {"limit": 10, "start": body.start, "q": body.search, "qmode": "titleCreatorYear"}
    )
    items = adapter.get(route)
    if not isinstance(items, list):
        raise KnowledgeError("ZOTERO_INVALID_RESPONSE", "Zotero 分类响应无效")

    def paper(item: dict[str, Any]) -> ZoteroPaper:
        key, data = adapter.key(item["key"]), item.get("data", {})
        children = adapter.get(f"{prefix}/items/{key}/children?limit=100")
        choices = []
        for child in children:
            value = child.get("data", {})
            if (
                value.get("itemType") != "attachment"
                or value.get("contentType") != "application/pdf"
            ):
                continue
            attachment_key = adapter.key(child["key"])
            try:
                available = adapter.attachment_path(body.library, attachment_key).is_file()
            except KnowledgeError:
                available = False
            choices.append(
                PdfChoice(
                    key=attachment_key,
                    title=value.get("title", "PDF"),
                    filename=value.get("filename", ""),
                    available=available,
                )
            )
        return ZoteroPaper(
            key=key,
            title=data.get("title", key),
            item_type=data.get("itemType", "unknown"),
            attachments=choices,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        papers = list(
            pool.map(
                paper,
                [
                    item
                    for item in items
                    if item.get("data", {}).get("itemType")
                    not in {"note", "annotation", "attachment"}
                ],
            )
        )
    return CollectionPage(items=papers, next_start=body.start + 10 if len(items) == 10 else None)


async def prepare_import(
    engine: Engine, job_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        assert job and job.payload
        payload = dict(job.payload)
    adapter = ZoteroAdapter()
    metadata, annotations, path = await asyncio.to_thread(
        adapter.read_annotations, payload["library"], payload["item_key"], payload["attachment_key"]
    )
    if payload["collection_key"] not in metadata.get("data", {}).get("collections", []):
        raise KnowledgeError("ZOTERO_COLLECTION_MISMATCH", "条目不属于所选分类，请刷新后重新选择")
    attachment = await asyncio.to_thread(
        adapter.get,
        f"/{adapter.library(payload['library'])}/items/{adapter.key(payload['attachment_key'])}",
    )
    if attachment.get("data", {}).get("contentType") != "application/pdf":
        raise KnowledgeError("ZOTERO_NOT_PDF", "所选附件不是 PDF")
    if not path.is_file():
        raise KnowledgeError("ZOTERO_FILE_UNAVAILABLE", "PDF 未下载到本机或无法读取")
    with Session(engine) as session, session.begin():
        current = session.get(Job, job_id)
        if current is None or current.status != "running":
            raise KnowledgeError("JOB_CANCELLED", "任务已取消")
        current.payload = {**payload, "path": str(path)}
    return metadata, annotations


def status(job: Job) -> ImportStatus:
    payload = job.payload or {}
    return ImportStatus(
        job=JobView.model_validate(job),
        **{k: payload[k] for k in ("item_key", "attachment_key", "collection_key", "library")},
    )


def register_zotero_batch_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    from researchgraph.app import Key, remember, remembered

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
        request_body = body.model_dump()
        if not body.extract_after_parse:
            for field in ("extract_after_parse", "provider", "allow_network"):
                request_body.pop(field, None)
        request = {"project_id": project_id, **request_body}
        with Session(engine()) as session, session.begin():
            if session.get(Project, project_id) is None:
                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            previous = remembered(session, "zotero-batch:" + idempotency_key, request)
            if previous:
                return [ImportStatus.model_validate(j) for j in previous["items"]]
            extraction_options: dict[str, Any] = {}
            if body.extract_after_parse:
                extraction_options = {
                    "provider": body.provider,
                    "allow_network": body.allow_network,
                    "pipeline": "paper-reading-v1",
                }
                if body.provider == "project":
                    from researchgraph.model_settings import from_snapshot, snapshot_for

                    profile = snapshot_for(session, project_id, "extraction")
                    from_snapshot(
                        profile, Path(str(engine().url.database)).parent, body.allow_network
                    )
                    extraction_options["model_snapshot"] = profile
            jobs: list[ImportStatus] = []
            pending = session.scalars(
                select(Job).where(
                    Job.project_id == project_id,
                    Job.kind == "zotero_import",
                    Job.status.in_(["queued", "running"]),
                )
            ).all()
            seen = set()
            for choice in body.selections:
                identity = (choice.item_key, choice.attachment_key)
                if identity in seen:
                    continue
                seen.add(identity)
                payload = {
                    "library": body.library,
                    "collection_key": body.collection_key,
                    "mode": body.mode,
                    **choice.model_dump(),
                    **(
                        {"extraction_options": extraction_options}
                        if body.extract_after_parse
                        else {}
                    ),
                }
                existing = next(
                    (
                        j
                        for j in pending
                        if j.payload and all(j.payload.get(k) == v for k, v in payload.items())
                    ),
                    None,
                )
                if existing:
                    jobs.append(status(existing))
                    continue
                job = Job(
                    id=str(uuid4()),
                    project_id=project_id,
                    kind="zotero_import",
                    payload=payload,
                    status="queued",
                    attempt=0,
                    created_at=now(),
                    updated_at=now(),
                )
                session.add(job)
                session.flush()
                jobs.append(status(job))
            remember(
                session,
                "zotero-batch:" + idempotency_key,
                request,
                {"items": [j.model_dump() for j in jobs]},
            )
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
