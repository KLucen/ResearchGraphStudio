"""User-controlled layouts for model-document overview graphs.

Semantic model results remain in ``llm_document_outputs``.  These tables store
only local canvas preferences and never become model input.
"""

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base, now


class ModelOverviewGraphLayout(Base):
    __tablename__ = "model_overview_graph_layouts"
    __table_args__ = (
        UniqueConstraint(
            "overview_result_id", "node_id", name="uq_model_overview_graph_layout_node"
        ),
        Index("ix_model_overview_graph_layout_paper", "paper_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    overview_result_id: Mapped[str] = mapped_column(
        ForeignKey("llm_document_outputs.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(120))
    x: Mapped[float] = mapped_column()
    y: Mapped[float] = mapped_column()
    pinned: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class ModelOverviewGraphViewport(Base):
    __tablename__ = "model_overview_graph_viewports"

    overview_result_id: Mapped[str] = mapped_column(
        ForeignKey("llm_document_outputs.id", ondelete="CASCADE"), primary_key=True
    )
    x: Mapped[float] = mapped_column()
    y: Mapped[float] = mapped_column()
    zoom: Mapped[float] = mapped_column()
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
