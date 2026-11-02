"""Additive P3 persistence; original extraction nodes and outputs stay immutable."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class ReasoningAttempt(Base):
    __tablename__ = "reasoning_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"))
    mode: Mapped[str] = mapped_column(String(24))
    comparison: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    model_run_ids: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class ProposalColumns:
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("reasoning_attempts.id"), unique=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(24))
    rationale: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(24), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))


class RelationAssertion(ProposalColumns, Base):
    __tablename__ = "relation_assertions"


class AlignmentCandidate(ProposalColumns, Base):
    __tablename__ = "entity_alignments"


class SemanticReview(Base):
    __tablename__ = "semantic_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    relation_id: Mapped[str | None] = mapped_column(ForeignKey("relation_assertions.id"))
    alignment_id: Mapped[str | None] = mapped_column(ForeignKey("entity_alignments.id"))
    action: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(Text)
    before: Mapped[dict[str, Any]] = mapped_column(JSON)
    after: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))
