"""Persistence models for Lite's PaperCard + LightGraph overview.

The overview is deliberately isolated from the legacy knowledge graph tables.  The
model output stores semantic JSON only; canvas coordinates live in a separate table.
"""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base, now


class PaperOverviewResult(Base):
    __tablename__ = "paper_overview_results"
    __table_args__ = (
        Index("ix_paper_overview_cache_key", "cache_key", "created_at"),
        Index("ix_paper_overview_paper_updated", "paper_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("attachment_revisions.id"), index=True
    )
    pdf_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    cache_key: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(80))
    provider_id: Mapped[str] = mapped_column(String(80))
    model_id: Mapped[str] = mapped_column(Text)
    paper_card_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    graph_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    graph_status: Mapped[str] = mapped_column(String(32), default="READY")
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class PaperGraphLayout(Base):
    __tablename__ = "paper_graph_layouts"
    __table_args__ = (
        UniqueConstraint("overview_result_id", "node_id", name="uq_paper_graph_layout_node"),
        Index("ix_paper_graph_layout_paper", "paper_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    overview_result_id: Mapped[str] = mapped_column(
        ForeignKey("paper_overview_results.id"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(120))
    x: Mapped[float] = mapped_column()
    y: Mapped[float] = mapped_column()
    pinned: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class PaperGraphViewport(Base):
    __tablename__ = "paper_graph_viewports"
    overview_result_id: Mapped[str] = mapped_column(
        ForeignKey("paper_overview_results.id"), primary_key=True
    )
    x: Mapped[float] = mapped_column(default=0.0)
    y: Mapped[float] = mapped_column(default=0.0)
    zoom: Mapped[float] = mapped_column(default=1.0)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
