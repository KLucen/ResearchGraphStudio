"""Local response authorization is independent of a frozen model-use permission."""

from typing import Any

from sqlalchemy.orm import Session

from researchgraph.knowledge_models import AuthorizedRoot, NoteSnapshot
from researchgraph.knowledge_store import KnowledgeError
from researchgraph.query_documents import note_allowed


def assert_local_sources(
    session: Session,
    project_id: str,
    retrieval: dict[str, Any],
    context: dict[str, Any] | None = None,
    *,
    include_personal: bool,
) -> None:
    """Check personal identities even when model permission still authorizes the task.

    Source hashes and scientific validity remain the caller's existing responsibility.
    This per-call set only avoids repeating local permission checks for shared roots.
    Nothing is cached between requests or written to the frozen snapshot.
    """
    checked: set[tuple[str, str]] = set()

    def source(value: dict[str, Any], kind: str | None = None, oid: str | None = None) -> None:
        kind = kind or value.get("source_kind") or value.get("type")
        oid = oid or value.get("id")
        if kind in {"note", "annotation", "external"}:
            if not include_personal or not isinstance(oid, str) or not oid:
                raise KnowledgeError("QUERY_PERSONAL_NOT_AUTHORIZED", "个人来源未获本地读取授权")
            if (kind, oid) not in checked:
                if kind == "note":
                    note = session.get(NoteSnapshot, oid)
                    root = session.get(AuthorizedRoot, note.root_id) if note else None
                    if not root or not note_allowed(session, root, project_id, "local"):
                        raise KnowledgeError("QUERY_NOTE_NOT_AUTHORIZED", "笔记本地读取授权已撤销")
                elif kind == "annotation":
                    from researchgraph.p5_personal import annotation_source

                    annotation_source(session, project_id, oid, purpose="local")
                else:
                    from researchgraph.external_documents import validate_external_version

                    validate_external_version(
                        session, project_id, oid, include_personal=True, purpose="local"
                    )
                checked.add((kind, oid))
        for root in value.get("roots", []):
            source(root)

    for hit in retrieval.get("hits", []):
        source(hit.get("data", {}), hit.get("source_kind"), hit.get("object_id"))
    for reference in (context or {}).get("references", []):
        source(reference)
