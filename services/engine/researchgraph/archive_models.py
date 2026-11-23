"""Local archive lifecycle kept separate from source data and task receipts."""

from typing import Any, Literal

from sqlalchemy import JSON, ColumnElement, Index, String, Text, UniqueConstraint, exists, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql.expression import SQLColumnExpression

from researchgraph.models import Base

ArchiveKind = Literal[
    "paper",
    "knowledge_paper",
    "knowledge_collection",
    "model_connection",
    "job",
    "paper_legacy_content",
    "model_profile",
]


class ArchivedItem(Base):
    __tablename__ = "archived_items"
    __table_args__ = (
        UniqueConstraint("kind", "target_id", name="uq_archive_target"),
        Index("ix_archive_status_time", "status", "archived_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[ArchiveKind] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    archived_at: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12), default="archived")
    restore_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


def archived_target(db: Session, kind: ArchiveKind, target_id: str) -> ArchivedItem | None:
    return db.scalar(
        select(ArchivedItem).where(ArchivedItem.kind == kind, ArchivedItem.target_id == target_id)
    )


def active_target(kind: ArchiveKind, column: SQLColumnExpression[str]) -> ColumnElement[bool]:
    return ~exists().where(ArchivedItem.kind == kind, ArchivedItem.target_id == column)
