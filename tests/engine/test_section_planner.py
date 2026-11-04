"""Offline checks for section input fidelity and frozen recovery, not model quality."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
import test_knowledge
from researchgraph import reading_wire, unified_extraction
from researchgraph.knowledge_models import EvidenceSpan
from researchgraph.knowledge_store import KnowledgeStore, text_hash
from researchgraph.models import Chunk, Job
from researchgraph.providers import MockProvider, ProviderError
from researchgraph.section_planner import plan_reading_sections, split_context_group
from sqlalchemy import select
from sqlalchemy.orm import Session

seeded = test_knowledge.seeded


@pytest.mark.parametrize("context_window,output_limit", [(None, None), (1000000, 384000)])
def test_whole_cross_page_section_has_no_character_or_evidence_cap(context_window, output_limit):
    entries = [{"id": f"ev-{i}", "text": "a" * 300, "section": "methods"} for i in range(90)] + [
        {"id": "result", "text": "Result", "section": "results"}
    ]
    groups = plan_reading_sections(
        entries, {}, context_window=context_window, max_output_tokens=output_limit, overhead=3000
    )
    assert len(groups) == 2 and len(groups[0]) == 90
    assert sum(len(e["text"]) for e in groups[0]) == 27000
    assert [e for group in groups for e in group] == entries


def test_known_model_context_splits_only_complete_evidence_groups():
    entries = [{"id": str(i), "text": "x" * 400, "section": "methods"} for i in range(8)]
    metadata = {str(i): {"context_group": "table" if i < 2 else str(i)} for i in range(8)}
    groups = plan_reading_sections(
        entries, metadata, context_window=2800, max_output_tokens=500, overhead=300
    )
    assert len(groups) > 1
    assert [e for group in groups for e in group] == entries
    assert any({"0", "1"} <= {e["id"] for e in g} for g in groups)


def test_atomic_table_over_context_is_reported_without_truncation():
    entries = [{"id": str(i), "text": "x" * 600, "section": "results"} for i in range(2)]
    metadata = {str(i): {"context_group": "same-table"} for i in range(2)}
    original = deepcopy(entries)
    with pytest.raises(ValueError, match="完整原文段落或表格"):
        plan_reading_sections(
            entries, metadata, context_window=2000, max_output_tokens=1000, overhead=200
        )
    assert entries == original
    assert split_context_group(entries, metadata) is None


def test_noncontiguous_table_evidence_is_still_not_split():
    entries = [{"id": str(i), "text": "x", "section": "results"} for i in range(3)]
    metadata = {"0": {"context_group": "table"}, "2": {"context_group": "table"}}
    assert split_context_group(entries, metadata) is None


def test_table_context_crossing_section_labels_merges_the_section_windows():
    entries = [
        {"id": "header", "text": "Header", "section": "a"},
        {"id": "row", "text": "Value", "section": "b"},
        {"id": "paragraph", "text": "Discussion", "section": "b"},
        {"id": "end", "text": "Conclusion", "section": "c"},
    ]
    metadata = {eid: {"context_group": "table"} for eid in ["header", "row"]}
    groups = plan_reading_sections(
        entries, metadata, context_window=None, max_output_tokens=None, overhead=1000
    )
    assert [[e["id"] for e in g] for g in groups] == [["header", "row", "paragraph"], ["end"]]


def test_subsections_stay_with_their_chapter_without_an_artificial_size_limit():
    entries = [
        {"id": str(i), "text": "a" * 3500, "section": leaf}
        for i, leaf in enumerate(["methods", "method-a", "method-b", "results"])
    ]
    metadata = {str(i): {"section_group": "chapter-methods"} for i in range(3)}
    groups = plan_reading_sections(
        entries, metadata, context_window=1048576, max_output_tokens=393216, overhead=12000
    )
    assert [[e["section"] for e in g] for g in groups] == [
        ["methods", "method-a", "method-b"],
        ["results"],
    ]


def structured_fixture(engine, eid):
    """Upgrade only an isolated source's parse artifact, preserving its old anchors."""
    with Session(engine) as session, session.begin():
        first = session.get(EvidenceSpan, eid)
        chunk = session.get(Chunk, first.paragraph_id)
        blocks = [
            dict(
                ref="p0:b0",
                page_index=0,
                block_index=0,
                page_label="1",
                text=chunk.text,
                bbox=chunk.bbox,
                ordinal=0,
                section_ref="methods",
                excluded=False,
            )
        ]
        for i, (title, text) in enumerate(
            [
                ("methods", "Our method uses a measured protocol."),
                ("results", "Accuracy | Value"),
                ("results", "Experiment A | 81%"),
                ("references", "Smith et al. Synthetic references only."),
            ],
            1,
        ):
            cid = f"block-{i}"
            session.add(
                Chunk(
                    id=cid,
                    revision_id="version",
                    page_index=i,
                    page_label=str(i + 1),
                    block_index=0,
                    text=text,
                    bbox=[0.0, 0.0, 100.0, 100.0],
                )
            )
            session.flush()
            session.add(
                EvidenceSpan(
                    id=f"evidence-{i}",
                    document_version_id="version",
                    paragraph_id=cid,
                    section_id=first.section_id,
                    page_index=i,
                    start_offset=0,
                    end_offset=len(text),
                    quote=text,
                    text_sha256=text_hash(text),
                    normalization="identity-v1",
                    bbox_list=[[0.0, 0.0, 100.0, 100.0]],
                )
            )
            blocks.append(
                dict(
                    ref=f"p{i}:b0",
                    page_index=i,
                    block_index=0,
                    page_label=str(i + 1),
                    text=text,
                    bbox=[0.0, 0.0, 100.0, 100.0],
                    ordinal=i,
                    section_ref=title,
                    excluded=title == "references",
                )
            )
        structure = dict(
            schema_version="pdf-structure-1",
            parser_version="synthetic-structure-v1",
            sections=[
                dict(
                    id=ref,
                    parent_id=None,
                    title=ref.title(),
                    role=ref,
                    level=1,
                    excluded=ref == "references",
                    start_page=0,
                    end_page=4,
                    block_refs=[],
                )
                for ref in ["methods", "results", "references"]
            ],
            blocks=blocks,
            tables=[
                dict(
                    ref="table-one",
                    page_index=2,
                    section_ref="results",
                    block_refs=["p2:b0", "p3:b0"],
                    bbox=[0.0, 0.0, 100.0, 100.0],
                    rows=[["Accuracy", "Value"], ["Experiment A", "81%"]],
                    header={"names": ["Accuracy", "Value"], "external": False, "cells": []},
                    cells=[],
                    structure_status="resolved",
                    notes=[],
                )
            ],
            warnings=[],
        )
        artifact = KnowledgeStore(session).apply_document_structure("version", "a" * 64, structure)
        job = session.get(Job, "job")
        job.payload = dict(
            document_version_id="version",
            pipeline="paper-reading-v1",
            provider="mock",
            allow_network=False,
        )
        return artifact.id


def test_table_metadata_cannot_bypass_excluded_reference_evidence(seeded):
    import json

    from researchgraph.document_structure import current_structure, section_entries

    _, engine, eid = seeded
    structured_fixture(engine, eid)
    with Session(engine) as session:
        artifact = current_structure(session, "version")
        # Simulate an ambiguous grid crossing the bibliography boundary. The raw
        # artifact stays available; only complete body context may be sent to AI.
        artifact.data["tables"][0]["block_refs"].append("p4:b0")
        artifact.data["tables"][0]["rows"].append(["Excluded bibliography sentinel", ""])
        entries, metadata = section_entries(artifact, list(session.scalars(select(EvidenceSpan))))
        assert not any("references" in e["text"].lower() for e in entries)
        assert "Excluded bibliography sentinel" not in json.dumps(metadata)
        assert metadata["evidence-2"]["context_complete"] is False
        assert metadata["evidence-3"]["context_complete"] is False
        assert artifact.data["tables"][0]["rows"][-1][0] == "Excluded bibliography sentinel"


@pytest.mark.parametrize("historical_prompt", [False, True])
def test_structured_plan_excludes_references_preserves_tables_and_resumes_frozen(
    seeded, monkeypatch, historical_prompt
):
    _, engine, eid = seeded
    artifact_id = structured_fixture(engine, eid)

    class Fault(MockProvider):
        def __init__(self):
            self.calls = []
            self.fail = True
            self.capabilities = SimpleNamespace(context_window=None, max_output_tokens=None)

        async def complete(self, prompt, data, schema):
            if data.get("contract_version") == "reading-extraction-1.0":
                self.calls.append(deepcopy(data))
                if self.fail and len(self.calls) == 2:
                    raise ProviderError("timeout", "Synthetic timeout", timeout_phase="total")
            return await super().complete(prompt, data, schema)

    provider = Fault()
    monkeypatch.setattr(unified_extraction, "provider_for", lambda *args: provider)
    with monkeypatch.context() as first_run:
        if historical_prompt:
            first_run.setattr(reading_wire, "PROMPT", "P02_reading_extract_compact_v2")
        with pytest.raises(ValueError, match="超时"):
            asyncio.run(unified_extraction.run_unified_extraction(engine, "job", reading=True))
    with Session(engine) as session:
        job = session.get(Job, "job")
        frozen = deepcopy(job.payload["unified_plan"])
        assert frozen["parse_artifact_id"] == artifact_id
        assert frozen["planner"] == "section-context-v1"
        assert job.result["completed_batches"] == "1" and job.result["total_batches"] == "2"
        assert len(session.scalars(select(EvidenceSpan)).all()) == 5
    first, table_request = provider.calls
    assert len(first["allowed_evidence"]) == 2  # Same methods section, across pages.
    assert all(
        "references" not in e["text"].lower()
        for data in provider.calls
        for e in data["allowed_evidence"]
    )
    assert table_request["source_tables"][0]["rows"][1][1] == "81%"
    assert table_request["source_tables"][0]["evidence_ids"] == ["ev0001", "ev0002"]
    assert all(e["context_complete"] for e in table_request["allowed_evidence"])
    provider.fail = False
    provider.capabilities.context_window = 1024  # Never replan an existing immutable plan.
    asyncio.run(unified_extraction.run_unified_extraction(engine, "job", reading=True))
    assert len(provider.calls) == 3 and provider.calls[-1] == table_request
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert job.status == "succeeded"
        assert job.payload["unified_plan"]["config"] == frozen["config"]
        assert job.result["completed_batches"] == "2"
