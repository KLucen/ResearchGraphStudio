"""Small, centralized checks for the additive Lite experience mode."""

from sqlalchemy.orm import Session

from researchgraph.models import Job, Project, now


def is_lite_project(session: Session, project_id: str | None) -> bool:
    if not project_id:
        return False
    project = session.get(Project, project_id)
    return bool(project and getattr(project, "experience_mode", "legacy") == "lite")


def block_model_job(session: Session, job: Job, *, code: str = "LITE_MODE_DISABLED") -> None:
    """Finish a queued/running legacy model job without calling a provider."""

    if job.status not in {"queued", "running"}:
        return
    job.status = "failed"
    job.error = "Lite 模式默认关闭完整知识图谱模型任务；请使用本地阅读流程"
    job.updated_at = now()
    job.result = {**(job.result or {}), "error_code": code, "model_calls": 0}
