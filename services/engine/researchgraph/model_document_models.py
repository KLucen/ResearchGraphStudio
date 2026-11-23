"""Persisted model-first document parsing artifacts.

These tables are deliberately separate from AttachmentRevision/Chunk/Section.
Legacy local parsing remains the source for those tables; model-derived text,
formulas and tables are stored here until a later projection explicitly opts in.
"""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class LlmDocumentParse(Base):
    __tablename__ = "llm_document_parses"
    __table_args__ = (
        Index("ix_llm_document_parses_session", "import_session_id", "created_at"),
        Index("ix_llm_document_parses_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_session_id: Mapped[str] = mapped_column(
        ForeignKey("import_sessions.id", ondelete="CASCADE"), index=True
    )
    parse_version: Mapped[str] = mapped_column(String(80))
    provider_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    modality: Mapped[str] = mapped_column(String(16), default="text")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class LlmDocumentSegment(Base):
    __tablename__ = "llm_document_segments"
    __table_args__ = (
        Index("ix_llm_document_segments_parse_order", "parse_id", "ordinal"),
        Index("ix_llm_document_segments_parse_kind", "parse_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parse_id: Mapped[str] = mapped_column(
        ForeignKey("llm_document_parses.id", ondelete="CASCADE"), index=True
    )
    chapter_ref: Mapped[str] = mapped_column(String(160))
    chapter_title: Mapped[str] = mapped_column(Text)
    chapter_level: Mapped[int] = mapped_column(Integer, default=1)
    chapter_order: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(16))
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    latex: Mapped[str | None] = mapped_column(Text, nullable=True)
    mathml: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_table_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    table_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    locator: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="ok")
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(40))


class LlmDocumentOutput(Base):
    """Model-first overview/reading/translation output.

    These outputs intentionally do not point at legacy AttachmentRevision rows:
    a model-first import can be useful before local PDF structures exist.
    """

    __tablename__ = "llm_document_outputs"
    __table_args__ = (
        Index(
            "ix_llm_document_outputs_session_kind_created",
            "import_session_id",
            "item_kind",
            "created_at",
        ),
        Index("ix_llm_document_outputs_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_session_id: Mapped[str] = mapped_column(
        ForeignKey("import_sessions.id", ondelete="CASCADE"), index=True
    )
    parse_id: Mapped[str] = mapped_column(
        ForeignKey("llm_document_parses.id", ondelete="CASCADE"), index=True
    )
    item_kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    provider_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class LlmDocumentOutputLocalRecovery(Base):
    """User-triggered, source-versioned partial reading or card-set recovery."""

    __tablename__ = "llm_document_output_local_recoveries"

    output_id: Mapped[str] = mapped_column(
        ForeignKey("llm_document_outputs.id", ondelete="CASCADE"), primary_key=True
    )
    source_updated_at: Mapped[str] = mapped_column(String(40))
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    audit_json: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))
