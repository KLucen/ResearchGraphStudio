"""Private durable request slots; source deletion must not erase library accounting."""

from typing import Any

from sqlalchemy import JSON, Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base, now


class KnowledgeExtractionRun(Base):
    __tablename__ = "knowledge_extraction_runs"
    __table_args__ = (
        Index("ix_knowledge_extract_cache", "cache_key", "created_at"),
        Index("ix_knowledge_extract_input", "paper_id", "input_hash", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True)
    source_project_id: Mapped[str] = mapped_column(String(36), index=True)
    paper_id: Mapped[str] = mapped_column(String(36), index=True)
    library_paper_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(120))
    source_manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String(64))
    model_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cache_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    request_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    previous_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
