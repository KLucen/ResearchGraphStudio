"""Q04 complete table groups and Wiki-root graph consumption, using synthetic rows."""

import copy

import pytest
import test_knowledge
from researchgraph.knowledge_models import EvidenceSpan
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, text_hash
from researchgraph.models import AttachmentRevision, Chunk
from researchgraph.query_context import build_context, validate_context
from researchgraph.query_contracts import QueryRequest
from researchgraph.query_retrieval import retrieve
from researchgraph.structure_models import DocumentParse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_query_graph import production

seeded = test_knowledge.seeded


def table_source(engine, eid):
    """The row has an old span; the header deliberately has no EvidenceSpan."""
    with Session(engine) as session, session.begin():
        row = session.get(Chunk, "paragraph")
        row.text, row.bbox = "rowmarker | 7.5", [0.0, 20.0, 100.0, 40.0]
        span = session.get(EvidenceSpan, eid)
        span.quote, span.end_offset = row.text, len(row.text)
        span.text_sha256, span.bbox_list = text_hash(row.text), [row.bbox]
        session.add(
            Chunk(
                id="header",
                revision_id="version",
                page_index=0,
                page_label="1",
                block_index=1,
                text="Method | Pressure (kPa)",
                bbox=[0.0, 0.0, 100.0, 20.0],
            )
        )
        session.flush()
        header = session.get(Chunk, "header")
        table = {
            "ref": "table0",
            "page_index": 0,
            "bbox": [0.0, 0.0, 100.0, 40.0],
            "section_ref": "s0",
            "block_refs": ["header-block", "row-block"],
            "excluded": False,
            "rows": [["Method", "Pressure (kPa)"], ["rowmarker", "7.5"]],
            "header": {
                "names": ["Method", "Pressure (kPa)"],
                "external": False,
                "cells": [[0.0, 0.0, 50.0, 20.0], [50.0, 0.0, 100.0, 20.0]],
            },
            "cells": [
                {
                    "row": r,
                    "column": c,
                    "row_span": 1,
                    "col_span": 1,
                    "text": value,
                    "bbox": [c * 50.0, r * 20.0, (c + 1) * 50.0, (r + 1) * 20.0],
                    "block_refs": ["header-block" if r == 0 else "row-block"],
                }
                for r, values in enumerate([["Method", "Pressure (kPa)"], ["rowmarker", "7.5"]])
                for c, value in enumerate(values)
            ],
            "structure_status": "resolved",
            "notes": ["Synthetic table, no scientific claim."],
        }
        structure = {
            "schema_version": "pdf-structure-1",
            "parser_version": "synthetic-table-query",
            "sections": [
                {
                    "id": "s0",
                    "parent_id": None,
                    "level": 1,
                    "title": "Results",
                    "role": "body",
                    "excluded": False,
                }
            ],
            "blocks": [
                {
                    "ref": ref,
                    "page_index": 0,
                    "block_index": chunk.block_index,
                    "ordinal": index,
                    "text": chunk.text,
                    "bbox": chunk.bbox,
                    "section_ref": "s0",
                    "excluded": False,
                    "lines": [],
                    "kind": "table",
                }
                for index, (ref, chunk) in enumerate([("header-block", header), ("row-block", row)])
            ],
            "tables": [table],
            "warnings": [],
        }
        version = session.get(AttachmentRevision, "version")
        artifact = KnowledgeStore(session).apply_document_structure(
            "version", version.sha256, structure
        )
        return artifact.id


def row_context(session):
    request = QueryRequest(project_id="project", question="rowmarker", source_kinds=["chunk"])
    found = retrieve(session, "project", request.question, [], source_kinds=request.source_kinds)
    assert [h["object_id"] for h in found["hits"]] == ["paragraph"]
    return build_context(session, request.model_dump(), found), found


def test_row_hit_keeps_header_cells_units_and_does_not_create_evidence(seeded):
    _, engine, eid = seeded
    parse_id = table_source(engine, eid)
    with Session(engine) as session, session.begin():
        original = copy.deepcopy(session.get(DocumentParse, parse_id).data)
        span_count = session.scalar(select(func.count()).select_from(EvidenceSpan))
        context, found = row_context(session)
        assert context["status"] == "ready"
        assert {r["id"] for r in context["references"] if r["type"] == "chunk"} == {
            "paragraph",
            "header",
        }
        assert context["tables"][0]["data"] == original["tables"][0]
        assert context["tables"][0]["data"]["header"]["names"] == ["Method", "Pressure (kPa)"]
        assert validate_context(session, context, found)["valid"] is True
        assert session.scalar(select(func.count()).select_from(EvidenceSpan)) == span_count
        assert session.get(DocumentParse, parse_id).data == original


@pytest.mark.parametrize("fault", ["partial", "missing_header"])
def test_incomplete_table_is_preserved_but_context_is_insufficient(seeded, fault):
    _, engine, eid = seeded
    parse_id = table_source(engine, eid)
    with Session(engine) as session, session.begin():
        artifact = session.get(DocumentParse, parse_id)
        data = copy.deepcopy(artifact.data)
        table = data["tables"][0]
        if fault == "partial":
            table["structure_status"] = "partial"
        else:
            table["header"]["names"] = []
        artifact.data = data
    with Session(engine) as session, session.begin():
        context, _ = row_context(session)
        assert context["status"] == "insufficient" and context["coverage_gaps"]
        assert context["tables"][0]["data"] == data["tables"][0]
        assert {r["id"] for r in context["references"] if r["type"] == "chunk"} == {
            "header",
            "paragraph",
        }


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_cell_block",
        "row",
        "column",
        "negative_row",
        "negative_column",
        "row_span",
        "col_span",
    ],
)
def test_invalid_cell_sources_or_grid_indexes_are_never_ready(seeded, fault):
    _, engine, eid = seeded
    parse_id = table_source(engine, eid)
    with Session(engine) as session, session.begin():
        artifact = session.get(DocumentParse, parse_id)
        data = copy.deepcopy(artifact.data)
        cell = data["tables"][0]["cells"][-1]
        if fault == "unknown_cell_block":
            cell["block_refs"] = ["invented-block"]
        elif fault in {"negative_row", "negative_column"}:
            cell[fault.removeprefix("negative_")] = -1
        else:
            cell[fault] = 2
        artifact.data = data
    with Session(engine) as session, session.begin():
        try:
            context, _ = row_context(session)
        except KnowledgeError as error:
            assert error.code in {"QUERY_PARSE_INVALID", "QUERY_SOURCE_INVALID", "INVALID_TABLE"}
        else:
            assert context["status"] == "insufficient" and context["coverage_gaps"]


def test_wiki_only_hit_walks_to_root_claim_support_and_conditions(seeded):
    _, engine, eid = seeded
    ids = production(engine, eid)
    with Session(engine) as session, session.begin():
        saved = (
            KnowledgeStore(session)
            .query()
            .save_document(
                {
                    "project_id": "project",
                    "kind": "wiki",
                    "title": "Synthetic saved reading",
                    "passages": [
                        {
                            "local_ref": "p",
                            "text": "wikionlymarker",
                            "attribution": "model_synthesis",
                            "dependencies": [{"type": "node", "id": ids["c"], "revision": 1}],
                        }
                    ],
                },
                "synthetic-wiki-root-path",
            )
        )
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "wikionlymarker", [], source_kinds=["wiki"])
        assert [(h["source_kind"], h["object_id"]) for h in found["hits"]] == [
            ("wiki", saved["passage_ids"][0])
        ]
        assert {p["root_id"] for p in found["graph"]["paths"]} == {ids["c"]}
        assert {n["id"] for n in found["graph"]["nodes"]} == set(ids.values())
        assert found["graph"]["conditions"][0]["node_id"] == ids["d"]
        assert found["independent_sources"] == ["paper:version"]
        request = QueryRequest(
            project_id="project", question="wikionlymarker", source_kinds=["wiki"]
        )
        context = build_context(session, request.model_dump(), found)
        assert context["status"] == "ready"
        assert any(r["type"] == "node" and r["id"] == ids["d"] for r in context["references"])
