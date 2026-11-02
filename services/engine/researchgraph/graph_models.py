"""Additive display/layout data; scientific objects keep their existing IDs and tables."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class KnowledgeDisplay(Base):
    __tablename__ = "knowledge_display"
    node_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"))
    source_revision: Mapped[int] = mapped_column(Integer)


class SourceAssertion(Base):
    __tablename__ = "source_assertions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    relation: Mapped[str] = mapped_column(String(32))
    evidence_ids: Mapped[list[str]] = mapped_column(JSON)
    model_run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"))


class GraphLayout(Base):
    __tablename__ = "graph_layouts"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    view_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[str] = mapped_column(Text)
