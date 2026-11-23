"""Read-only global project and paper search for the personal workspace."""

from collections.abc import Callable
from typing import Literal

from fastapi import FastAPI, Query
from sqlalchemy import Engine, func, literal, select, union_all

from researchgraph.archive_models import active_target
from researchgraph.core import StrictModel
from researchgraph.models import Paper, Project
from researchgraph.schemas import ProjectView
from researchgraph.storage import read_session


class WorkspaceSearchHit(StrictModel):
    kind: Literal["project", "paper"]
    id: str
    title: str
    project: ProjectView


class WorkspaceSearchPage(StrictModel):
    items: list[WorkspaceSearchHit]
    total: int
    next_offset: int | None


def register_workspace_search_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    @app.get("/api/v1/workspace/search", response_model=WorkspaceSearchPage)
    def search_workspace(
        q: str = Query(min_length=1, max_length=200),
        offset: int = Query(0, ge=0, le=2_147_483_647),
        limit: int = Query(24, ge=1, le=50),
    ) -> WorkspaceSearchPage:
        term = q.strip().lower()
        if not term:
            return WorkspaceSearchPage(items=[], total=0, next_offset=None)
        matches = union_all(
            select(
                literal("project").label("kind"),
                Project.id.label("id"),
                Project.name.label("title"),
                Project.id.label("project_id"),
            ).where(
                func.lower(Project.name).contains(term, autoescape=True)
                | func.lower(Project.description).contains(term, autoescape=True)
            ),
            select(literal("paper"), Paper.id, Paper.title, Paper.project_id).where(
                func.lower(Paper.title).contains(term, autoescape=True),
                active_target("paper", Paper.id),
            ),
        ).subquery()
        with read_session(engine()) as db:
            total = db.scalar(select(func.count()).select_from(matches)) or 0
            rows = db.execute(
                select(matches.c.kind, matches.c.id, matches.c.title, Project)
                .join(Project, matches.c.project_id == Project.id)
                .order_by(
                    (func.lower(matches.c.title) != term),
                    func.lower(matches.c.title),
                    matches.c.kind,
                    matches.c.id,
                )
                .offset(offset)
                .limit(limit)
            ).all()
            return WorkspaceSearchPage(
                items=[
                    WorkspaceSearchHit(
                        kind=kind,
                        id=identity,
                        title=title,
                        project=ProjectView.model_validate(project),
                    )
                    for kind, identity, title, project in rows
                ],
                total=total,
                next_offset=offset + limit if offset + limit < total else None,
            )
