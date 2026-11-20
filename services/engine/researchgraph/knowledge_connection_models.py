"""Durable bounded cross-paper analysis, independent of project paper deletion."""

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base, now


class KnowledgeConnectionRun(Base):
    __tablename__ = "knowledge_connection_runs"
    __table_args__ = (Index("ix_kb_connection_input", "input_hash", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    library_paper_id: Mapped[str] = mapped_column(String(36), index=True)
    version_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_paper_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    previous_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class KnowledgeConnectionRequest(Base):
    __tablename__ = "knowledge_connection_requests"
    __table_args__ = (UniqueConstraint("run_id", "ordinal", name="uq_kb_connection_request"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_connection_runs.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="planned")
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    sent_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class KnowledgeConnectionReport(Base):
    __tablename__ = "knowledge_connection_reports"
    __table_args__ = (Index("ix_kb_reports_created", "created_at", "id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True)
    library_paper_id: Mapped[str] = mapped_column(String(36), index=True)
    version_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(Text)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class KnowledgeAnalysisEvent(Base):
    """One post-publication event per immutable version, retryable without resending."""

    __tablename__ = "knowledge_analysis_events"
    version_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state: Mapped[str] = mapped_column(String(24), default="pending")
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class KnowledgePairCheckpoint(Base):
    __tablename__ = "knowledge_pair_checkpoints"
    pair_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_a: Mapped[str] = mapped_column(String(36), index=True)
    version_b: Mapped[str] = mapped_column(String(36), index=True)
    report_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class KnowledgeUsageTombstone(Base):
    """Anonymous usage survives a purge; no source IDs or text remain."""

    __tablename__ = "knowledge_usage_tombstones"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_kind: Mapped[str] = mapped_column(String(40))
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class KnowledgeCollectionEvent(Base):
    """Atomic parsing receipt: restart considers only explicitly authorized events."""

    __tablename__ = "knowledge_collection_events"
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(String(36), index=True)
    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(120))
    source_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    extraction_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
