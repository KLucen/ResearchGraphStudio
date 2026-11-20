"""Persistent checkpoints for bounded model document batches."""

from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class LlmDocumentBatchRun(Base):
    __tablename__ = "llm_document_batch_runs"
    __table_args__ = (
        UniqueConstraint("import_session_id"),
        CheckConstraint("page_count > 0", name="ck_document_batch_run_page_count"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_session_id: Mapped[str] = mapped_column(
        ForeignKey("import_sessions.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    source_version: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    page_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class LlmDocumentBatch(Base):
    __tablename__ = "llm_document_batches"
    __table_args__ = (
        UniqueConstraint("run_id", "kind", "ordinal"),
        Index("ix_llm_document_batches_run_status", "run_id", "status"),
        CheckConstraint("kind IN ('extract', 'boundary')", name="ck_document_batch_kind"),
        CheckConstraint(
            "status IN ('pending', 'sent', 'validated', 'schema_failed', 'failed', 'uncertain')",
            name="ck_document_batch_status",
        ),
        CheckConstraint(
            "page_start > 0 AND page_end >= page_start AND send_start > 0 "
            "AND send_start <= page_start AND send_end >= page_end",
            name="ck_document_batch_page_range",
        ),
        CheckConstraint(
            "ordinal >= 0 AND attempts >= 0 AND repair_attempts >= 0 "
            "AND repair_attempts <= 1 AND request_count >= 0",
            name="ck_document_batch_counters",
        ),
        CheckConstraint(
            "result_json IS NULL OR status = 'validated'",
            name="ck_document_batch_validated_result",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("llm_document_batch_runs.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    send_start: Mapped[int] = mapped_column(Integer)
    send_end: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    repair_attempts: Mapped[int] = mapped_column(Integer, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class LlmDocumentBatchFailure(Base):
    """Private failed response and one explicit text-only repair authorization.

    The raw material is deliberately separate from Job diagnostics and public
    checkpoint DTOs. Deleting the import session cascades through its batch.
    """

    __tablename__ = "llm_document_batch_failures"
    __table_args__ = (
        CheckConstraint(
            "state IN ('available', 'authorized', 'sent', 'succeeded', 'failed')",
            name="ck_document_batch_failure_state",
        ),
        CheckConstraint(
            "source_request_count > 0 AND (authorized_attempt IS NULL OR authorized_attempt > 0)",
            name="ck_document_batch_failure_binding",
        ),
    )

    batch_id: Mapped[str] = mapped_column(
        ForeignKey("llm_document_batches.id", ondelete="CASCADE"), primary_key=True
    )
    raw_response: Mapped[str] = mapped_column(Text)
    repair_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_request_count: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default="available")
    authorized_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
