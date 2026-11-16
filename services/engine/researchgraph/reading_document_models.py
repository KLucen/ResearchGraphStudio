"""Versioned reading projections, independent of immutable extraction anchors."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class ReadingDocumentProjection(Base):
    __tablename__ = "lite_reading_documents"
    __table_args__ = (UniqueConstraint("document_version_id", "projection_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("attachment_revisions.id"), index=True
    )
    projection_version: Mapped[str] = mapped_column(String(80))
    source_hash: Mapped[str] = mapped_column(String(64))
    projection_hash: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
