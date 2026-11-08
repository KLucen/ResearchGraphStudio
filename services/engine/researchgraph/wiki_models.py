"""Wiki metadata extends the existing Query document registry, never its own body store."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class WikiPage(Base):
    __tablename__ = "wiki_pages"
    document_id: Mapped[str] = mapped_column(ForeignKey("query_documents.id"), primary_key=True)
    head_version_id: Mapped[str] = mapped_column(ForeignKey("query_document_versions.id"))
    created_at: Mapped[str] = mapped_column(String(40))


class WikiVersion(Base):
    __tablename__ = "wiki_versions"
    version_id: Mapped[str] = mapped_column(
        ForeignKey("query_document_versions.id"), primary_key=True
    )
    title: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    markdown: Mapped[str] = mapped_column(Text)
    references: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON)
    base_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class WikiSection(Base):
    __tablename__ = "wiki_sections"
    __table_args__ = (UniqueConstraint("version_id", "section_id"),)
    passage_id: Mapped[str] = mapped_column(ForeignKey("query_passages.id"), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("query_document_versions.id"), index=True)
    section_id: Mapped[str] = mapped_column(String(36), index=True)
    heading: Mapped[str] = mapped_column(Text)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    links: Mapped[list[str]] = mapped_column(JSON)
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class WikiWriteRoot(Base):
    __tablename__ = "wiki_write_roots"
    __table_args__ = (UniqueConstraint("project_id", "path"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    path: Mapped[str] = mapped_column(Text)
    device: Mapped[str] = mapped_column(String(40))
    inode: Mapped[str] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(default=True)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))


class WikiFileBinding(Base):
    __tablename__ = "wiki_file_bindings"
    __table_args__ = (UniqueConstraint("root_id", "relative_path"),)
    document_id: Mapped[str] = mapped_column(ForeignKey("query_documents.id"), primary_key=True)
    root_id: Mapped[str] = mapped_column(ForeignKey("wiki_write_roots.id"))
    relative_path: Mapped[str] = mapped_column(Text)
    version_id: Mapped[str] = mapped_column(ForeignKey("query_document_versions.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    device: Mapped[str] = mapped_column(String(40))
    inode: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class WikiPublication(Base):
    __tablename__ = "wiki_publications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("query_documents.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("query_document_versions.id"))
    root_id: Mapped[str] = mapped_column(ForeignKey("wiki_write_roots.id"))
    root_revision: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(200), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    relative_path: Mapped[str] = mapped_column(Text)
    base_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_hash: Mapped[str] = mapped_column(String(64))
    stage_identity: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    state: Mapped[str] = mapped_column(String(24))
    error: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class WikiFileObservation(Base):
    """Read-only diagnostic snapshot; never a Wiki version or inherited scientific source."""

    __tablename__ = "wiki_file_observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("query_documents.id"), index=True)
    root_id: Mapped[str] = mapped_column(ForeignKey("wiki_write_roots.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
