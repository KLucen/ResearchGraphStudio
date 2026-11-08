"""Transactional, batched derived indexes and indexed dependency closure queries.

The catalog and document dependency validators remain the authority for current
sources and permissions. All preparation here belongs to this one transaction;
no source or authorization result survives into another call.
"""

from collections.abc import Iterable, Iterator
from itertools import islice
from typing import Any

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import (
    Annotation,
    EvidenceSpan,
    KnowledgeDependency,
    KnowledgeNode,
    NodeEvidence,
)
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.lint_models import DependencyCursor, DependencyIndex
from researchgraph.models import Chunk, now
from researchgraph.query_documents import validate_dependencies
from researchgraph.query_models import QueryDocument, QueryDocumentVersion, QueryPassage
from researchgraph.reading_models import ReadingHead, ReadingMember, ReadingSelection, ReadingUnit
from researchgraph.reasoning_models import RelationAssertion
from researchgraph.wiki_models import WikiPage

# Stay below the variable limit on older supported SQLite distributions. Inserts
# use executemany, so this is also a bound on temporary Python insertion lists.
_BATCH_SIZE = 400


def _batches(values: Iterable[Any]) -> Iterator[list[Any]]:
    remaining = iter(values)
    while batch := list(islice(remaining, _BATCH_SIZE)):
        yield batch


def _rows(
    session: Session, columns: tuple[Any, ...], key: Any, ids: Iterable[str]
) -> Iterator[Any]:
    for batch in _batches(ids):
        yield from session.execute(select(*columns).where(key.in_(batch)))


def rebuild_dependencies(
    store: KnowledgeStore,
    project_id: str,
    *,
    include_personal: bool | None = None,
    skip_unchanged: bool = False,
) -> dict[str, Any]:
    # Deferred import keeps the public service entry point and catalog compatible
    # with scan preparation while avoiding a circular module dependency.
    from researchgraph.lint_service import _catalog, _sequence

    session = store.session
    before = session.get(DependencyCursor, project_id)
    previous = dict(before.objects) if before else {}
    if include_personal is None:
        include_personal = previous.get("settings:include_personal") == "true"
    targets = _catalog(session, project_id, {"include_personal": include_personal})
    objects = {f"{target['type']}:{target['id']}": target["fingerprint"] for target in targets}
    objects["settings:include_personal"] = "true" if include_personal else "false"
    if skip_unchanged and before and objects == previous:
        before.event_sequence = _sequence(session, project_id)
        return {
            "project_id": project_id,
            "event_sequence": before.event_sequence,
            "generation": before.generation,
            "edge_count": int(
                session.scalar(
                    select(func.count())
                    .select_from(DependencyIndex)
                    .where(DependencyIndex.project_id == project_id)
                )
                or 0
            ),
            "change_count": 0,
            "changes": [],
        }

    grouped: dict[str, set[str]] = {}
    for target in targets:
        grouped.setdefault(target["type"], set()).add(target["id"])
    edges: dict[str, dict[str, Any]] = {}

    def add(
        dependent_type: str,
        dependent_id: str,
        source_type: str,
        source_id: str,
        role: str,
        category: str = "semantic",
        expected: dict[str, Any] | None = None,
        state: str | None = None,
    ) -> None:
        identity = digest([project_id, dependent_type, dependent_id, source_type, source_id, role])
        edges[identity] = {
            "id": identity,
            "project_id": project_id,
            "dependent_type": dependent_type,
            "dependent_id": dependent_id,
            "source_type": source_type,
            "source_id": source_id,
            "role": role,
            "category": category,
            "expected": expected or {},
            "state": state
            if state is not None
            else "valid"
            if f"{source_type}:{source_id}" in objects
            else "invalid",
        }

    def rows(kind: str, columns: tuple[Any, ...], key: Any) -> Iterator[Any]:
        return _rows(session, columns, key, sorted(grouped.get(kind, ())))

    for oid, revision_id in rows("chunk", (Chunk.id, Chunk.revision_id), Chunk.id):
        add("chunk", oid, "version", revision_id, "document_source", "source")
    for oid, chunk_id, sha256 in rows(
        "evidence",
        (EvidenceSpan.id, EvidenceSpan.paragraph_id, EvidenceSpan.text_sha256),
        EvidenceSpan.id,
    ):
        add("evidence", oid, "chunk", chunk_id, "anchor", "evidence", {"sha256": sha256})
    for oid, evidence_id, role in rows(
        "node",
        (NodeEvidence.node_id, NodeEvidence.evidence_id, NodeEvidence.role),
        NodeEvidence.node_id,
    ):
        add("node", oid, "evidence", evidence_id, role, "evidence")
    for oid, dependee_id, role in rows(
        "node",
        (KnowledgeDependency.node_id, KnowledgeDependency.dependee_id, KnowledgeDependency.role),
        KnowledgeDependency.node_id,
    ):
        add("node", oid, "node", dependee_id, role)
    for kind, model in (("assertion", SourceAssertion), ("relation", RelationAssertion)):
        for oid, source_id, target_id, evidence_ids in rows(
            kind, (model.id, model.source_id, model.target_id, model.evidence_ids), model.id
        ):
            add(kind, oid, "node", source_id, "source_endpoint")
            add(kind, oid, "node", target_id, "target_endpoint")
            for evidence_id in evidence_ids:
                add(kind, oid, "evidence", evidence_id, "relation_evidence", "evidence")
    for oid, root_claim_id in rows(
        "unit", (ReadingUnit.id, ReadingUnit.root_claim_id), ReadingUnit.id
    ):
        add("unit", oid, "node", root_claim_id, "root_claim")
    for oid, node_id, associations in rows(
        "unit",
        (ReadingMember.unit_id, ReadingMember.node_id, ReadingMember.association_ids),
        ReadingMember.unit_id,
    ):
        add("unit", oid, "node", node_id, "member")
        for path in associations:
            if not path.startswith("dependency:"):
                add("unit", oid, "assertion", path, "support_path")
    for oid, data in rows(
        "selection", (ReadingSelection.id, ReadingSelection.data), ReadingSelection.id
    ):
        for unit in data.get("units", []):
            if isinstance(unit, dict) and isinstance(unit.get("id"), str):
                add("selection", oid, "unit", unit["id"], "organization", "organization")

    external_documents = []
    for oid, current_version_id, kind in rows(
        "document",
        (QueryDocument.id, QueryDocument.current_version_id, QueryDocument.kind),
        QueryDocument.id,
    ):
        if current_version_id:
            add(
                "document",
                oid,
                "document_version",
                current_version_id,
                "current_version",
                "organization",
            )
        if kind == "external":
            external_documents.append(oid)
    for oid, head_version_id in rows(
        "document", (WikiPage.document_id, WikiPage.head_version_id), WikiPage.document_id
    ):
        add("document", oid, "document_version", head_version_id, "draft_head", "organization")
    for oid, version_id in _rows(
        session,
        (QueryDocumentVersion.document_id, QueryDocumentVersion.id),
        QueryDocumentVersion.document_id,
        external_documents,
    ):
        if f"external:{version_id}" in objects:
            add("document", oid, "external", version_id, "external_source")
    for oid, version_id, evidence_id in rows(
        "annotation",
        (Annotation.id, Annotation.document_version_id, Annotation.evidence_id),
        Annotation.id,
    ):
        add("annotation", oid, "version", version_id, "annotation_attachment")
        if evidence_id:
            add("annotation", oid, "evidence", evidence_id, "highlight_anchor")
    for oid, passage_id in rows(
        "document_version", (QueryPassage.version_id, QueryPassage.id), QueryPassage.version_id
    ):
        add("document_version", oid, "passage", passage_id, "paragraph")

    # Keep each citation's authoritative validation, including exact text hashes,
    # full support and current permissions. Only support-context lookup is batched.
    citations = list(rows("passage", (QueryPassage.id, QueryPassage.dependencies), QueryPassage.id))
    cited_ids = {
        dep["id"]
        for _, dependencies in citations
        for dep in dependencies
        if isinstance(dep, dict) and dep.get("type") == "node" and isinstance(dep.get("id"), str)
    }
    cited_nodes = {
        oid: (version_id, paper_id)
        for oid, version_id, paper_id in _rows(
            session,
            (KnowledgeNode.id, KnowledgeNode.document_version_id, KnowledgeNode.paper_id),
            KnowledgeNode.id,
            sorted(cited_ids),
        )
    }
    cited_units: dict[str, set[str]] = {}
    for unit_id, node_id, version_id in _rows(
        session,
        (ReadingUnit.id, ReadingUnit.root_claim_id, ReadingUnit.document_version_id),
        ReadingUnit.root_claim_id,
        sorted(cited_nodes),
    ):
        if cited_nodes[node_id][0] == version_id:
            cited_units.setdefault(node_id, set()).add(unit_id)
    for node_id, unit_id in _rows(
        session,
        (ReadingMember.node_id, ReadingMember.unit_id),
        ReadingMember.node_id,
        sorted(cited_nodes),
    ):
        cited_units.setdefault(node_id, set()).add(unit_id)
    selections: dict[str, str] = dict(
        _rows(
            session,
            (ReadingHead.paper_id, ReadingHead.selection_id),
            ReadingHead.paper_id,
            sorted({paper_id for _, paper_id in cited_nodes.values()}),
        )
    )
    for oid, dependencies in citations:
        for dep in dependencies:
            if (
                not isinstance(dep, dict)
                or not isinstance(dep.get("id"), str)
                or dep.get("type")
                not in {"chunk", "evidence", "node", "note", "annotation", "external", "passage"}
            ):
                continue
            state = validate_dependencies(session, project_id, [dep], True)["content_state"]
            add("passage", oid, dep["type"], dep["id"], "citation", "evidence", dep, state)
            if dep["type"] == "node" and dep["id"] in cited_nodes:
                for unit_id in sorted(cited_units.get(dep["id"], ())):
                    add("passage", oid, "unit", unit_id, "support_context")
                selection_id = selections.get(cited_nodes[dep["id"]][1])
                if selection_id:
                    add("passage", oid, "selection", selection_id, "organization", "organization")

    session.execute(delete(DependencyIndex).where(DependencyIndex.project_id == project_id))
    for batch in _batches(edges.values()):
        session.execute(insert(DependencyIndex), batch)
    sequence, generation = _sequence(session, project_id), (before.generation + 1 if before else 1)
    categories = {
        "version": "source",
        "chunk": "evidence",
        "evidence": "evidence",
        "node": "semantic",
        "assertion": "semantic",
        "relation": "semantic",
        "unit": "semantic",
        "selection": "organization",
        "document": "organization",
        "document_version": "semantic",
        "passage": "semantic",
        "note": "authorization",
        "annotation": "authorization",
        "external": "authorization",
    }
    changes = [
        {
            "object_type": key.split(":", 1)[0],
            "object_id": key.split(":", 1)[1],
            "category": categories.get(key.split(":", 1)[0], "semantic"),
            "change": "removed"
            if key not in objects
            else "added"
            if key not in previous
            else "changed",
        }
        for key in sorted(set(objects) | set(previous))
        if not key.startswith("settings:") and objects.get(key) != previous.get(key)
    ]
    if before:
        before.event_sequence, before.generation, before.objects = sequence, generation, objects
        before.changes, before.updated_at = changes, now()
    else:
        session.add(
            DependencyCursor(
                project_id=project_id,
                event_sequence=sequence,
                generation=generation,
                objects=objects,
                changes=changes,
                updated_at=now(),
            )
        )
    session.flush()
    store.audit_event(
        project_id,
        "DEPENDENCY_INDEX_REBUILT",
        {
            "generation": generation,
            "event_sequence": sequence,
            "edge_count": len(edges),
            "change_count": len(changes),
        },
        actor="system",
        trigger="lint_index",
    )
    return {
        "project_id": project_id,
        "event_sequence": sequence,
        "generation": generation,
        "edge_count": len(edges),
        "change_count": len(changes),
        "changes": changes,
    }


def dependencies(
    session: Session,
    project_id: str,
    *,
    object_type: str | None = None,
    object_id: str | None = None,
    direction: str = "dependents",
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    from researchgraph.lint_service import _personal_visible, _project, _sequence

    _project(session, project_id)
    if bool(object_type) != bool(object_id) or direction not in {"dependents", "dependencies"}:
        raise KnowledgeError("LINT_SCOPE_INVALID", "依赖查询需同时指定对象类型与 ID")
    index = DependencyIndex.__table__
    keys = (
        "id",
        "dependent_type",
        "dependent_id",
        "source_type",
        "source_id",
        "role",
        "category",
        "state",
    )
    statement: Any = (
        select(*(index.c[key] for key in keys))
        .where(index.c.project_id == project_id)
        .order_by(index.c.id)
    )
    if object_type and object_id:
        reverse = direction == "dependents"
        from_kind, to_kind = ("source", "dependent") if reverse else ("dependent", "source")
        index_name = "ix_dependency_reverse" if reverse else "ix_dependency_forward"
        # CROSS JOIN fixes SQLite's loop order: each reached object probes its
        # complete indexed key. An ordinary JOIN can be reordered into a scan of
        # every project edge for every recursive step on unanalysed user databases.
        # Identifiers below are exclusively these program-owned constants; user
        # values remain SQL bind parameters.
        statement = text(
            f"""WITH RECURSIVE reachable_dependencies(kind, oid) AS (
                SELECT :root_kind, :root_id
                UNION
                SELECT d.{to_kind}_type, d.{to_kind}_id
                FROM reachable_dependencies AS r
                CROSS JOIN dependency_index AS d INDEXED BY {index_name}
                WHERE d.project_id = :project_id
                  AND d.{from_kind}_type = r.kind AND d.{from_kind}_id = r.oid
            )
            SELECT {", ".join("d." + key for key in keys)}
            FROM reachable_dependencies AS r
            CROSS JOIN dependency_index AS d INDEXED BY {index_name}
            WHERE d.project_id = :project_id
              AND d.{from_kind}_type = r.kind AND d.{from_kind}_id = r.oid
            ORDER BY d.id"""
        ).bindparams(project_id=project_id, root_kind=object_type, root_id=object_id)
    statement = statement.execution_options(yield_per=_BATCH_SIZE)
    visibility: dict[tuple[str, str], bool] = {}
    personal_kinds = {"note", "external", "annotation", "document", "document_version", "passage"}

    def visible(kind: str, oid: str) -> bool:
        if kind not in personal_kinds:
            return True
        key = (kind, oid)
        if key not in visibility:
            visibility[key] = _personal_visible(session, project_id, kind, oid)
        return visibility[key]

    items, total = [], 0
    first, last = (page - 1) * page_size, page * page_size
    # Visibility is deliberately applied after full closure. A hidden intermediate
    # vertex must not truncate a later public dependency path or leak its identity.
    for row in session.execute(statement).mappings():
        if visible(row["source_type"], row["source_id"]) and visible(
            row["dependent_type"], row["dependent_id"]
        ):
            if first <= total < last:
                items.append(dict(row))
            total += 1
    cursor = session.get(DependencyCursor, project_id)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "generation": cursor.generation if cursor else 0,
        "event_sequence": cursor.event_sequence if cursor else 0,
        "pending_events": _sequence(session, project_id) > (cursor.event_sequence if cursor else 0),
    }
