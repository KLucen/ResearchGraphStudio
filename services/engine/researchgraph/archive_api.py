"""Archive user-visible records and apply permanent cleanup on explicit request."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import ConfigDict, Field
from sqlalchemy import ColumnElement, Engine, delete, func, select
from sqlalchemy.orm import Session

from researchgraph.archive_models import ArchivedItem, ArchiveKind, archived_target
from researchgraph.core import StrictModel, digest
from researchgraph.credentials import CredentialError, SecretStore
from researchgraph.knowledge_library_models import (
    KnowledgeCollection,
    KnowledgeLibrary,
    LibraryPaper,
)
from researchgraph.model_settings import GlobalModelRole, ModelConnection, ModelProfile
from researchgraph.models import Idempotency, Job, Paper, now
from researchgraph.schemas import reading_task_for
from researchgraph.storage import read_session

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)]


class ArchiveCreate(StrictModel):
    kind: ArchiveKind
    target_id: UUID


class ArchiveItem(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: str
    kind: ArchiveKind
    target_id: str
    title: str
    project_id: str | None
    archived_at: str
    status: Literal["archived", "purging"]


class ArchiveList(StrictModel):
    items: list[ArchiveItem]
    total: int


class ArchiveAction(StrictModel):
    ok: bool = True


class ArchivePurgeResult(ArchiveAction):
    status: Literal["purged", "purging"] = "purged"
    backup_file: str | None = None
    removed: dict[str, int] = Field(default_factory=dict)
    retained_personal_metadata: int = 0
    retained_managed_files: int = 0
    pending_managed_files: int = 0


def _failure(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _missing_target() -> HTTPException:
    return _failure(404, "ARCHIVE_TARGET_NOT_FOUND", "待归档内容不存在")


def _pending_item() -> HTTPException:
    return _failure(409, "ARCHIVE_PURGE_IN_PROGRESS", "清除已开始，可从归档管理继续清除")


def _archived_item(db: Session, item_id: str) -> ArchivedItem:
    item = db.get(ArchivedItem, item_id)
    if item is None:
        raise _failure(404, "ARCHIVE_ITEM_NOT_FOUND", "归档条目不存在")
    return item


def _stop_collection_analysis(db: Session, collection: KnowledgeCollection) -> None:
    from researchgraph.knowledge_library_contracts import LibrarySettings

    library = db.get(KnowledgeLibrary, collection.library_id)
    if library is None:
        return
    settings = LibrarySettings.model_validate(library.settings_json)
    if settings.collection_id == collection.id:
        library.settings_json = settings.model_copy(
            update={"scope": "project", "collection_id": None, "auto_connect": False}
        ).model_dump()
        library.updated_at = now()


def _archive_profiles(db: Session, profiles: list[ModelProfile]) -> dict[str, Any]:
    profile_ids = sorted(profile.id for profile in profiles)
    roles = [
        {"role": role.role, "profile_id": role.profile_id}
        for role in db.scalars(
            select(GlobalModelRole).where(GlobalModelRole.profile_id.in_(profile_ids))
        )
    ]
    db.execute(delete(GlobalModelRole).where(GlobalModelRole.profile_id.in_(profile_ids)))
    for profile in profiles:
        profile.active = False
    return {"profiles": profile_ids, "roles": roles}


def _restore_profiles(db: Session, profiles: list[ModelProfile], state: dict[str, Any]) -> None:
    for profile in profiles:
        profile.active = True
    profile_ids = {profile.id for profile in profiles}
    for role in state["roles"]:
        if role["profile_id"] in profile_ids and db.get(GlobalModelRole, role["role"]) is None:
            db.add(GlobalModelRole(role=role["role"], profile_id=role["profile_id"]))


def archive_target(db: Session, kind: ArchiveKind, target_id: str) -> ArchivedItem:
    existing = archived_target(db, kind, target_id)
    if existing is not None:
        if existing.status == "purged":
            if kind != "paper_legacy_content":
                raise _missing_target()
            # A surviving paper may have a fresh cache after a previous purge.
            db.delete(existing)
            db.flush()
        else:
            return existing
    project_id: str | None = None
    restore: dict[str, Any] = {}
    if kind in {"paper", "paper_legacy_content"}:
        from researchgraph.paper_management_api import _ensure_no_running_jobs, _paper_context

        context = _paper_context(db, target_id)
        _ensure_no_running_jobs(
            context, preserve_model_first=kind == "paper_legacy_content", reject_queued_legacy=True
        )
        title, project_id = context["paper"].title, context["paper"].project_id
    elif kind == "knowledge_paper":
        from researchgraph.knowledge_library_api import _paper

        library_paper = _paper(db, target_id)
        title = library_paper.title
        library_paper.archived = True
        library_paper.updated_at = now()
    elif kind == "knowledge_collection":
        from researchgraph.knowledge_library_api import _collection

        collection = _collection(db, target_id)
        title = collection.name
        _stop_collection_analysis(db, collection)
    elif kind == "model_connection":
        connection = db.get(ModelConnection, target_id)
        if connection is None or not connection.active:
            raise _missing_target()
        title, project_id = connection.name, connection.project_id
        restore = _archive_profiles(
            db,
            list(
                db.scalars(
                    select(ModelProfile).where(
                        ModelProfile.connection_id == connection.id, ModelProfile.active.is_(True)
                    )
                )
            ),
        )
        connection.active = False
        connection.updated_at = now()
    elif kind == "model_profile":
        profile = db.get(ModelProfile, target_id)
        if profile is None or not profile.active:
            raise _missing_target()
        title, project_id = profile.name, profile.project_id
        restore = _archive_profiles(db, [profile])
    else:
        job = db.get(Job, target_id)
        if job is None:
            raise _missing_target()
        if job.status in {"queued", "running"}:
            raise _failure(409, "ARCHIVE_TASK_ACTIVE", "任务仍在运行或排队，请先取消或等待完成")
        reading_task = reading_task_for(job.kind, job.payload or {})
        label = {
            "paper_card_set": "论文卡片集生成",
            "paper_overview": "历史论文概览",
            "paper_reading": "全文精读笔记生成",
            "translation": "逐段中文翻译",
        }.get(reading_task or "") or {
            "diagnostics": "存储诊断",
            "llm_document_parse": "模型解析论文",
            "llm_document_postprocess": "模型论文内容生成",
            "pdf_import": "PDF 导入",
            "zotero_import": "Zotero 导入",
            "knowledge_extract": "提取论文知识",
            "knowledge_connect": "分析论文联系",
            "paper_overview": "历史论文概览",
            "paper_reading_notes": "全文精读笔记生成",
            "pdf_translation": "PDF 翻译",
        }.get(job.kind, "任务记录")
        result_title = (job.result or {}).get("title")
        title = (
            f"{label} · {result_title.strip()}"
            if isinstance(result_title, str) and result_title.strip()
            else label
        )
        project_id = job.project_id
    item = ArchivedItem(
        id=str(uuid4()),
        kind=kind,
        target_id=target_id,
        title=title,
        project_id=project_id,
        archived_at=now(),
        status="archived",
        restore_json=restore,
    )
    db.add(item)
    db.flush()
    return item


def restore_target(db: Session, item: ArchivedItem) -> None:
    if item.status == "purging":
        raise _pending_item()
    if item.status != "archived":
        raise _failure(404, "ARCHIVE_ITEM_NOT_FOUND", "该归档条目已彻底清除")
    if item.kind == "knowledge_paper":
        library_paper = db.get(LibraryPaper, item.target_id)
        if library_paper is None:
            raise _missing_target()
        library_paper.archived = False
        library_paper.updated_at = now()
    elif item.kind == "model_connection":
        connection = db.get(ModelConnection, item.target_id)
        if connection is None:
            raise _missing_target()
        profiles = list(
            db.scalars(
                select(ModelProfile).where(
                    ModelProfile.connection_id == connection.id,
                    ModelProfile.id.in_(item.restore_json["profiles"]),
                )
            )
        )
        connection.active = True
        connection.updated_at = now()
        _restore_profiles(db, profiles, item.restore_json)
    elif item.kind == "model_profile":
        profile = db.get(ModelProfile, item.target_id)
        if profile is None:
            raise _missing_target()
        if profile.connection_id:
            provider = db.get(ModelConnection, profile.connection_id)
            if provider is None or not provider.active:
                raise _failure(
                    409, "ARCHIVE_MODEL_CONNECTION_INACTIVE", "请先恢复此模型所属的提供商"
                )
        _restore_profiles(db, [profile], item.restore_json)
    else:
        owner = {
            "paper": Paper,
            "paper_legacy_content": Paper,
            "job": Job,
            "knowledge_collection": KnowledgeCollection,
        }[item.kind]
        if db.get(owner, item.target_id) is None:
            raise _missing_target()
    db.delete(item)


def _mark_purged(item: ArchivedItem) -> None:
    # Keep only the target needed to hide a task receipt and make a purge replay safe.
    item.status, item.title, item.project_id, item.restore_json = "purged", "", None, {}


def _model_credentials(model: ModelConnection | ModelProfile) -> set[str]:
    return {*model.secret_refs, *([model.credential_ref] if model.credential_ref else [])}


def _ensure_model_tasks_idle(db: Session, identifiers: set[str]) -> None:
    from researchgraph.import_plan_models import ImportPlanItem, ImportSession
    from researchgraph.knowledge_connection_models import (
        KnowledgeCollectionEvent,
        KnowledgeConnectionRun,
    )
    from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
    from researchgraph.paper_management_api import _contains_any

    active = Job.status.in_(("queued", "running"))
    jobs = select(Job.id).where(active)
    candidates = (
        select(Job.payload).where(active),
        select(ImportPlanItem.config).where(ImportPlanItem.job_id.in_(jobs)),
        select(ImportSession.plan).join(ImportPlanItem).where(ImportPlanItem.job_id.in_(jobs)),
        select(KnowledgeExtractionRun.model_snapshot).where(
            KnowledgeExtractionRun.job_id.in_(jobs)
        ),
        select(KnowledgeConnectionRun.model_snapshot).where(
            KnowledgeConnectionRun.job_id.in_(jobs)
        ),
        select(KnowledgeCollectionEvent.model_snapshot).where(
            KnowledgeCollectionEvent.state == "pending"
        ),
    )
    if any(
        _contains_any(payload, identifiers)
        for statement in candidates
        for payload in db.scalars(statement)
    ):
        raise _failure(
            409, "ARCHIVE_MODEL_TASK_ACTIVE", "此配置仍有排队或执行中的任务，请等待任务结束"
        )


def _model_purge_references(db: Session, item: ArchivedItem) -> set[str]:
    connection_ids: set[str] = set()
    if item.kind == "model_connection":
        connection = db.get(ModelConnection, item.target_id)
        if connection is None:
            raise _missing_target()
        profiles = list(
            db.scalars(select(ModelProfile).where(ModelProfile.connection_id == connection.id))
        )
        connection_ids.add(connection.id)
        references = _model_credentials(connection)
        if db.scalar(
            select(ArchivedItem.id)
            .where(
                ArchivedItem.kind == "model_profile",
                ArchivedItem.target_id.in_([model.id for model in profiles]),
                ArchivedItem.status == "purging",
            )
            .limit(1)
        ):
            raise _failure(409, "ARCHIVE_MODEL_PROFILE_PURGING", "请先完成所属模型配置的清除")
    else:
        profile = db.get(ModelProfile, item.target_id)
        if profile is None:
            raise _missing_target()
        if (
            profile.connection_id
            and (owner := archived_target(db, "model_connection", profile.connection_id))
            and owner.status == "purging"
        ):
            raise _failure(409, "ARCHIVE_MODEL_CONNECTION_PURGING", "请继续清除该模型所属的提供商")
        profiles, references = [profile], set()
    profile_ids = {profile.id for profile in profiles}
    for profile in profiles:
        references.update(_model_credentials(profile))
    # Inactive and archived rows may also share a secret. Preserve each
    # reference until its final owner is explicitly purged.
    for other_connection in db.scalars(
        select(ModelConnection).where(ModelConnection.id.not_in(connection_ids))
    ):
        references.difference_update(_model_credentials(other_connection))
    for other_profile in db.scalars(
        select(ModelProfile).where(ModelProfile.id.not_in(profile_ids))
    ):
        references.difference_update(_model_credentials(other_profile))
    _ensure_model_tasks_idle(db, {*connection_ids, *profile_ids, *references})
    return references


def _purge_model_secrets(db: Session, item: ArchivedItem, data_dir: Path) -> None:
    references = _model_purge_references(db, item)
    secrets = SecretStore(data_dir)
    try:
        for reference in references:
            secrets.delete(reference)
    except CredentialError:
        raise _failure(
            409, "ARCHIVE_CREDENTIAL_PURGE_FAILED", "凭据清除失败，可稍后继续清除"
        ) from None


def _purge_unreferenced_job(db: Session, job: Job) -> None:
    # General jobs can anchor import/parse results and paid request receipts.
    if job.kind != "diagnostics":
        return
    from researchgraph.document_batch_models import LlmDocumentBatchRun
    from researchgraph.import_plan_models import ImportPlanItem
    from researchgraph.translation_models import PDFTranslation

    for column in (LlmDocumentBatchRun.job_id, ImportPlanItem.job_id, PDFTranslation.job_id):
        if db.scalar(select(column).where(column == job.id).limit(1)):
            return
    db.delete(job)


def _finish_paper_file_purge(engine: Engine, item_id: str, data_dir: Path) -> ArchivePurgeResult:
    from researchgraph.paper_management_api import _purge_unreferenced_managed_files

    with Session(engine) as db, db.begin():
        item = _archived_item(db, item_id)
        if item.status == "purged":
            return ArchivePurgeResult()
        state = item.restore_json
        result = ArchivePurgeResult.model_validate(state["result"])
        retained, pending = _purge_unreferenced_managed_files(db, data_dir, state["managed_paths"])
        result.retained_managed_files += retained
        result.pending_managed_files = len(pending)
        result.status = "purging" if pending else "purged"
        result.ok = not pending
        if pending:
            item.restore_json = {"managed_paths": pending, "result": result.model_dump()}
        else:
            _mark_purged(item)
        return result


def purge_target(engine: Engine, item_id: str, data_dir: Path) -> ArchivePurgeResult:
    from researchgraph.knowledge_library_api import _backup, _purge_library_paper
    from researchgraph.paper_management_api import (
        _backup_database,
        _delete_paper_data,
        _ensure_no_running_jobs,
        _paper_context,
        _remove_legacy_content,
    )

    with read_session(engine) as db:
        item = _archived_item(db, item_id)
        if item.status == "purged":
            return ArchivePurgeResult()
        kind, target_id = item.kind, item.target_id
        finish_files = kind == "paper" and item.status == "purging"
        if not finish_files and kind in {"paper", "paper_legacy_content"}:
            _ensure_no_running_jobs(
                _paper_context(db, target_id),
                preserve_model_first=kind == "paper_legacy_content",
                reject_queued_legacy=True,
            )
    if finish_files:
        return _finish_paper_file_purge(engine, item_id, data_dir)
    result = ArchivePurgeResult()
    if kind in {"paper", "paper_legacy_content"}:
        result.backup_file = _backup_database(
            engine, data_dir, target_id, "delete" if kind == "paper" else "legacy-content"
        )
    elif kind == "knowledge_paper":
        _backup(engine, data_dir)
    elif kind in {"model_connection", "model_profile"}:
        # Persist the boundary before deleting any OS credential. Revalidate
        # and delete secrets under the same writer lock as their owner rows.
        with Session(engine) as db, db.begin():
            item = _archived_item(db, item_id)
            if item.status == "purged":
                return result
            _model_purge_references(db, item)
            item.status = "purging"
    managed_paths: list[str] = []
    with Session(engine) as db, db.begin():
        item = _archived_item(db, item_id)
        if item.status == "purged":
            return result
        if kind == "paper" and item.status == "purging":
            finish_files = True
        elif kind in {"paper", "paper_legacy_content"}:
            context = _paper_context(db, target_id)
            _ensure_no_running_jobs(
                context,
                preserve_model_first=kind == "paper_legacy_content",
                reject_queued_legacy=True,
            )
            if kind == "paper_legacy_content":
                result.removed = _remove_legacy_content(db, context)
                result.retained_personal_metadata = result.removed.get(
                    "personal_metadata_retained", 0
                )
            else:
                result.removed, managed_paths = _delete_paper_data(db, context)
                for dependent in db.scalars(
                    select(ArchivedItem).where(
                        (
                            (ArchivedItem.kind == "job")
                            & ArchivedItem.target_id.in_(context["job_ids"])
                        )
                        | (
                            (ArchivedItem.kind == "paper_legacy_content")
                            & (ArchivedItem.target_id == target_id)
                        )
                    )
                ):
                    _mark_purged(dependent)
                if managed_paths:
                    item.status = "purging"
                    item.restore_json = {
                        "managed_paths": managed_paths,
                        "result": result.model_dump(),
                    }
                    finish_files = True
        elif kind == "knowledge_paper":
            _purge_library_paper(db, target_id)
        elif kind == "knowledge_collection":
            collection = db.get(KnowledgeCollection, target_id)
            if collection is not None:
                _stop_collection_analysis(db, collection)
                db.delete(collection)
        elif kind == "model_connection":
            _purge_model_secrets(db, item, data_dir)
            profiles = select(ModelProfile.id).where(ModelProfile.connection_id == target_id)
            for dependent in db.scalars(
                select(ArchivedItem).where(
                    ArchivedItem.kind == "model_profile", ArchivedItem.target_id.in_(profiles)
                )
            ):
                _mark_purged(dependent)
            db.execute(delete(GlobalModelRole).where(GlobalModelRole.profile_id.in_(profiles)))
            db.execute(delete(ModelProfile).where(ModelProfile.connection_id == target_id))
            db.execute(delete(ModelConnection).where(ModelConnection.id == target_id))
        elif kind == "model_profile":
            _purge_model_secrets(db, item, data_dir)
            db.execute(delete(GlobalModelRole).where(GlobalModelRole.profile_id == target_id))
            db.execute(delete(ModelProfile).where(ModelProfile.id == target_id))
        else:
            job = db.get(Job, target_id)
            if job is not None:
                _purge_unreferenced_job(db, job)
        if not finish_files:
            _mark_purged(item)
    if finish_files:
        return _finish_paper_file_purge(engine, item_id, data_dir)
    return result


def _replayed(db: Session, key: str, body: dict[str, Any]) -> dict[str, Any] | None:
    previous = db.get(Idempotency, key)
    if previous is None:
        return None
    if previous.request_hash != digest(body):
        raise _failure(409, "IDEMPOTENCY_CONFLICT", "同一操作标识不能用于不同内容")
    return previous.response


def _remember(db: Session, key: str, body: dict[str, Any], result: dict[str, Any]) -> None:
    db.add(Idempotency(key=key, request_hash=digest(body), response=result))


def register_archive_api(app: FastAPI, engine: Callable[[], Engine], data_dir: Path) -> None:
    path = "/api/v1/archive"

    @app.get(path, response_model=ArchiveList)
    def list_archive(
        kind: ArchiveKind | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ) -> ArchiveList:
        filters: list[ColumnElement[bool]] = [ArchivedItem.status.in_(("archived", "purging"))]
        if kind is not None:
            filters.append(ArchivedItem.kind == kind)
        with read_session(engine()) as db:
            total = db.scalar(select(func.count()).select_from(ArchivedItem).where(*filters)) or 0
            items = db.scalars(
                select(ArchivedItem)
                .where(*filters)
                .order_by(ArchivedItem.archived_at.desc(), ArchivedItem.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return ArchiveList(
                items=[ArchiveItem.model_validate(row) for row in items], total=total
            )

    @app.post(path, response_model=ArchiveItem)
    def archive(body: ArchiveCreate, idempotency_key: Key) -> ArchiveItem:
        payload = body.model_dump(mode="json")
        key = "archive-create:" + idempotency_key
        with Session(engine()) as db, db.begin():
            previous = _replayed(db, key, payload)
            if previous:
                item = _archived_item(db, previous["id"])
                if item.status == "purged":
                    raise _failure(409, "ARCHIVE_ALREADY_PURGED", "该归档条目已彻底清除")
            else:
                item = archive_target(db, body.kind, str(body.target_id))
                _remember(db, key, payload, {"id": item.id})
            return ArchiveItem.model_validate(item)

    @app.post(path + "/{item_id}/restore", response_model=ArchiveAction)
    def restore(item_id: UUID, idempotency_key: Key) -> ArchiveAction:
        payload = {"id": str(item_id)}
        key = "archive-restore:" + idempotency_key
        with Session(engine()) as db, db.begin():
            if not _replayed(db, key, payload):
                restore_target(db, _archived_item(db, str(item_id)))
                _remember(db, key, payload, {"ok": True})
        return ArchiveAction()

    @app.delete(path + "/{item_id}", response_model=ArchivePurgeResult)
    def purge(item_id: UUID) -> ArchivePurgeResult:
        return purge_target(engine(), str(item_id), data_dir)
