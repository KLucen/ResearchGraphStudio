import asyncio
import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from filelock import FileLock
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from researchgraph import PROTOCOL_VERSION, __version__
from researchgraph.ingest import import_pdf
from researchgraph.models import (
    AttachmentRevision,
    Chunk,
    Event,
    Idempotency,
    Job,
    Paper,
    PaperSource,
    Project,
    now,
)
from researchgraph.schemas import (
    ChunkList,
    ChunkView,
    Health,
    JobCreate,
    JobView,
    PaperDetail,
    PaperList,
    PaperView,
    PdfImport,
    ProjectCreate,
    ProjectList,
    ProjectView,
    RevisionView,
    SourceView,
)
from researchgraph.storage import SCHEMA_HEAD, diagnostics, make_engine, migrate

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=120)]


def failure(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def remembered(session: Session, key: str, body: dict[str, Any]) -> dict[str, Any] | None:
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    item = session.get(Idempotency, key)
    if item:
        if item.request_hash != digest:
            raise failure(409, "IDEMPOTENCY_CONFLICT", "同一个请求标识不能用于不同内容")
        return item.response
    return None


def remember(session: Session, key: str, body: dict[str, Any], response: dict[str, Any]) -> None:
    session.add(
        Idempotency(
            key=key,
            request_hash=hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
            response=response,
        )
    )


async def worker(engine: Engine, data_dir: Path) -> None:
    while True:
        job_id: str | None = None
        kind = "diagnostics"
        with Session(engine) as session, session.begin():
            job = session.scalar(select(Job).where(Job.status == "queued").order_by(Job.created_at))
            if job:
                job_id = job.id
                kind = job.kind
                job.status, job.updated_at = "running", now()
                job.attempt += 1
        if job_id is None:
            await asyncio.sleep(0.15)
            continue
        result: dict[str, str | bool] | None = None
        error = None
        try:
            if kind == "pdf_import":
                await import_pdf(engine, job_id, data_dir)
                continue
            result = await asyncio.to_thread(diagnostics, engine)
        except Exception as exc:
            error = (
                str(exc)
                if kind == "pdf_import" and isinstance(exc, ValueError)
                else "任务失败，请检查文件或数据库权限"
            )
        with Session(engine) as session, session.begin():
            current = session.get(Job, job_id)
            if current and current.status == "running":
                current.status = "failed" if error else "succeeded"
                current.result, current.error, current.updated_at = result, error, now()


def create_app(
    data_dir: Path,
    token: str,
    *,
    start_worker: bool = True,
    ready: Callable[[], None] | None = None,
) -> FastAPI:
    if len(token) < 32:
        raise ValueError("会话令牌至少需要 32 个字符")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        data_dir.mkdir(parents=True, exist_ok=True)
        lock = FileLock(data_dir / "engine.lock", timeout=0)
        with lock:
            engine = make_engine(data_dir)
            app.state.engine = engine
            task = None
            try:
                migrate(engine, data_dir)
                diagnostics(engine)
                with Session(engine) as session, session.begin():
                    session.execute(
                        update(Job)
                        .where(Job.status == "running")
                        .values(
                            status="interrupted", error="上次运行中断，可手动重试", updated_at=now()
                        )
                    )
                if start_worker:
                    task = asyncio.create_task(worker(engine, data_dir))
                if ready:
                    ready()
                yield
            finally:
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                with Session(engine) as session, session.begin():
                    # Best effort during normal shutdown; restart also recovers interrupted jobs.
                    if engine.dialect.has_table(session.connection(), "jobs"):
                        session.execute(
                            update(Job)
                            .where(Job.status == "running")
                            .values(
                                status="interrupted", error="应用退出，任务已中断", updated_at=now()
                            )
                        )
                engine.dispose()

    app = FastAPI(title="ResearchGraph Engine", version=__version__, lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def authenticate(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = str(uuid4())
        if request.headers.get("origin"):
            return error_response(request, 403, "ORIGIN_DENIED", "仅允许桌面宿主访问")
        if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
            return error_response(request, 401, "UNAUTHORIZED", "缺少有效会话令牌")
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "retryable": status >= 500,
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return error_response(
            request, exc.status_code, detail.get("code", "HTTP_ERROR"), detail["message"]
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "INVALID_INPUT", "输入格式错误，请检查字段与请求标识")

    def engine() -> Engine:
        return cast(Engine, app.state.engine)

    @app.get("/api/v1/health", response_model=Health)
    def health() -> Health:
        return Health(
            version=__version__,
            protocol_version=PROTOCOL_VERSION,
            schema_version=SCHEMA_HEAD,
            fts5=True,
        )

    @app.get("/api/v1/projects", response_model=ProjectList)
    def projects(cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)) -> ProjectList:
        with Session(engine()) as session:
            rows = session.scalars(
                select(Project)
                .order_by(Project.created_at.desc(), Project.id)
                .offset(cursor)
                .limit(limit + 1)
            ).all()
            return ProjectList(
                items=[ProjectView.model_validate(p) for p in rows[:limit]],
                next_cursor=cursor + limit if len(rows) > limit else None,
            )

    @app.post("/api/v1/projects", response_model=ProjectView, status_code=201)
    def create_project(body: ProjectCreate, idempotency_key: Key) -> ProjectView:
        key, payload = f"project:{idempotency_key}", body.model_dump()
        with Session(engine()) as session, session.begin():
            previous = remembered(session, key, payload)
            if previous:
                return ProjectView.model_validate(previous)
            project = Project(id=str(uuid4()), created_at=now(), **payload)
            session.add(project)
            session.flush()
            session.add(
                Event(
                    event_id=str(uuid4()),
                    project_id=project.id,
                    event_type="PROJECT_CREATED",
                    payload=payload,
                    created_at=now(),
                )
            )
            response = ProjectView.model_validate(project)
            remember(session, key, payload, response.model_dump())
            return response

    @app.get("/api/v1/jobs", response_model=list[JobView])
    def jobs() -> list[JobView]:
        with Session(engine()) as session:
            return [
                JobView.model_validate(j)
                for j in session.scalars(select(Job).order_by(Job.created_at.desc()).limit(50))
            ]

    @app.post("/api/v1/jobs", response_model=JobView, status_code=202)
    def create_job(body: JobCreate, idempotency_key: Key) -> JobView:
        key, payload = f"job:{idempotency_key}", body.model_dump()
        with Session(engine()) as session, session.begin():
            previous = remembered(session, key, payload)
            if previous:
                return JobView.model_validate(previous)
            job = Job(
                id=str(uuid4()),
                kind=body.kind,
                status="queued",
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
            session.add(job)
            response = JobView.model_validate(job)
            remember(session, key, payload, response.model_dump())
            return response

    @app.get("/api/v1/jobs/{job_id}", response_model=JobView)
    def get_job(job_id: str) -> JobView:
        with Session(engine()) as session:
            job = session.get(Job, job_id)
            if not job:
                raise failure(404, "JOB_NOT_FOUND", "任务不存在")
            return JobView.model_validate(job)

    @app.post("/api/v1/jobs/{job_id}/{action}", response_model=JobView)
    def change_job(job_id: str, action: str, idempotency_key: Key) -> JobView:
        if action not in {"cancel", "retry"}:
            raise failure(404, "ACTION_NOT_FOUND", "操作不存在")
        key, payload = f"job-action:{idempotency_key}", {"job_id": job_id, "action": action}
        with Session(engine()) as session, session.begin():
            previous = remembered(session, key, payload)
            if previous:
                return JobView.model_validate(previous)
            job = session.get(Job, job_id)
            if not job:
                raise failure(404, "JOB_NOT_FOUND", "任务不存在")
            if action == "cancel" and job.status in {"queued", "running"}:
                job.status = "cancelled"
            elif (
                action == "retry"
                and job.status in {"failed", "interrupted", "cancelled"}
                and job.attempt < 3
            ):
                job.status, job.error, job.result = "queued", None, None
            else:
                raise failure(409, "JOB_STATE_CONFLICT", "任务状态已改变或达到重试上限")
            job.updated_at = now()
            response = JobView.model_validate(job)
            remember(session, key, payload, response.model_dump())
            return response

    @app.post(
        "/api/v1/projects/{project_id}/papers/import/pdf", response_model=JobView, status_code=202
    )
    def queue_pdf(project_id: str, body: PdfImport, idempotency_key: Key) -> JobView:
        path = Path(body.path)
        if not path.is_absolute() or path.suffix.lower() != ".pdf":
            raise failure(422, "INVALID_PDF_PATH", "请选择绝对路径的 PDF 文件")
        payload = {"path": str(path.resolve()), "mode": body.mode, "project_id": project_id}
        key = f"pdf-import:{idempotency_key}"
        with Session(engine()) as session, session.begin():
            if not session.get(Project, project_id):
                raise failure(404, "PROJECT_NOT_FOUND", "项目不存在")
            previous = remembered(session, key, payload)
            if previous:
                return JobView.model_validate(previous)
            job = Job(
                id=str(uuid4()),
                kind="pdf_import",
                project_id=project_id,
                payload=payload,
                status="queued",
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
            session.add(job)
            response = JobView.model_validate(job)
            remember(session, key, payload, response.model_dump())
            return response

    @app.get("/api/v1/projects/{project_id}/papers", response_model=PaperList)
    def papers(
        project_id: str, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
    ) -> PaperList:
        with Session(engine()) as session:
            if not session.get(Project, project_id):
                raise failure(404, "PROJECT_NOT_FOUND", "项目不存在")
            rows = session.scalars(
                select(Paper)
                .where(Paper.project_id == project_id)
                .order_by(Paper.created_at.desc(), Paper.id)
                .offset(cursor)
                .limit(limit + 1)
            ).all()
            return PaperList(
                items=[PaperView.model_validate(p) for p in rows[:limit]],
                next_cursor=cursor + limit if len(rows) > limit else None,
            )

    @app.get("/api/v1/papers/{paper_id}", response_model=PaperDetail)
    def paper_detail(paper_id: str) -> PaperDetail:
        with Session(engine()) as session:
            paper = session.get(Paper, paper_id)
            if not paper:
                raise failure(404, "PAPER_NOT_FOUND", "文献不存在")
            return PaperDetail(
                paper=PaperView.model_validate(paper),
                revisions=[
                    RevisionView.model_validate(r)
                    for r in session.scalars(
                        select(AttachmentRevision)
                        .where(AttachmentRevision.paper_id == paper_id)
                        .order_by(AttachmentRevision.created_at.desc(), AttachmentRevision.id)
                    )
                ],
                sources=[
                    SourceView.model_validate(s)
                    for s in session.scalars(
                        select(PaperSource).where(PaperSource.paper_id == paper_id)
                    )
                ],
            )

    @app.get("/api/v1/revisions/{revision_id}/chunks", response_model=ChunkList)
    def chunks(
        revision_id: str, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
    ) -> ChunkList:
        with Session(engine()) as session:
            if not session.get(AttachmentRevision, revision_id):
                raise failure(404, "REVISION_NOT_FOUND", "附件修订不存在")
            rows = session.scalars(
                select(Chunk)
                .where(Chunk.revision_id == revision_id)
                .order_by(Chunk.page_index, Chunk.block_index)
                .offset(cursor)
                .limit(limit + 1)
            ).all()
            return ChunkList(
                items=[ChunkView.model_validate(c) for c in rows[:limit]],
                next_cursor=cursor + limit if len(rows) > limit else None,
            )

    return app
