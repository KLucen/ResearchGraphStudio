"""Persistent planning records for model-first paper imports."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class ImportSession(Base):
    __tablename__ = "import_sessions"
    __table_args__ = (Index("ix_import_sessions_project_created", "project_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    source_kind: Mapped[str] = mapped_column(String(16))
    selection_id: Mapped[str] = mapped_column(String(200))
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="planned")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ImportPlanItem(Base):
    __tablename__ = "import_plan_items"
    __table_args__ = (
        UniqueConstraint("session_id", "item_kind"),
        Index("ix_import_plan_items_session_status", "session_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("import_sessions.id"), index=True)
    item_kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="planned")
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
