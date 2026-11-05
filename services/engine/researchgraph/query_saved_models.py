"""Explicit saved Query knowledge, independently layered over immutable paper knowledge."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class QuerySavedKnowledge(Base):
    __tablename__ = "query_saved_knowledge"
    __table_args__ = (UniqueConstraint("project_id", "fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(Text)
    source_query_id: Mapped[str] = mapped_column(ForeignKey("query_runs.id"), index=True)
    answer_version_id: Mapped[str] = mapped_column(ForeignKey("query_answer_versions.id"))
    document_id: Mapped[str] = mapped_column(ForeignKey("query_documents.id"))
    document_version_id: Mapped[str] = mapped_column(ForeignKey("query_document_versions.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    selected_passage_refs: Mapped[list[str]] = mapped_column(JSON)
    passage_ids: Mapped[list[str]] = mapped_column(JSON)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    graph_revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))


class QuerySavedPreference(Base):
    """User-owned library metadata; immutable saved/model/source records stay unchanged."""

    __tablename__ = "query_saved_preferences"
    saved_id: Mapped[str] = mapped_column(ForeignKey("query_saved_knowledge.id"), primary_key=True)
    annotation: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)
    removed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(40))
