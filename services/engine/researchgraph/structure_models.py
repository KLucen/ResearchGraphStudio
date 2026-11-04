"""Versioned parse artifacts alongside immutable PDF/chunk/evidence records."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class DocumentParse(Base):
    __tablename__ = "document_parses"
    __table_args__ = (UniqueConstraint("document_version_id", "parser_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("attachment_revisions.id"), index=True
    )
    parser_version: Mapped[str] = mapped_column(String(100))
    source_sha256: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))
