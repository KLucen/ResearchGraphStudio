"""Independent Q04 persisted-parse integrity regressions on synthetic source rows."""

import pytest
import test_knowledge
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.models import AttachmentRevision, Chunk
from researchgraph.query_context import build_context
from researchgraph.query_contracts import QueryRequest
from researchgraph.query_retrieval import retrieve
from researchgraph.structure_models import DocumentParse
from sqlalchemy import select
from sqlalchemy.orm import Session

seeded = test_knowledge.seeded


def source_parse(engine):
    with Session(engine) as session, session.begin():
        chunk = session.get(Chunk, "paragraph")
        version = session.get(AttachmentRevision, "version")
        structure = {
            "schema_version": "pdf-structure-1",
            "parser_version": "synthetic-query-test",
            "blocks": [
                {
                    "ref": "b0",
                    "page_index": chunk.page_index,
                    "block_index": chunk.block_index,
                    "ordinal": 0,
                    "text": chunk.text,
                    "bbox": chunk.bbox,
                    "section_ref": "s0",
                    "excluded": False,
                    "lines": [],
                }
            ],
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
            "tables": [],
            "warnings": [],
        }
        artifact = KnowledgeStore(session).apply_document_structure(
            "version", version.sha256, structure
        )
        return artifact.id


@pytest.mark.parametrize(
    "fault", ["source_hash", "schema", "block_text", "block_bbox", "missing_table_block"]
)
def test_query_revalidates_persisted_structure_before_trusting_sections_or_tables(seeded, fault):
    _, engine, _ = seeded
    parse_id = source_parse(engine)
    with Session(engine) as session, session.begin():
        artifact = session.get(DocumentParse, parse_id)
        if fault == "source_hash":
            artifact.source_sha256 = "f" * 64
        else:
            import copy

            data = copy.deepcopy(artifact.data)
            if fault == "schema":
                data["schema_version"] = "unknown-parse-contract"
            elif fault == "block_text":
                data["blocks"][0]["text"] = "This fabricated parse text has no source anchor."
            elif fault == "block_bbox":
                data["blocks"][0]["bbox"] = [90, 90, 95, 95]
            else:
                data["tables"] = [
                    {
                        "ref": "t0",
                        "section_ref": "s0",
                        "block_refs": ["b0", "missing-header"],
                        "structure_status": "resolved",
                        "headers": ["Invented header"],
                        "rows": [["3"]],
                        "cells": [],
                        "excluded": False,
                    }
                ]
            artifact.data = data
    with Session(engine) as session, session.begin():
        with pytest.raises(KnowledgeError):
            found = retrieve(session, "project", "accuracy", [])
            build_context(
                session, QueryRequest(project_id="project", question="accuracy").model_dump(), found
            )


def test_clean_registered_structure_remains_readable_and_has_no_science_writes(seeded):
    _, engine, _ = seeded
    source_parse(engine)
    with Session(engine) as session, session.begin():
        before = [c.text for c in session.scalars(select(Chunk))]
        found = retrieve(session, "project", "accuracy", [])
        context = build_context(
            session, QueryRequest(project_id="project", question="accuracy").model_dump(), found
        )
        assert context["status"] == "ready"
        assert any(r.get("section_path") == ["Results"] for r in context["references"])
        assert [c.text for c in session.scalars(select(Chunk))] == before
