"""Import-session planning API for the model-first paper workflow.

This module only persists the plan and its retry state. A later document parser
worker consumes these records; creating or retrying a plan never calls a model.
"""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.models import Job, Project, now
from researchgraph.schemas import (
    ImportPlan,
    ImportPlanItemView,
    ImportSessionCreate,
    ImportSessionView,
    PdfPostImportPlan,
    SourceSnapshot,
)

ITEM_KINDS = ("document_parse", "paper_overview", "paper_reading", "translation")


def _failure(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def _view(session: ImportSession, items: list[ImportPlanItem]) -> ImportSessionView:
    value = ImportSessionView.model_validate(session)
    rank = {kind: index for index, kind in enumerate(ITEM_KINDS)}
    ordered = sorted(items, key=lambda item: (rank.get(item.item_kind, len(rank)), item.id))
    value.items = [ImportPlanItemView.model_validate(item) for item in ordered]
    return value


def _item_kinds(plan: dict[str, Any]) -> list[str]:
    kinds = ["document_parse"]
    if plan.get("overview"):
        kinds.append("paper_overview")
    if plan.get("reading"):
        kinds.append("paper_reading")
        if plan.get("translation_mode") == "full":
            kinds.append("translation")
    return kinds


def normalize_post_import_plan(value: PdfPostImportPlan | None) -> ImportPlan | None:
    """Map desktop-only modality labels to the persisted plan contract."""

    if value is None or not value.parse:
        return None
    return ImportPlan(
        overview=value.overview,
        reading=value.reading,
        translation_mode=value.translation_mode,
        modality="pdf",
        require_multimodal=value.modality == "required",
        allow_network=value.allow_network,
        provider_profile_id=value.provider_profile_id,
    )


def create_import_session_record(
    db: Session,
    *,
    project_id: str,
    source_kind: str,
    selection_id: str,
    source_snapshot: SourceSnapshot,
    plan: ImportPlan,
) -> tuple[ImportSession, list[ImportPlanItem]]:
    """Create the additive plan layer inside a caller-owned transaction."""

    timestamp = now()
    session = ImportSession(
        id=str(uuid4()),
        project_id=project_id,
        source_kind=source_kind,
        selection_id=selection_id,
        source_snapshot=source_snapshot.model_dump(exclude_none=True),
        plan=plan.model_dump(),
        status="planned",
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(session)
    db.flush()
    items: list[ImportPlanItem] = []
    for item_kind in _item_kinds(session.plan):
        item = ImportPlanItem(
            id=str(uuid4()),
            session_id=session.id,
            item_kind=item_kind,
            status="planned",
            config={
                "modality": session.plan["modality"],
                "require_multimodal": session.plan["require_multimodal"],
                "translation_mode": session.plan["translation_mode"],
            },
            attempt=0,
            created_at=timestamp,
            updated_at=timestamp,
        )
        db.add(item)
        items.append(item)
    return session, items


def register_import_plan_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    from researchgraph.app import Key, remember, remembered

    @app.post(
        "/api/v1/projects/{project_id}/import-sessions",
        response_model=ImportSessionView,
        status_code=202,
    )
    def create_import_session(
        project_id: str, body: ImportSessionCreate, idempotency_key: Key
    ) -> ImportSessionView:
        request = {"project_id": project_id, **body.model_dump()}
        key = "import-session:" + idempotency_key
        with Session(engine()) as db, db.begin():
            if db.get(Project, project_id) is None:
                raise _failure(404, "PROJECT_NOT_FOUND", "项目不存在")
            previous = remembered(db, key, request)
            if previous:
                return ImportSessionView.model_validate(previous)
            session, items = create_import_session_record(
                db,
                project_id=project_id,
                source_kind=body.source_kind,
                selection_id=body.selection_id,
                source_snapshot=body.source_snapshot,
                plan=body.plan,
            )
            response = _view(session, items)
            remember(db, key, request, response.model_dump())
            return response

    @app.get("/api/v1/import-sessions/{session_id}", response_model=ImportSessionView)
    def get_import_session(session_id: str) -> ImportSessionView:
        with Session(engine()) as db:
            session = db.get(ImportSession, session_id)
            if session is None:
                raise _failure(404, "IMPORT_SESSION_NOT_FOUND", "导入会话不存在")
            items = db.scalars(
                select(ImportPlanItem)
                .where(ImportPlanItem.session_id == session_id)
                .order_by(ImportPlanItem.created_at, ImportPlanItem.id)
            ).all()
            return _view(session, list(items))

    @app.get(
        "/api/v1/projects/{project_id}/import-sessions",
        response_model=list[ImportSessionView],
    )
    def list_import_sessions(project_id: str) -> list[ImportSessionView]:
        with Session(engine()) as db:
            if db.get(Project, project_id) is None:
                raise _failure(404, "PROJECT_NOT_FOUND", "项目不存在")
            sessions = db.scalars(
                select(ImportSession)
                .where(ImportSession.project_id == project_id)
                .order_by(ImportSession.created_at.desc(), ImportSession.id.desc())
                .limit(100)
            ).all()
            return [
                _view(
                    session,
                    list(
                        db.scalars(
                            select(ImportPlanItem)
                            .where(ImportPlanItem.session_id == session.id)
                            .order_by(ImportPlanItem.created_at, ImportPlanItem.id)
                        ).all()
                    ),
                )
                for session in sessions
            ]

    @app.post(
        "/api/v1/import-sessions/{session_id}/items/{item_kind}/retry",
        response_model=ImportSessionView,
    )
    def retry_import_item(
        session_id: str, item_kind: str, idempotency_key: Key
    ) -> ImportSessionView:
        if item_kind not in ITEM_KINDS:
            raise _failure(422, "INVALID_IMPORT_ITEM", "不支持的导入计划项")
        request = {"session_id": session_id, "item_kind": item_kind}
        key = "import-item-retry:" + idempotency_key
        with Session(engine()) as db, db.begin():
            session = db.get(ImportSession, session_id)
            if session is None:
                raise _failure(404, "IMPORT_SESSION_NOT_FOUND", "导入会话不存在")
            previous = remembered(db, key, request)
            if previous:
                return ImportSessionView.model_validate(previous)
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == session_id,
                    ImportPlanItem.item_kind == item_kind,
                )
            )
            if item is None:
                raise _failure(404, "IMPORT_ITEM_NOT_FOUND", "导入计划项不存在")
            if item.status not in {"failed", "interrupted", "paused"}:
                raise _failure(409, "IMPORT_ITEM_STATE_CONFLICT", "当前计划项不能重试")
            item.status = "queued"
            item.attempt += 1
            item.error = None
            item.updated_at = now()
            # Keep the plan item and its worker job in sync.  A failed model
            # parse/post-process item already owns a terminal Job; merely
            # changing the item status would leave that Job invisible to the
            # worker and make the advertised retry a no-op.  Requeue the same
            # idempotent payload, matching the ordinary /jobs/{id}/retry path.
            if item.job_id:
                job = db.get(Job, item.job_id)
                if job is not None and job.status in {
                    "failed",
                    "interrupted",
                    "cancelled",
                    "paused",
                }:
                    job.status, job.stage, job.error, job.updated_at = (
                        "queued",
                        None,
                        None,
                        now(),
                    )
            session.status = "queued"
            session.error = None
            session.updated_at = now()
            items = list(
                db.scalars(
                    select(ImportPlanItem)
                    .where(ImportPlanItem.session_id == session_id)
                    .order_by(ImportPlanItem.created_at, ImportPlanItem.id)
                ).all()
            )
            response = _view(session, items)
            remember(db, key, request, response.model_dump())
            return response
