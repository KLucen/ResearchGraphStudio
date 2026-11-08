"""Fixed synthetic scale checks for batched indexes and complete indexed closure."""

from contextlib import contextmanager

import pytest
from researchgraph.knowledge_models import GraphRevision
from researchgraph.knowledge_store import KnowledgeStore, digest, text_hash
from researchgraph.lint_models import DependencyCursor, DependencyIndex
from researchgraph.lint_service import dependencies, rebuild_dependencies
from researchgraph.models import Chunk
from sqlalchemy import event, insert, select
from sqlalchemy.orm import Session
from test_knowledge import seeded as seeded
from test_query_documents import add_note
from test_query_documents import engine as engine


@contextmanager
def statements(engine):
    observed = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        observed.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", observe)
    try:
        yield observed
    finally:
        event.remove(engine, "before_cursor_execute", observe)


def edge(identity, dependent, source, project="p"):
    return {
        "id": identity,
        "project_id": project,
        "dependent_type": dependent[0],
        "dependent_id": dependent[1],
        "source_type": source[0],
        "source_id": source[1],
        "role": "synthetic",
        "category": "semantic",
        "expected": {},
        "state": "valid",
    }


def test_dependency_rebuild_batches_sources_and_preserves_edge_identity(engine):
    with Session(engine) as session, session.begin():
        session.execute(
            insert(Chunk),
            [
                {
                    "id": f"bulk-{i:04}",
                    "revision_id": "v",
                    "page_index": 0,
                    "page_label": "1",
                    "block_index": i + 1,
                    "text": f"Synthetic paragraph {i}.",
                    "bbox": [0, 0, 100, 50],
                }
                for i in range(900)
            ],
        )
    with statements(engine) as observed:
        with Session(engine) as session, session.begin():
            result = rebuild_dependencies(KnowledgeStore(session), "p")
    assert result["edge_count"] == 902
    # The old loop needed more than 900 SELECTs just for these source rows.
    selects = [sql for sql, _ in observed if sql.lstrip().upper().startswith("SELECT")]
    assert len(selects) < 50, len(selects)
    with Session(engine) as session:
        rows = list(session.scalars(select(DependencyIndex)))
        chunk_edge = next(row for row in rows if row.dependent_id == "bulk-0899")
        assert chunk_edge.id == digest(
            ["p", "chunk", "bulk-0899", "version", "v", "document_source"]
        )
        assert chunk_edge.state == "valid" and chunk_edge.category == "source"
        span = next(row for row in rows if row.dependent_type == "evidence")
        assert span.expected == {"sha256": text_hash("A method at 20 K.")}
        assert session.get(GraphRevision, "p") is None
        generation = session.get(DependencyCursor, "p").generation
    with Session(engine) as session, session.begin():
        unchanged = rebuild_dependencies(KnowledgeStore(session), "p", skip_unchanged=True)
    assert unchanged["generation"] == generation and unchanged["changes"] == []


def test_batched_citation_index_retains_root_member_selection_and_invalid_state(seeded):
    import asyncio

    from researchgraph.knowledge_models import KnowledgeNode, NodeEvidence
    from researchgraph.providers import MockProvider
    from researchgraph.reading_models import ReadingHead, ReadingUnit
    from researchgraph.reading_pipeline import finish_reading
    from sqlalchemy import delete
    from test_query_graph import production
    from test_reading_selection import setup_job

    _, engine, eid = seeded
    ids = production(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        cited = [session.get(KnowledgeNode, ids[ref]) for ref in ("c", "m")]
        saved = (
            KnowledgeStore(session)
            .query()
            .save_document(
                {
                    "project_id": "project",
                    "kind": "wiki",
                    "title": "Citations retain every support context",
                    "passages": [
                        {
                            "local_ref": "context",
                            "text": "A synthetic interpretation.",
                            "attribution": "model_synthesis",
                            "dependencies": [
                                {"type": "node", "id": node.id, "revision": node.revision}
                                for node in cited
                            ],
                        }
                    ],
                },
                "save-citation-context",
            )
        )
        rebuilt = rebuild_dependencies(KnowledgeStore(session), "project")
        expected_units = set(session.scalars(select(ReadingUnit.id)))
        selection_id = session.get(ReadingHead, "paper").selection_id
        edges = list(
            session.scalars(
                select(DependencyIndex).where(
                    DependencyIndex.dependent_type == "passage",
                    DependencyIndex.dependent_id == saved["passage_ids"][0],
                )
            )
        )
        assert {row.source_id for row in edges if row.role == "support_context"} == expected_units
        assert {row.source_id for row in edges if row.role == "organization"} == {selection_id}
        assert all(row.state == "valid" for row in edges)
    with Session(engine) as session, session.begin():
        session.execute(delete(NodeEvidence).where(NodeEvidence.node_id == ids["m"]))
        invalid = rebuild_dependencies(KnowledgeStore(session), "project")
        method_edge = session.scalar(
            select(DependencyIndex).where(
                DependencyIndex.dependent_type == "passage",
                DependencyIndex.dependent_id == saved["passage_ids"][0],
                DependencyIndex.source_type == "node",
                DependencyIndex.source_id == ids["m"],
            )
        )
        assert method_edge.state == "invalid"
        assert invalid["generation"] == rebuilt["generation"] + 1


@pytest.mark.parametrize(
    "direction,root", [("dependents", "node-0"), ("dependencies", "node-1200")]
)
def test_indexed_closure_reaches_deep_cycles_and_pages_without_loading_unrelated_rows(
    engine, direction, root
):
    connected = [
        edge(f"connected-{i:04}", ("node", f"node-{i + 1}"), ("node", f"node-{i}"))
        for i in range(1200)
    ]
    connected.append(edge("cycle-back", ("node", "node-0"), ("node", "node-1200")))
    connected.append(edge("second-path", ("node", "node-1200"), ("node", "node-0")))
    unrelated = [
        edge(f"unrelated-{i:04}", ("node", f"other-{i + 1}"), ("node", f"other-{i}"))
        for i in range(2000)
    ]
    unrelated.append(edge("other-project", ("node", "node-1201"), ("node", "node-1200"), "other"))
    with Session(engine) as session, session.begin():
        session.execute(insert(DependencyIndex), connected + unrelated)
    with Session(engine) as session, statements(engine) as observed:
        result = dependencies(
            session,
            "p",
            object_type="node",
            object_id=root,
            direction=direction,
            page=40,
            page_size=17,
        )
        assert not any(isinstance(item, DependencyIndex) for item in session.identity_map.values())
    expected = sorted(row["id"] for row in connected)
    assert result["total"] == len(connected)
    assert [row["id"] for row in result["items"]] == expected[39 * 17 : 40 * 17]
    recursive = [(sql, args) for sql, args in observed if sql.startswith("WITH RECURSIVE")]
    assert len(recursive) == 1
    with engine.connect() as connection:
        plan = connection.exec_driver_sql(
            "EXPLAIN QUERY PLAN " + recursive[0][0], recursive[0][1]
        ).all()
    detail = "\n".join(row[-1] for row in plan)
    # Both the recursive step and returned edges must use their project/direction key.
    expected_index = (
        "ix_dependency_reverse" if direction == "dependents" else "ix_dependency_forward"
    )
    assert detail.count(expected_index) == 2, detail
    assert detail.count("project_id=? AND") == 2, detail
    selected_queries = [
        sql for sql, _ in observed if sql.lstrip().upper().startswith(("SELECT", "WITH RECURSIVE"))
    ]
    assert len(selected_queries) == 4


@pytest.mark.parametrize("direction,root", [("dependents", "first"), ("dependencies", "last")])
def test_revoked_private_intermediate_is_hidden_without_truncating_public_closure(
    engine, tmp_path, direction, root
):
    with Session(engine) as session, session.begin():
        authorized, note, _ = add_note(session, tmp_path)
        session.execute(
            insert(DependencyIndex),
            [
                edge("private-in", ("note", note.id), ("node", "first")),
                edge("private-out", ("node", "middle"), ("note", note.id)),
                edge("public-tail", ("node", "last"), ("node", "middle")),
            ],
        )
        authorized.active = False
    with Session(engine) as session:
        result = dependencies(session, "p", object_type="node", object_id=root, direction=direction)
    assert result["total"] == 1
    assert [row["id"] for row in result["items"]] == ["public-tail"]
    assert "note" not in str(result)
