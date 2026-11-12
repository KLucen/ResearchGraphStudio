"""Stop removed features without deleting their historical records or files.

Translation schemas remain importable only for compatibility with installed Lite
databases. This module has no model, network, subprocess, or artifact access.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.models import Job, now
from researchgraph.translation_models import PDFTranslation

TRANSLATION_REMOVED = "FEATURE_REMOVED"
TRANSLATION_REMOVED_MESSAGE = "文献翻译功能已移除，未完成任务已停止，不会自动调用模型"


def retire_translation_jobs(session: Session, job_id: str | None = None) -> int:
    """Cancel unfinished translation work; terminal history and usage are immutable."""
    timestamp = now()
    jobs = session.scalars(
        select(Job).where(
            Job.kind == "pdf_translation",
            Job.status.in_(("queued", "running")),
            *([Job.id == job_id] if job_id else []),
        )
    ).all()
    for job in jobs:
        job.status, job.stage = "cancelled", "interrupted"
        job.error, job.updated_at = TRANSLATION_REMOVED_MESSAGE, timestamp
    records = session.scalars(
        select(PDFTranslation).where(
            PDFTranslation.status.in_(("PENDING", "RUNNING")),
            *([PDFTranslation.job_id == job_id] if job_id else []),
        )
    ).all()
    for record in records:
        record.status, record.stage = "CANCELLED", "disabled"
        record.error_code, record.error = TRANSLATION_REMOVED, TRANSLATION_REMOVED_MESSAGE
        record.updated_at = timestamp
    return len(jobs)
