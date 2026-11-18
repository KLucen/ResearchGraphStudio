"""Bounded local upgrade for legacy PDF section trees.

Older Lite databases can contain a ``structure-v1`` parse whose chapter list
includes printed table-of-contents entries.  The current parser is additive:
it reads the already registered PDF, verifies the revision hash, and stores a
new ``structure-v2`` artifact while retaining every old Section/Span and
historical result.  This module deliberately has no model/provider calls.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError
from researchgraph.document_structure import apply_structure, current_structure
from researchgraph.models import AttachmentRevision, Paper
from researchgraph.storage import database_busy, read_session

LEGACY_CONTENT_CLEARED_WARNING = "旧本地解析内容已由用户清理，普通读取不会自动重建。"


def local_content_was_cleared(revision: AttachmentRevision) -> bool:
    return LEGACY_CONTENT_CLEARED_WARNING in (revision.warnings or [])


def mark_local_content_cleared(revision: AttachmentRevision) -> None:
    warnings = list(revision.warnings or [])
    if LEGACY_CONTENT_CLEARED_WARNING not in warnings:
        warnings.append(LEGACY_CONTENT_CLEARED_WARNING)
    revision.warnings = warnings


def clear_local_content_cleared(revision: AttachmentRevision) -> None:
    revision.warnings = [
        warning
        for warning in (revision.warnings or [])
        if warning != LEGACY_CONTENT_CLEARED_WARNING
    ]


def _is_current_parser(parser_version: str | None) -> bool:
    return isinstance(parser_version, str) and parser_version.endswith(";structure-v2")


def ensure_structure_v2(
    engine: Engine,
    paper_id: str,
    revision_id: str | None,
    data_dir: Path | None,
) -> bool:
    """Upgrade one legacy revision when its registered PDF is available.

    The expensive PDF read happens in a read transaction.  The write
    transaction only rechecks the selected revision and publishes the
    validated artifact, so concurrent readers either observe the old tree or
    the complete new tree.  A busy writer or unavailable PDF leaves the old
    tree readable and returns ``False``.
    """

    with read_session(engine) as session:
        paper = session.get(Paper, paper_id)
        if paper is None:
            raise KnowledgeError("PAPER_NOT_FOUND", "论文不存在")
        revision = (
            session.get(AttachmentRevision, revision_id)
            if revision_id
            else session.scalar(
                select(AttachmentRevision)
                .where(AttachmentRevision.paper_id == paper_id)
                .order_by(AttachmentRevision.created_at.desc(), AttachmentRevision.id)
            )
        )
        if revision is None or revision.paper_id != paper_id:
            raise KnowledgeError("REVISION_NOT_FOUND", "文献版本不存在或不属于当前论文")
        if local_content_was_cleared(revision):
            return False
        artifact = current_structure(session, revision.id)
        if artifact is None or _is_current_parser(artifact.parser_version):
            return False
        selected_id, source_hash = revision.id, revision.sha256
        # Import lazily to avoid a module cycle: reading_projection itself
        # imports document_structure.
        from researchgraph.reading_projection import _scan_pdf

        fresh, _warnings = _scan_pdf(session, revision, data_dir)
        if fresh is None or not _is_current_parser(str(fresh.get("parser_version"))):
            return False

    try:
        # An upgrade is a best-effort derived update. Do not make the normal
        # outline request wait behind another local writer; it can return the
        # still-valid legacy tree and retry on the next read.
        with (
            Session(engine.execution_options(sqlite_busy_timeout_ms=0)) as session,
            session.begin(),
        ):
            revision = session.get(AttachmentRevision, selected_id)
            if revision is None or revision.paper_id != paper_id or revision.sha256 != source_hash:
                return False
            artifact = current_structure(session, selected_id)
            if artifact is not None and _is_current_parser(artifact.parser_version):
                return False
            published = apply_structure(session, selected_id, source_hash, fresh)
            from researchgraph.local_index import index_document

            index_document(session, selected_id)
            return _is_current_parser(published.parser_version)
    except OperationalError as error:
        if database_busy(error):
            return False
        raise
