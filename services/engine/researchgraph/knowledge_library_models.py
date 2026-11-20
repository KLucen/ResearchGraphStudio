"""Durable, local knowledge snapshots, separate from disposable paper outputs."""

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base, now


class KnowledgeLibrary(Base):
    __tablename__ = "knowledge_libraries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="个人研究知识库")
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class LibraryPaper(Base):
    __tablename__ = "knowledge_library_papers"
    __table_args__ = (Index("ix_library_paper_updated", "library_id", "updated_at", "id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    library_id: Mapped[str] = mapped_column(ForeignKey("knowledge_libraries.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    identity_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    # The semantic snapshot stays immutable. Selecting its current version is a
    # user/library preference, not an overwrite of that snapshot.
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class LibraryPaperSourceLink(Base):
    __tablename__ = "knowledge_library_source_links"
    __table_args__ = (
        UniqueConstraint("original_paper_id", name="uq_library_source_original_paper"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    library_paper_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_library_papers.id", ondelete="CASCADE"), index=True
    )
    paper_id: Mapped[str | None] = mapped_column(
        ForeignKey("papers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    original_paper_id: Mapped[str] = mapped_column(String(36))
    # Historic project metadata survives removing an application paper/project.
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class PaperKnowledgeVersion(Base):
    __tablename__ = "paper_knowledge_versions"
    __table_args__ = (
        UniqueConstraint("library_paper_id", "snapshot_hash", name="uq_knowledge_snapshot"),
        Index("ix_knowledge_version_paper_created", "library_paper_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    library_paper_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_library_papers.id", ondelete="CASCADE"), index=True
    )
    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(120))
    source_paper_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(80))
    evidence_status: Mapped[str] = mapped_column(String(24))
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class KnowledgeCollection(Base):
    __tablename__ = "knowledge_collections"
    __table_args__ = (UniqueConstraint("library_id", "name", name="uq_knowledge_collection_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    library_id: Mapped[str] = mapped_column(ForeignKey("knowledge_libraries.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class KnowledgeCollectionMember(Base):
    __tablename__ = "knowledge_collection_members"

    collection_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_collections.id", ondelete="CASCADE"), primary_key=True
    )
    library_paper_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_library_papers.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class KnowledgeLibraryView(Base):
    __tablename__ = "knowledge_library_views"

    view_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    library_id: Mapped[str] = mapped_column(ForeignKey("knowledge_libraries.id"), index=True)
    layout_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
