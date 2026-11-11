"""Derived PDF translations are separate from authoritative paper revisions."""

from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class PDFTranslationSettings(Base):
    __tablename__ = "pdf_translation_settings"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    service_url: Mapped[str] = mapped_column(Text)
    launch_mode: Mapped[str] = mapped_column(
        String(16), default="bundled", server_default="bundled"
    )
    python_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    server_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class PDFTranslation(Base):
    __tablename__ = "pdf_translations"
    __table_args__ = (
        Index("ix_pdf_translations_paper_created", "paper_id", "created_at"),
        Index("ix_pdf_translations_cache", "cache_key", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"))
    document_version_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    source_hash: Mapped[str] = mapped_column(String(64))
    profile_id: Mapped[str] = mapped_column(String(36))
    model_id: Mapped[str] = mapped_column(Text)
    model_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    output_mode: Mapped[str] = mapped_column(String(16), default="both", server_default="both")
    runtime_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    cache_key: Mapped[str] = mapped_column(String(64))
    service_url: Mapped[str] = mapped_column(Text)
    engine_version: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24))
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer)
    progress: Mapped[float] = mapped_column(Float, default=0)
    stage: Mapped[str] = mapped_column(String(40))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True)
    external_task_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_state: Mapped[str] = mapped_column(String(24), default="not_started")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON)
    artifacts: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    max_calls: Mapped[int] = mapped_column(Integer)
    max_input_tokens: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
