import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "schemas"))
from contracts import (  # noqa: E402
    KnowledgeExtractionBatch, GraphProjection, ComparabilityReport,
    RelationInference, EvidenceSpan, JobBatchRecord,
    require_allowed_evidence, verify_span_exact,
)


def load(name):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_unified_extraction_fixture():
    batch = KnowledgeExtractionBatch.model_validate(load("extraction_batch.json"))
    assert {i.kind.value for i in batch.items} == {"Concept", "Method", "Claim", "ResearchQuestion"}
    require_allowed_evidence(batch, {"ev-a-1"})


def test_invalid_evidence_id_blocked():
    batch = KnowledgeExtractionBatch.model_validate(load("extraction_batch.json"))
    with pytest.raises(ValueError, match="unknown/out-of-scope"):
        require_allowed_evidence(batch, set())


def test_graph_projection_fixture_and_only_five_types():
    graph = GraphProjection.model_validate(load("graph_projection.json"))
    assert len(graph.edges) == 2
    assert {n.kind.value for n in graph.nodes} <= {"Paper", "Concept", "Method", "Claim", "ResearchQuestion"}


def test_relation_no_decision_never_an_edge():
    relation = RelationInference.model_validate(load("relation_no_decision.json"))
    assert relation.relation_type is None
    data = load("relation_no_decision.json")
    data["relation_type"] = "CONTRADICTS"
    with pytest.raises(ValidationError):
        RelationInference.model_validate(data)


def test_comparability_has_unknown_not_different():
    report = ComparabilityReport.model_validate(load("comparability_report.json"))
    assert any(d.comparison == "unknown" for d in report.dimensions)


def test_evidence_offset_exact():
    span = EvidenceSpan.model_validate(load("evidence_span.json"))
    assert verify_span_exact(span, "Shared memory helps researchers")
    assert not verify_span_exact(span, "Shared memory harms researchers")


def test_unknown_conditions_cannot_assert_value():
    data = load("extraction_batch.json")
    data["items"][2]["claim_detail"]["conditions"][2]["value_en"] = "invented dataset"
    with pytest.raises(ValidationError):
        KnowledgeExtractionBatch.model_validate(data)


def test_automated_nodes_do_not_require_accepted_review():
    graph = GraphProjection.model_validate(load("graph_projection.json"))
    assert all(n.review_status.value == "unreviewed" for n in graph.nodes)


def test_unreviewed_inference_requires_dashed():
    data = load("graph_projection.json")
    data["edges"][1]["epistemic_status"] = "model_inferred"
    with pytest.raises(ValidationError):
        GraphProjection.model_validate(data)


def test_batch_record_not_retried_after_committed_invariant_example():
    record = JobBatchRecord(
        job_id="job", batch_id="batch", chunk_id="chunk", input_hash="hash",
        document_version_id="dv", prompt_version="p02@3", model_id="mock",
        state="committed", committed_revision=3, attempts=1
    )
    assert record.state == "committed"
    # Job orchestrator must implement the "never retry committed batch" business rule.


def test_future_prompt_contracts_have_json_schema():
    from contracts import (
        PaperOutline, TranslationRepair, QueryAnswer, QueryDistillation,
        LintIssueBatch, ReadingSynthesisDraft, WikiDeltaProposal,
    )
    for contract in [PaperOutline, TranslationRepair, QueryAnswer, QueryDistillation,
                     LintIssueBatch, ReadingSynthesisDraft, WikiDeltaProposal]:
        schema = contract.model_json_schema()
        assert schema["type"] == "object"
        assert (ROOT / "schemas" / "generated" / f"{contract.__name__}.schema.json").exists()


def test_node_detail_and_layout_separate():
    from contracts import NodeDetail, GraphLayoutSnapshot
    detail = NodeDetail.model_validate(load("graph_node_detail.json"))
    assert detail.full_text_en != detail.label_en
    layout = GraphLayoutSnapshot.model_validate({
        "project_id": "project-demo", "view_id": "default", "layout_version": 1,
        "positions": [{"node_id": "claim-001", "x": 20, "y": 30, "pinned": True}],
    })
    assert layout.positions[0].pinned
    assert "x" not in NodeDetail.model_fields
