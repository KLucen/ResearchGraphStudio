"""Personal chapter progress, scoped to a model-derived parse version."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class ModelChapterReadingState(Base):
    __tablename__ = "llm_chapter_reading_states"
    __table_args__ = (UniqueConstraint("parse_id", "chapter_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parse_id: Mapped[str] = mapped_column(
        ForeignKey("llm_document_parses.id", ondelete="CASCADE"), index=True
    )
    chapter_ref: Mapped[str] = mapped_column(String(160))
    progress: Mapped[str] = mapped_column(String(16), default="NOT_STARTED")
    updated_at: Mapped[str] = mapped_column(String(40))
