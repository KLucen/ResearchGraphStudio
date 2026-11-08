"""Reading projections reference existing knowledge; no second content store."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class CandidateMetadata(Base):
    __tablename__ = "candidate_metadata"
    node_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), primary_key=True)
    quality: Mapped[dict[str, Any]] = mapped_column(JSON)
    validation_status: Mapped[str] = mapped_column(String(24))
    canonical_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_nodes.id"))
    policy_version: Mapped[str] = mapped_column(String(40))


class ReadingUnit(Base):
    __tablename__ = "reading_units"
    __table_args__ = (
        Index("ix_reading_units_root_version", "root_claim_id", "document_version_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    root_claim_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    model_run_id: Mapped[str | None] = mapped_column(ForeignKey("model_runs.id"))
    rationale: Mapped[str] = mapped_column(String)


class ReadingMember(Base):
    __tablename__ = "reading_members"
    __table_args__ = (Index("ix_reading_members_node", "node_id"),)
    unit_id: Mapped[str] = mapped_column(ForeignKey("reading_units.id"), primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), primary_key=True)
    association_ids: Mapped[list[str]] = mapped_column(JSON)


class ReadingSelection(Base):
    __tablename__ = "reading_selections"
    __table_args__ = (UniqueConstraint("paper_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    revision: Mapped[int] = mapped_column(Integer)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class ReadingHead(Base):
    __tablename__ = "reading_heads"
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    selection_id: Mapped[str] = mapped_column(ForeignKey("reading_selections.id"))
    revision: Mapped[int] = mapped_column(Integer)


class ReadingPreference(Base):
    __tablename__ = "reading_preferences"
    node_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), primary_key=True)
    action: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(String)


class ReadingCheckpoint(Base):
    __tablename__ = "reading_checkpoints"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    stage: Mapped[str] = mapped_column(String(24))
    input_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
