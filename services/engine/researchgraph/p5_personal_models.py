"""Purpose grants and last explicitly imported annotation heads; snapshots stay immutable."""

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class AnnotationUseGrant(Base):
    __tablename__ = "p5_annotation_use_grants"
    annotation_id: Mapped[str] = mapped_column(ForeignKey("annotations.id"), primary_key=True)
    allow_local: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_model: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class AnnotationHead(Base):
    __tablename__ = "p5_annotation_heads"
    link_id: Mapped[str] = mapped_column(ForeignKey("zotero_links.id"), primary_key=True)
    annotation_key: Mapped[str] = mapped_column(String(8), primary_key=True)
    annotation_id: Mapped[str] = mapped_column(ForeignKey("annotations.id"))
    removed: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=0)
