"""Project-scoped P5 model preparation and explicit draft creation."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import FastAPI, Header
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.models import Project
from researchgraph.p5_contracts import WorkflowGenerate, WorkflowList, WorkflowPrepare, WorkflowView
from researchgraph.p5_models import P5Workflow
from researchgraph.p5_workflows import checked, enqueue, materialize, prepare, view
from researchgraph.schemas import JobView
from researchgraph.storage import read_session

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)]


def register_p5_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    base = "/api/v1/projects/{project_id}/workflows"

    @app.post(base + "/prepare", response_model=WorkflowView)
    def prepare_workflow(
        project_id: str, body: WorkflowPrepare, idempotency_key: Key
    ) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            row = prepare(session, project_id, body, idempotency_key)
            return view(session, row)

    @app.get(base, response_model=WorkflowList)
    def workflow_history(project_id: str) -> dict[str, Any]:
        with read_session(engine()) as session:
            if session.get(Project, project_id) is None:
                from researchgraph.knowledge_store import KnowledgeError

                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            return {
                "items": [
                    view(session, row)
                    for row in session.scalars(
                        select(P5Workflow)
                        .where(P5Workflow.project_id == project_id)
                        .order_by(P5Workflow.created_at.desc(), P5Workflow.id.desc())
                    )
                ]
            }

    @app.get(base + "/{workflow_id}", response_model=WorkflowView)
    def read_workflow(project_id: str, workflow_id: str) -> dict[str, Any]:
        with read_session(engine()) as session:
            return view(session, checked(session, project_id, workflow_id))

    @app.post(base + "/{workflow_id}/generate", response_model=JobView, status_code=202)
    def generate_workflow(
        project_id: str, workflow_id: str, body: WorkflowGenerate, idempotency_key: Key
    ) -> JobView:
        with Session(engine()) as session, session.begin():
            return JobView.model_validate(
                enqueue(
                    session,
                    checked(session, project_id, workflow_id),
                    idempotency_key,
                    continue_requested=body.continue_requested,
                )
            )

    @app.post(base + "/{workflow_id}/materialize")
    def create_workflow_draft(
        project_id: str, workflow_id: str, idempotency_key: Key
    ) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            return materialize(KnowledgeStore(session), project_id, workflow_id, idempotency_key)
