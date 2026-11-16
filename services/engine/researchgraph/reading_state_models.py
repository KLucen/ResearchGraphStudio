"""Subjective reading state, deliberately separate from LightGraph semantics."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base, now


class ReadingState(Base):
    __tablename__ = "lite_reading_states"
    __table_args__ = (
        UniqueConstraint("paper_id", "document_version_id", "section_id"),
        Index("ix_lite_reading_state_paper", "paper_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"))
    source_hash: Mapped[str] = mapped_column(String(64))
    progress: Mapped[str] = mapped_column(String(16), default="NOT_STARTED")
    self_assessment: Mapped[str] = mapped_column(String(16), default="UNSET")
    unresolved_concept_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    graph_reference_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class ConceptUnderstanding(Base):
    __tablename__ = "lite_concept_understanding"
    __table_args__ = (
        UniqueConstraint("paper_id", "overview_result_id", "graph_node_id"),
        Index("ix_lite_concept_state_paper", "paper_id", "updated_at"),
        Index("ix_lite_concept_state_identity", "paper_id", "node_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    overview_result_id: Mapped[str] = mapped_column(ForeignKey("paper_overview_results.id"))
    graph_node_id: Mapped[str] = mapped_column(String(120))
    node_fingerprint: Mapped[str] = mapped_column(String(64))
    node_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    self_level: Mapped[str] = mapped_column(String(16), default="UNSET")
    last_check_result: Mapped[str] = mapped_column(String(24), default="NOT_CHECKED")
    note_zh: Mapped[str] = mapped_column(Text, default="")
    last_check_note_zh: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
