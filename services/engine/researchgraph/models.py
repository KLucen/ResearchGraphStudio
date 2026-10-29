from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> str:
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class Event(Base):
    __tablename__ = "knowledge_events"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class Idempotency(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)


class Paper(Base):
    __tablename__ = "papers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))


class AttachmentRevision(Base):
    __tablename__ = "attachment_revisions"
    __table_args__ = (UniqueConstraint("paper_id", "sha256"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(80))
    page_count: Mapped[int] = mapped_column(Integer)
    warnings: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class PaperSource(Base):
    __tablename__ = "paper_sources"
    __table_args__ = (UniqueConstraint("paper_id", "path", "mode"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    path: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20))
    managed_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("revision_id", "page_index", "block_index"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"), index=True)
    page_index: Mapped[int] = mapped_column(Integer)
    page_label: Mapped[str] = mapped_column(Text)
    block_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    bbox: Mapped[list[float]] = mapped_column(JSON)
