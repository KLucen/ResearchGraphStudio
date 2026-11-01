"""Additive v2 storage. Paper/AttachmentRevision/Chunk remain the source authority."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class Section(Base):
    __tablename__ = "sections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("attachment_revisions.id"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(24))
    parser: Mapped[str] = mapped_column(String(40))


class EvidenceSpan(Base):
    __tablename__ = "evidence_spans"
    __table_args__ = (UniqueConstraint("paragraph_id", "start_offset", "end_offset"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("attachment_revisions.id"), index=True
    )
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"))
    paragraph_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"))
    page_index: Mapped[int] = mapped_column(Integer)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    normalization: Mapped[str] = mapped_column(String(40))
    bbox_list: Mapped[list[list[float]]] = mapped_column(JSON)


class GraphRevision(Base):
    __tablename__ = "graph_revisions"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(Text)
    prompt_name: Mapped[str] = mapped_column(String(80))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(24))
    input_hash: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32))
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (UniqueConstraint("document_version_id", "fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("attachment_revisions.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(24), index=True)
    text: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    origin: Mapped[str] = mapped_column(String(40))
    authorship: Mapped[str] = mapped_column(String(24))
    source_status: Mapped[str] = mapped_column(String(24), index=True)
    review_status: Mapped[str] = mapped_column(String(24), index=True)
    issues: Mapped[list[str]] = mapped_column(JSON)
    dimension: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    known_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    model_run_id: Mapped[str | None] = mapped_column(ForeignKey("model_runs.id"), nullable=True)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class NodeEvidence(Base):
    __tablename__ = "node_evidence_links"
    node_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_spans.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(24))


class KnowledgeDependency(Base):
    __tablename__ = "knowledge_dependencies"
    node_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), primary_key=True)
    dependee_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), primary_key=True)


class KnowledgeOperation(Base):
    __tablename__ = "knowledge_operations"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    action: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    before: Mapped[dict[str, Any]] = mapped_column(JSON)
    after: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class ZoteroLink(Base):
    __tablename__ = "zotero_links"
    __table_args__ = (UniqueConstraint("paper_id", "library_id", "item_key", "attachment_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("attachment_revisions.id"))
    library_id: Mapped[str] = mapped_column(String(80))
    item_key: Mapped[str] = mapped_column(String(8))
    attachment_key: Mapped[str] = mapped_column(String(8))
    metadata_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (UniqueConstraint("link_id", "annotation_key", "source_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    link_id: Mapped[str] = mapped_column(ForeignKey("zotero_links.id"))
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("attachment_revisions.id"), index=True
    )
    annotation_key: Mapped[str] = mapped_column(String(8))
    annotation_type: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    comment: Mapped[str] = mapped_column(Text)
    source_position: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_hash: Mapped[str] = mapped_column(String(64))
    anchor_status: Mapped[str] = mapped_column(String(24))
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence_spans.id"), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))


class AuthorizedRoot(Base):
    __tablename__ = "authorized_roots"
    __table_args__ = (UniqueConstraint("project_id", "path"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    path: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[str] = mapped_column(String(40))


class NoteSnapshot(Base):
    __tablename__ = "note_snapshots"
    __table_args__ = (UniqueConstraint("root_id", "relative_path", "sha256"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    root_id: Mapped[str] = mapped_column(ForeignKey("authorized_roots.id"), index=True)
    relative_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
