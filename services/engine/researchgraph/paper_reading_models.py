"""Whole-paper notes freeze a source-mapped projection; old A02 rows stay intact."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base, now


class PaperReadingResult(Base):
    __tablename__ = "lite_paper_readings"
    __table_args__ = (
        Index("ix_paper_reading_scope_updated", "paper_id", "document_version_id", "updated_at"),
        UniqueConstraint("job_id", name="uq_paper_reading_job"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("attachment_revisions.id"), index=True
    )
    projection_version: Mapped[str] = mapped_column(String(80))
    projection_hash: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(80))
    provider_id: Mapped[str] = mapped_column(String(80))
    model_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    analysis_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    missing_paragraph_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
