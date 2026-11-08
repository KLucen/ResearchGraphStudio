"""Origin of explicitly registered external Markdown in the shared document registry."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class ExternalDocumentVersion(Base):
    __tablename__ = "external_document_versions"
    version_id: Mapped[str] = mapped_column(
        ForeignKey("query_document_versions.id"), primary_key=True
    )
    root_id: Mapped[str] = mapped_column(ForeignKey("authorized_roots.id"), index=True)
    relative_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    attribution: Mapped[str] = mapped_column(String(32))
