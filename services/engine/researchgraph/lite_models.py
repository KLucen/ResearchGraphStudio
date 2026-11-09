"""Lite model usage and source-scoped response cache."""

from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class LiteTokenUsage(Base):
    __tablename__ = "lite_token_usage"
    __table_args__ = (
        Index("ix_lite_usage_project_created", "project_id", "created_at"),
        Index("ix_lite_usage_project_kind", "project_id", "task_kind"),
        Index("ix_lite_usage_paper", "paper_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"))
    document_version_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id"), nullable=True)
    task_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_kind: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_source: Mapped[str] = mapped_column(String(16), default="unknown")
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="succeeded")
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40))


class LiteCacheEntry(Base):
    __tablename__ = "lite_cache_entries"
    __table_args__ = (
        Index("ix_lite_cache_project_kind", "project_id", "task_kind"),
        Index("ix_lite_cache_document", "document_version_id", "task_kind"),
    )

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    task_kind: Mapped[str] = mapped_column(String(24))
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"))
    document_version_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id"), nullable=True)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(80))
    schema_version: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(Text)
    config_fingerprint: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="fresh")
    stale_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
