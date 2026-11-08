"""Derived dependency indexes and immutable Lint reports; never scientific graph state."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from researchgraph.models import Base


class DependencyCursor(Base):
    __tablename__ = "dependency_cursors"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    event_sequence: Mapped[int] = mapped_column(Integer)
    generation: Mapped[int] = mapped_column(Integer)
    objects: Mapped[dict[str, Any]] = mapped_column(JSON)
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    updated_at: Mapped[str] = mapped_column(String(40))


class DependencyIndex(Base):
    __tablename__ = "dependency_index"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "dependent_type", "dependent_id", "source_type", "source_id", "role"
        ),
        Index("ix_dependency_reverse", "project_id", "source_type", "source_id"),
        Index("ix_dependency_forward", "project_id", "dependent_type", "dependent_id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    dependent_type: Mapped[str] = mapped_column(String(32))
    dependent_id: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(32))
    expected: Mapped[dict[str, Any]] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(24))


class LintRun(Base):
    __tablename__ = "lint_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(24))
    phase: Mapped[str] = mapped_column(String(32), default="scanning")
    timings: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    scope: Mapped[dict[str, Any]] = mapped_column(JSON)
    scope_hash: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(40))
    event_sequence: Mapped[int] = mapped_column(Integer)
    input_hash: Mapped[str] = mapped_column(String(64))
    targets: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    processed: Mapped[int] = mapped_column(Integer)
    counts: Mapped[dict[str, int]] = mapped_column(JSON)
    diff: Mapped[dict[str, int]] = mapped_column(JSON)
    previous_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class LintIssue(Base):
    __tablename__ = "lint_issues"
    __table_args__ = (
        UniqueConstraint("run_id", "fingerprint"),
        Index("ix_lint_issue_filter", "run_id", "severity", "category"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("lint_runs.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(80))
    rule_version: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(24))
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(200))
    paper_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    location: Mapped[dict[str, Any]] = mapped_column(JSON)
    message: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str] = mapped_column(Text)
    lifecycle: Mapped[str] = mapped_column(String(24))


class LintOperation(Base):
    __tablename__ = "lint_operations"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
