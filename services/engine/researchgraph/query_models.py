"""Additive Query/document execution state, separate from scientific graph objects."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class QueryRun(Base):
    __tablename__ = "query_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class QueryModelRun(Base):
    __tablename__ = "query_model_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query_run_id: Mapped[str] = mapped_column(ForeignKey("query_runs.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(Text)
    prompt_name: Mapped[str] = mapped_column(String(80))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(40))
    input_hash: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32))
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class QueryAnswerVersion(Base):
    __tablename__ = "query_answer_versions"
    __table_args__ = (UniqueConstraint("query_run_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    query_run_id: Mapped[str] = mapped_column(ForeignKey("query_runs.id"), index=True)
    model_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("query_model_runs.id"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))


class QueryDocument(Base):
    __tablename__ = "query_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(Text)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))


class QueryDocumentVersion(Base):
    __tablename__ = "query_document_versions"
    __table_args__ = (UniqueConstraint("document_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("query_documents.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24))
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))


class QueryPassage(Base):
    __tablename__ = "query_passages"
    __table_args__ = (UniqueConstraint("version_id", "local_ref"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("query_document_versions.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    local_ref: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    attribution: Mapped[str] = mapped_column(String(32))
    dependencies: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    caveats: Mapped[list[str]] = mapped_column(JSON)


class QueryFileBinding(Base):
    __tablename__ = "query_file_bindings"
    document_id: Mapped[str] = mapped_column(ForeignKey("query_documents.id"), primary_key=True)
    root_id: Mapped[str] = mapped_column(ForeignKey("authorized_roots.id"))
    relative_path: Mapped[str] = mapped_column(Text)
    version_id: Mapped[str] = mapped_column(ForeignKey("query_document_versions.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    conflict: Mapped[bool] = mapped_column(default=False)


class NoteUseGrant(Base):
    __tablename__ = "note_use_grants"
    root_id: Mapped[str] = mapped_column(ForeignKey("authorized_roots.id"), primary_key=True)
    allow_local: Mapped[bool] = mapped_column(default=True)
    allow_model: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class QueryOperation(Base):
    __tablename__ = "query_operations"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
