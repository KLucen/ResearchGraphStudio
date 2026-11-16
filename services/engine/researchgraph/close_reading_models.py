"""Local, source-versioned A02/A03 records, separate from reading self-assessments."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base, now


class _ReadingResult:
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("attachment_revisions.id"), index=True
    )
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"), index=True)
    paragraph_ids: Mapped[list[str]] = mapped_column(JSON)
    range_hash: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(80))
    provider_id: Mapped[str] = mapped_column(String(80))
    model_id: Mapped[str] = mapped_column(Text)
    usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class SectionCloseReadingResult(_ReadingResult, Base):
    __tablename__ = "lite_section_close_readings"
    __table_args__ = (
        Index("ix_close_reading_scope_updated", "paper_id", "section_id", "updated_at"),
        UniqueConstraint("job_id", name="uq_close_reading_job"),
    )
    analysis_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    missing_paragraph_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)


class UnderstandingCheckResult(_ReadingResult, Base):
    __tablename__ = "lite_understanding_checks"
    __table_args__ = (
        Index("ix_understanding_check_scope_updated", "paper_id", "section_id", "updated_at"),
        UniqueConstraint("job_id", name="uq_understanding_check_job"),
    )
    user_explanation: Mapped[str] = mapped_column(Text)
    check_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
