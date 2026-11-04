"""Synthetic layout cautions do not infer numbers or rewrite source evidence."""

from copy import deepcopy

import pytest
import test_knowledge
from researchgraph.knowledge_models import EvidenceSpan, ModelRun
from researchgraph.knowledge_store import text_hash
from researchgraph.models import AttachmentRevision, Chunk, now
from researchgraph.reading_evidence_quality import layout_context
from researchgraph.structure_models import DocumentParse
from sqlalchemy.orm import Session

seeded = test_knowledge.seeded


def make_layout(engine, eid, *, upper_size=6.74, upper_bbox=None):
    spans = [
        {"text": "2", "size": 9.5, "bbox": [10.0, 20.0, 15.0, 30.0]},
        {
            "text": "12",
            "size": upper_size,
            "bbox": upper_bbox or [15.0, 15.0, 24.0, 22.0],
        },
    ]
    with Session(engine) as session, session.begin():
        chunk = session.get(Chunk, "paragraph")
        chunk.text = "212"
        span = session.get(EvidenceSpan, eid)
        span.quote, span.start_offset, span.end_offset = chunk.text, 0, len(chunk.text)
        span.text_sha256 = text_hash(chunk.text)
        session.add(
            DocumentParse(
                id="parse",
                document_version_id="version",
                parser_version="layout-test-1",
                source_sha256="a" * 64,
                created_at=now(),
                data={
                    "schema_version": "pdf-structure-1",
                    "blocks": [
                        {
                            "ref": "p0b0",
                            "chunk_id": chunk.id,
                            "text": chunk.text,
                            "page_index": chunk.page_index,
                            "bbox": chunk.bbox,
                            "lines": [
                                {
                                    "text": "212",
                                    "bbox": [10.0, 15.0, 24.0, 30.0],
                                    "spans": spans,
                                }
                            ],
                        }
                    ],
                },
            )
        )
    return spans


def test_flattened_superscript_returns_original_layout_without_correcting_number(seeded):
    _, engine, eid = seeded
    spans = make_layout(engine, eid)
    with Session(engine) as session:
        artifact, evidence = session.get(DocumentParse, "parse"), session.get(EvidenceSpan, eid)
        before = deepcopy(artifact.data), evidence.quote, evidence.text_sha256
        result = layout_context(session, "version", [eid, eid])
        assert result["status"] == "checked" and result["checked_evidence_count"] == 1
        assert result["unresolved_evidence"] == []
        assert result["risk_blocks"] == [
            {
                "paragraph_id": "paragraph",
                "block_ref": "p0b0",
                "evidence_ids": [eid],
                "risk": "numeric_script_layout",
                "lines": [
                    {
                        "text": "212",
                        "bbox": [10.0, 15.0, 24.0, 30.0],
                        "spans": spans,
                        "risk_pairs": [
                            {
                                "left_span": 0,
                                "right_span": 1,
                                "size_change": True,
                                "vertical_shift": True,
                            }
                        ],
                    }
                ],
            }
        ]
        assert (artifact.data, evidence.quote, evidence.text_sha256) == before
        assert session.get(Chunk, "paragraph").text == "212"
        assert session.get(ModelRun, "run").raw_output == '{"original":true}'
        assert not session.new and not session.dirty and not session.deleted


def test_same_baseline_same_size_numbers_are_checked_without_layout_payload(seeded):
    _, engine, eid = seeded
    make_layout(engine, eid, upper_size=9.5, upper_bbox=[15.0, 20.0, 24.0, 30.0])
    with Session(engine) as session:
        result = layout_context(session, "version", {eid})
        assert result["status"] == "checked"
        assert result["checked_evidence_count"] == 1
        assert result["risk_blocks"] == result["unresolved_evidence"] == []


def test_numeric_baseline_shift_is_visible_even_without_size_change(seeded):
    _, engine, eid = seeded
    make_layout(engine, eid, upper_size=9.5)
    with Session(engine) as session:
        pair = layout_context(session, "version", [eid])["risk_blocks"][0]["lines"][0][
            "risk_pairs"
        ][0]
        assert pair == {
            "left_span": 0,
            "right_span": 1,
            "size_change": False,
            "vertical_shift": True,
        }


def test_distant_same_line_number_columns_are_not_inferred_to_be_adjacent(seeded):
    _, engine, eid = seeded
    make_layout(engine, eid, upper_bbox=[100.0, 15.0, 110.0, 22.0])
    with Session(engine) as session:
        result = layout_context(session, "version", [eid])
        assert result["status"] == "checked" and result["risk_blocks"] == []


def test_no_parse_is_unknown_not_a_claim_that_plain_numbers_are_safe(seeded):
    _, engine, eid = seeded
    with Session(engine) as session:
        result = layout_context(session, "version", [eid])
        assert result["status"] == "unknown" and result["risk_blocks"] == []
        assert result["parse_artifact_id"] is None and result["checked_evidence_count"] == 0
        assert result["unresolved_evidence"] == [
            {"evidence_id": eid, "reason": "parse_unavailable"}
        ]
        assert layout_context(session, "version", [])["status"] == "not_requested"


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("version", "evidence_version_mismatch"),
        ("paragraph", "paragraph_mapping_unavailable"),
        ("duplicate_block", "paragraph_mapping_unavailable"),
        ("text", "paragraph_mapping_mismatch"),
        ("bbox", "paragraph_mapping_mismatch"),
        ("source_hash", "parse_source_mismatch"),
        ("anchor", "evidence_anchor_invalid"),
        ("line_text", "rich_layout_unavailable"),
        ("span_geometry", "rich_layout_unavailable"),
        ("no_lines", "rich_layout_unavailable"),
    ],
)
def test_layout_never_guesses_mapping_from_matching_page_or_partial_identity(seeded, fault, reason):
    _, engine, eid = seeded
    make_layout(engine, eid)
    with Session(engine) as session, session.begin():
        artifact = session.get(DocumentParse, "parse")
        data = deepcopy(artifact.data)
        block = data["blocks"][0]
        if fault == "version":
            session.add(
                AttachmentRevision(
                    id="other-version",
                    paper_id="paper",
                    sha256="b" * 64,
                    parser_version="test",
                    page_count=1,
                    warnings=[],
                    created_at=now(),
                )
            )
            session.flush()
            session.get(EvidenceSpan, eid).document_version_id = "other-version"
        elif fault == "paragraph":
            block["chunk_id"] = "different-paragraph-on-the-same-page"
        elif fault == "duplicate_block":
            data["blocks"].append(deepcopy(block))
        elif fault == "text":
            block["text"] = "2^12"
        elif fault == "bbox":
            block["bbox"] = [1.0, 2.0, 3.0, 4.0]
        elif fault == "source_hash":
            artifact.source_sha256 = "c" * 64
        elif fault == "anchor":
            session.get(EvidenceSpan, eid).end_offset = 2
        elif fault == "line_text":
            block["lines"][0]["text"] = "2^12"
        elif fault == "span_geometry":
            block["lines"][0]["spans"][1]["bbox"] = [1.0, 2.0]
        else:
            block["lines"] = []
        artifact.data = data
    with Session(engine) as session:
        result = layout_context(session, "version", [eid])
        assert result["status"] == "unknown" and result["risk_blocks"] == []
        assert result["unresolved_evidence"] == [{"evidence_id": eid, "reason": reason}]


def test_one_unavailable_evidence_does_not_hide_exactly_mapped_risk(seeded):
    _, engine, eid = seeded
    make_layout(engine, eid)
    with Session(engine) as session:
        result = layout_context(session, "version", [eid, "missing-evidence"])
        assert result["status"] == "partial" and result["checked_evidence_count"] == 1
        assert result["risk_blocks"][0]["evidence_ids"] == [eid]
        assert result["unresolved_evidence"] == [
            {"evidence_id": "missing-evidence", "reason": "evidence_unavailable"}
        ]
