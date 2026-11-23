"""Explicit knowledge builds, comparison runs and saved report metadata."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Query
from pydantic import Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.archive_models import active_target, archived_target
from researchgraph.core import KnowledgeError, StrictModel
from researchgraph.knowledge_connection_models import (
    KnowledgeConnectionReport,
    KnowledgeConnectionRequest,
    KnowledgeConnectionRun,
)
from researchgraph.knowledge_connections import (
    connection_contract_version,
    queue_knowledge_connect,
    report_view,
)
from researchgraph.knowledge_connections_contracts import (
    KnowledgeConnectInput,
    KnowledgeExtractInput,
    KnowledgeReportEdit,
    KnowledgeRetryInput,
)
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.knowledge_library import (
    PERSONAL_LIBRARY_ID,
    ensure_library,
    library_error,
    library_view,
)
from researchgraph.knowledge_library_api import Key, _collection, _remember, _replay
from researchgraph.knowledge_library_models import (
    KnowledgeCollectionMember,
    LibraryPaper,
    PaperKnowledgeVersion,
)
from researchgraph.knowledge_tasks import (
    local_recovery_preview,
    queue_knowledge_extract,
    recover_knowledge_locally,
)
from researchgraph.model_document_models import LlmDocumentOutput, LlmDocumentParse
from researchgraph.model_document_overview import model_document_paper
from researchgraph.model_settings import snapshot_for
from researchgraph.models import AttachmentRevision, Job, Paper
from researchgraph.paper_overview_models import PaperOverviewResult
from researchgraph.schemas import JobView
from researchgraph.storage import read_session


def _job(db: Session, job_id: str) -> JobView:
    job = db.get(Job, job_id)
    if job is None:
        raise library_error(404, "KNOWLEDGE_RUN_MISSING", "任务记录已移除")
    _require_active_job(db, job_id)
    return JobView.model_validate(job)


def _error(error: KnowledgeError) -> Any:
    return library_error(409, error.code, str(error))


def _require_active_job(db: Session, job_id: str) -> None:
    if archived_target(db, "job", job_id):
        raise library_error(409, "JOB_ARCHIVED", "请先在归档管理中恢复该任务")


class KnowledgeLocalRecoveryInput(StrictModel):
    preview_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ExternalTopicPaper(StrictModel):
    id: str
    title: str
    version_id: str


class ExternalTopicPapers(StrictModel):
    items: list[ExternalTopicPaper]
    has_more: bool


def register_knowledge_workflow_api(
    app: FastAPI,
    engine: Callable[[], Engine],
    data_dir: Path | Callable[[], Path] | None = None,
    *_compatibility: Any,
) -> None:
    prefix = "/api/v1/knowledge"

    @app.get(
        prefix + "/collections/{collection_id}/external-papers",
        response_model=ExternalTopicPapers,
    )
    def external_topic_papers(
        collection_id: UUID, paper_ids: str = Query(min_length=36, max_length=1775)
    ) -> ExternalTopicPapers:
        """Read only the titles/current versions of explicitly requested context nodes."""
        candidates = paper_ids.split(",")
        if len(candidates) > 48:
            raise library_error(422, "KNOWLEDGE_CANDIDATES_INVALID", "最多接收 48 篇关联论文")
        try:
            ordered_ids = list(dict.fromkeys(str(UUID(candidate)) for candidate in candidates))
        except ValueError:
            raise library_error(422, "KNOWLEDGE_CANDIDATES_INVALID", "关联论文编号无效") from None
        with read_session(engine()) as db:
            _collection(db, str(collection_id))
            members = select(KnowledgeCollectionMember.library_paper_id).where(
                KnowledgeCollectionMember.collection_id == str(collection_id)
            )
            rows = db.execute(
                select(LibraryPaper.id, LibraryPaper.title, PaperKnowledgeVersion.id)
                .join(
                    PaperKnowledgeVersion,
                    PaperKnowledgeVersion.id == LibraryPaper.current_version_id,
                )
                .where(
                    LibraryPaper.id.in_(ordered_ids),
                    LibraryPaper.library_id == PERSONAL_LIBRARY_ID,
                    LibraryPaper.archived.is_(False),
                    active_target("knowledge_paper", LibraryPaper.id),
                    PaperKnowledgeVersion.library_paper_id == LibraryPaper.id,
                    LibraryPaper.id.not_in(members),
                )
            )
            by_id = {
                paper_id: ExternalTopicPaper(id=paper_id, title=title, version_id=version_id)
                for paper_id, title, version_id in rows
            }
            items = [by_id[paper_id] for paper_id in ordered_ids if paper_id in by_id]
            return ExternalTopicPapers(items=items[:12], has_more=len(items) > 12)

    @app.get(prefix + "/source-options")
    def sources(project_id: str | None = None, paper_id: str | None = None) -> dict[str, Any]:
        with read_session(engine()) as db:
            statement = (
                select(Paper)
                .where(active_target("paper", Paper.id))
                .order_by(Paper.created_at.desc(), Paper.id)
            )
            if project_id:
                statement = statement.where(Paper.project_id == project_id)
            if paper_id:
                statement = statement.where(Paper.id == paper_id)
            papers = list(db.scalars(statement))
            by_id: dict[str, dict[str, Any]] = {
                paper.id: {
                    "paper_id": paper.id,
                    "project_id": paper.project_id,
                    "title": paper.title,
                    "sources": [],
                }
                for paper in papers
            }
            for revision in db.scalars(
                select(AttachmentRevision).order_by(AttachmentRevision.created_at.desc())
            ):
                if revision.paper_id not in by_id:
                    continue
                overview = db.scalar(
                    select(PaperOverviewResult)
                    .where(
                        PaperOverviewResult.paper_id == revision.paper_id,
                        PaperOverviewResult.document_version_id == revision.id,
                        PaperOverviewResult.status == "COMPLETED",
                        PaperOverviewResult.schema_version == "paper_overview_graph.v1",
                    )
                    .order_by(PaperOverviewResult.created_at.desc())
                )
                by_id[revision.paper_id]["sources"].append(
                    {
                        "source_kind": "local_revision",
                        "source_id": revision.id,
                        "label": f"本地解析 · {revision.created_at}",
                        "has_overview": overview is not None,
                        "overview_result_id": overview.id if overview else None,
                    }
                )
            for parse in db.scalars(
                select(LlmDocumentParse)
                .where(LlmDocumentParse.status == "succeeded")
                .order_by(LlmDocumentParse.created_at.desc())
            ):
                paper = model_document_paper(db, parse)
                if paper is None or paper.id not in by_id:
                    continue
                overview_output = db.scalar(
                    select(LlmDocumentOutput)
                    .where(
                        LlmDocumentOutput.parse_id == parse.id,
                        LlmDocumentOutput.item_kind == "paper_overview",
                        LlmDocumentOutput.status == "succeeded",
                        LlmDocumentOutput.output_json["schema_version"].as_string()
                        == "paper_overview_graph.v1",
                    )
                    .order_by(LlmDocumentOutput.created_at.desc())
                )
                by_id[paper.id]["sources"].append(
                    {
                        "source_kind": "model_parse",
                        "source_id": parse.id,
                        "label": f"模型解析 · {parse.created_at}",
                        "has_overview": overview_output is not None,
                        "overview_result_id": overview_output.id if overview_output else None,
                    }
                )
            return {"items": list(by_id.values())}

    @app.post(prefix + "/extract", response_model=JobView)
    def extract(body: KnowledgeExtractInput, idempotency_key: Key) -> JobView:
        payload, key = body.model_dump(), "knowledge-extract:" + idempotency_key
        with Session(engine()) as db, db.begin():
            previous = _replay(db, key, payload)
            if previous:
                return _job(db, previous["id"])
            try:
                job = queue_knowledge_extract(
                    db,
                    paper_id=body.paper_id,
                    source_kind=body.source_kind,
                    source_version_id=body.source_id,
                    allow_network=body.allow_network,
                    model_snapshot=snapshot_for(db, None, "knowledge_extract"),
                    auto_connect=library_view(ensure_library(db)).settings.auto_connect,
                )
            except KnowledgeError as error:
                raise _error(error) from None
            response = JobView.model_validate(job)
            _remember(db, key, payload, {"id": job.id})
            return response

    @app.post(prefix + "/versions/{version_id}/connect", response_model=JobView)
    def connect(version_id: str, body: KnowledgeConnectInput, idempotency_key: Key) -> JobView:
        payload, key = (
            {"version_id": version_id, **body.model_dump()},
            "knowledge-connect:" + idempotency_key,
        )
        with Session(engine()) as db, db.begin():
            previous = _replay(db, key, payload)
            if previous:
                return _job(db, previous["id"])
            try:
                job = queue_knowledge_connect(
                    db,
                    version_id,
                    allow_network=body.allow_network,
                    force_regenerate=body.force_regenerate,
                )
            except KnowledgeError as error:
                raise _error(error) from None
            _remember(db, key, payload, {"id": job.id})
            return JobView.model_validate(job)

    @app.get(prefix + "/reports")
    def reports(
        library_paper_id: str | None = None,
        unread_only: bool = False,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        with read_session(engine()) as db:
            statement = select(KnowledgeConnectionReport)
            if library_paper_id:
                statement = statement.where(
                    KnowledgeConnectionReport.library_paper_id == library_paper_id
                )
            if unread_only:
                statement = statement.where(KnowledgeConnectionReport.read.is_(False))
            rows = list(
                db.scalars(
                    statement.order_by(
                        KnowledgeConnectionReport.pinned.desc(),
                        KnowledgeConnectionReport.created_at.desc(),
                        KnowledgeConnectionReport.id.desc(),
                    )
                )
            )
            return {
                "items": [report_view(db, r) for r in rows[offset : offset + limit]],
                "total": len(rows),
                "unread": sum(not r.read for r in rows),
            }

    @app.get(prefix + "/reports/{report_id}")
    def report(report_id: str) -> dict[str, Any]:
        with read_session(engine()) as db:
            row = db.get(KnowledgeConnectionReport, report_id)
            if row is None:
                raise library_error(404, "KNOWLEDGE_REPORT_MISSING", "联系汇报不存在")
            return report_view(db, row)

    @app.patch(prefix + "/reports/{report_id}")
    def edit_report(
        report_id: str, body: KnowledgeReportEdit, idempotency_key: Key
    ) -> dict[str, Any]:
        payload, key = (
            {"report_id": report_id, **body.model_dump(exclude_unset=True)},
            "knowledge-report:" + idempotency_key,
        )
        with Session(engine()) as db, db.begin():
            row = db.get(KnowledgeConnectionReport, report_id)
            if row is None:
                raise library_error(404, "KNOWLEDGE_REPORT_MISSING", "联系汇报不存在")
            if not _replay(db, key, payload):
                for field, value in body.model_dump(exclude_unset=True).items():
                    if value is not None:
                        setattr(row, field, value)
                _remember(db, key, payload, {"id": row.id})
            return report_view(db, row)

    @app.get(prefix + "/runs")
    def runs(
        library_paper_id: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        job_ids: str | None = Query(default=None, max_length=924),
    ) -> dict[str, Any]:
        requested_jobs: list[str] | None = None
        if job_ids is not None:
            try:
                values = job_ids.split(",")
                if len(values) > 25:
                    raise ValueError
                requested_jobs = [str(UUID(value)) for value in values]
            except ValueError:
                raise library_error(422, "INVALID_INPUT", "任务编号无效或数量超出 25 项") from None
        with read_session(engine()) as db:
            items: list[dict[str, Any]] = []
            extractions_by_id: dict[str, KnowledgeExtractionRun] = {}
            extractions = select(KnowledgeExtractionRun).where(
                active_target("job", KnowledgeExtractionRun.job_id)
            )
            connections = select(KnowledgeConnectionRun).where(
                active_target("job", KnowledgeConnectionRun.job_id)
            )
            if library_paper_id:
                extractions = extractions.where(
                    KnowledgeExtractionRun.library_paper_id == library_paper_id
                )
                connections = connections.where(
                    KnowledgeConnectionRun.library_paper_id == library_paper_id
                )
            if requested_jobs is not None:
                extractions = extractions.where(KnowledgeExtractionRun.job_id.in_(requested_jobs))
                connections = connections.where(KnowledgeConnectionRun.job_id.in_(requested_jobs))
            for extraction in db.scalars(extractions):
                extractions_by_id[extraction.id] = extraction
                job = db.get(Job, extraction.job_id)
                items.append(
                    {
                        "id": extraction.id,
                        "kind": "extract",
                        "job_id": extraction.job_id,
                        "library_paper_id": extraction.library_paper_id,
                        "version_id": extraction.version_id,
                        "status": job.status if job else extraction.status,
                        "stage": job.stage if job else None,
                        "error_code": extraction.error_code,
                        "error": job.error if job else None,
                        "request_count": int(extraction.request_sent),
                        "max_requests": extraction.max_attempts,
                        "created_at": extraction.created_at,
                    }
                )
            for connection in db.scalars(connections):
                job = db.get(Job, connection.job_id)
                slots = list(
                    db.scalars(
                        select(KnowledgeConnectionRequest).where(
                            KnowledgeConnectionRequest.run_id == connection.id
                        )
                    )
                )
                items.append(
                    {
                        "id": connection.id,
                        "kind": "connect",
                        "job_id": connection.job_id,
                        "library_paper_id": connection.library_paper_id,
                        "version_id": connection.version_id,
                        "status": job.status if job else connection.status,
                        "stage": job.stage if job else None,
                        "error_code": connection.error_code,
                        "error": connection.error,
                        "request_count": sum(r.sent_at is not None for r in slots),
                        "max_requests": connection.policy_json["max_requests_per_run"],
                        "created_at": connection.created_at,
                    }
                )
            items.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
            page = items[offset : offset + limit]
            for item in page:
                page_extraction = extractions_by_id.get(item["id"])
                if page_extraction is not None:
                    item["local_recovery"] = (
                        local_recovery_preview(db, page_extraction)
                        if page_extraction.status == "failed"
                        else None
                    )
            return {"items": page, "total": len(items)}

    @app.get(prefix + "/usage")
    def usage() -> dict[str, Any]:
        from researchgraph.lite_usage import aggregate_knowledge_usage

        with read_session(engine()) as db:
            return aggregate_knowledge_usage(db).model_dump()

    @app.post(prefix + "/runs/{run_id}/retry", response_model=JobView)
    def retry(run_id: str, body: KnowledgeRetryInput, idempotency_key: Key) -> JobView:
        payload, key = {"run_id": run_id, **body.model_dump()}, "knowledge-retry:" + idempotency_key
        with Session(engine()) as db, db.begin():
            connection = db.get(KnowledgeConnectionRun, run_id)
            extraction = db.get(KnowledgeExtractionRun, run_id)
            original = connection or extraction
            if original is None:
                raise library_error(404, "KNOWLEDGE_RUN_MISSING", "知识任务不存在")
            _require_active_job(db, original.job_id)
            previous = _replay(db, key, payload)
            if previous:
                return _job(db, previous["id"])
            try:
                if connection:
                    job = queue_knowledge_connect(
                        db,
                        connection.version_id,
                        allow_network=body.allow_network,
                        retry_failed=True,
                        connection_version=connection_contract_version(connection.input_json),
                    )
                elif extraction:
                    job = queue_knowledge_extract(
                        db,
                        paper_id=extraction.paper_id,
                        source_kind=extraction.source_kind,
                        source_version_id=extraction.source_id,
                        model_snapshot=snapshot_for(db, None, "knowledge_extract"),
                        allow_network=body.allow_network,
                        retry_failed=True,
                        auto_connect=library_view(ensure_library(db)).settings.auto_connect,
                    )
                else:
                    raise library_error(404, "KNOWLEDGE_RUN_MISSING", "知识任务不存在")
            except KnowledgeError as error:
                raise _error(error) from None
            _remember(db, key, payload, {"id": job.id})
            return JobView.model_validate(job)

    @app.get(prefix + "/runs/{run_id}/local-recovery")
    def preview_local_recovery(run_id: str) -> dict[str, Any]:
        with read_session(engine()) as db:
            run = db.get(KnowledgeExtractionRun, run_id)
            if run is None:
                raise library_error(404, "KNOWLEDGE_RUN_MISSING", "知识抽取任务不存在")
            _require_active_job(db, run.job_id)
            return local_recovery_preview(db, run)

    @app.post(prefix + "/runs/{run_id}/local-recovery")
    def publish_local_recovery(
        run_id: str,
        body: KnowledgeLocalRecoveryInput,
        idempotency_key: Key,
    ) -> dict[str, Any]:
        payload = {"run_id": run_id, **body.model_dump()}
        key = "knowledge-local-recovery:" + idempotency_key
        with Session(engine()) as db, db.begin():
            previous = _replay(db, key, payload)
            run = db.get(KnowledgeExtractionRun, run_id)
            if run is None:
                raise library_error(404, "KNOWLEDGE_RUN_MISSING", "知识抽取任务不存在")
            _require_active_job(db, run.job_id)
            try:
                # Even an idempotency replay revalidates the original raw and current sources.
                result = recover_knowledge_locally(db, run, body.preview_fingerprint)
            except KnowledgeError as error:
                raise _error(error) from None
            except (ValueError, KeyError, TypeError, IndexError):
                raise library_error(
                    409,
                    "KNOWLEDGE_LOCAL_RECOVERY_UNAVAILABLE",
                    "保留内容尚有结构或引用问题，请重新查看本机恢复预览",
                ) from None
            if previous and previous.get("version_id") != result["version_id"]:
                raise library_error(409, "KNOWLEDGE_LOCAL_RECOVERY_STALE", "本机恢复结果已变化")
            if not previous:
                _remember(db, key, payload, result)
            return result
