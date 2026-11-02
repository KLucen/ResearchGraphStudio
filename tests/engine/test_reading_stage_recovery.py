import asyncio
import copy
import json

import pytest
import test_knowledge
from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.models import Job
from researchgraph.providers import MockProvider
from researchgraph.reading_models import CandidateMetadata
from researchgraph.reading_pipeline import finish_reading
from researchgraph.reading_validation import (
    isolate_integration_proposals,
    validate_integration,
    validate_selection,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_reading_extraction import candidate_batch, save

seeded = test_knowledge.seeded


def test_integration_quarantine_never_repairs_hallucinated_references():
    value = {
        "units": [
            {"root_claim_id": "root", "member_ids": ["method", "invented"]},
            {"root_claim_id": "outside-root", "member_ids": []},
        ],
        "associations": [{"source_id": "root", "target_id": "method", "evidence_ids": ["fake"]}],
        "duplicates": [{"candidate_ids": ["root", "outside-root"]}],
        "warnings": [],
    }
    data = {
        "root_claim_ids": ["root"],
        "candidates": [{"id": "root"}, {"id": "method"}],
        "allowed_evidence": [{"id": "real"}],
    }
    audit = isolate_integration_proposals(value, data)
    assert len(audit) == 4 and value["warnings"]
    assert value["units"] == [{"root_claim_id": "root", "member_ids": ["method"]}]
    assert value["associations"] == [] and value["duplicates"] == []


def test_stage_notes_and_root_self_membership_are_losslessly_normalized():
    data = {
        "contract_version": "reading-integration-1.0",
        "document_version_id": "v",
        "input_revision": 1,
        "units": [
            {
                "local_ref": "u",
                "root_claim_id": "c",
                "member_ids": ["c", "m"],
                "rationale": "source support",
            }
        ],
        "limitations": ["Table context is incomplete."],
    }
    raw = json.dumps(data)
    value, audit = validate_integration(raw)
    assert value["units"][0]["member_ids"] == ["m"]
    assert value["warnings"] == data["limitations"] and len(audit) == 2
    assert json.loads(raw) == data
    data["units"][0]["member_ids"] += ["m"]
    with pytest.raises(ValueError):
        validate_integration(json.dumps(data))
    selected = {
        "contract_version": "reading-selection-1.0",
        "document_version_id": "v",
        "input_revision": 1,
        "recommendations": [],
        "warnings": ["A"],
        "limitations": ["B"],
    }
    value, audit = validate_selection(json.dumps(selected))
    assert value["coverage_gaps"] == ["A", "B"] and len(audit) == 3
    selected["limitations"] = [{"invented": "science"}]
    with pytest.raises(ValueError):
        validate_selection(json.dumps(selected))


def test_invalid_integration_edge_is_quarantined_but_unknown_evidence_is_rejected(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    with Session(engine) as session, session.begin():
        store = KnowledgeStore(session).reading()
        nodes = {n.kind: n.id for n in store.nodes("version")}
        snapshot = store.snapshot("version")
        value = {
            "contract_version": "reading-integration-1.0",
            "document_version_id": "version",
            "input_revision": int(snapshot[:12], 16),
            "units": [],
            "associations": [
                {
                    "source_id": nodes["finding"],
                    "target_id": nodes["condition"],
                    "relation": "HAS_CONDITION",
                    "evidence_ids": [eid],
                    "rationale": "synthetic invalid direction",
                }
            ],
        }
        result = store.integrate(
            proposal=value, version_id="version", snapshot=snapshot, run_id="run", key="quarantine"
        )
        assert (
            result["warnings"]
            and session.get(ModelRun, "run").parameters["quarantined_integration_associations"]
        )
        assert not session.scalar(
            select(SourceAssertion).where(SourceAssertion.source_id == nodes["finding"])
        )
        value["associations"][0]["evidence_ids"] = ["invented"]
        with pytest.raises(KnowledgeError, match="整合证据不存在"):
            store.integrate(
                proposal=value,
                version_id="version",
                snapshot=snapshot,
                run_id="run",
                key="invalid-evidence",
            )


def test_conflicting_duplicate_suggestion_does_not_fold_or_abort_other_units(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    second = candidate_batch(eid)
    second["items"] = [second["items"][0]]
    second["items"][0]["origin"] = "citation_report"
    second["links"] = []
    save(engine, eid, second, key="citation")
    with Session(engine) as session, session.begin():
        store = KnowledgeStore(session).reading()
        roots = [n.id for n in store.nodes("version") if n.kind == "claim"]
        snapshot = store.snapshot("version")
        value = {
            "contract_version": "reading-integration-1.0",
            "document_version_id": "version",
            "input_revision": int(snapshot[:12], 16),
            "units": [],
            "duplicates": [
                {
                    "candidate_ids": roots,
                    "representative_id": roots[0],
                    "rationale": "not actually same attribution",
                }
            ],
        }
        result = store.integrate(
            proposal=value,
            version_id="version",
            snapshot=snapshot,
            run_id="run",
            key="different-attribution",
        )
        assert result["warnings"]
        assert all(session.get(CandidateMetadata, root).canonical_id is None for root in roots)


def test_large_support_window_reserves_root_and_reports_gaps(seeded):
    _, engine, eid = seeded
    data = candidate_batch(eid)
    method = data["items"][1]
    for index in range(14):
        support = copy.deepcopy(method)
        support["local_ref"] = f"support-{index}"
        support["summary"]["original"] = str(index) + "Synthetic supporting description. " * 160
        data["items"].append(support)
    save(engine, eid, data)
    with Session(engine) as session, session.begin():
        session.get(Job, "job").payload = {"document_version_id": "version"}
        root = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "claim"))
        # Verify this fixture actually would evict the root under UUID ordering.
        preceding = [
            n for n in KnowledgeStore(session).reading().nodes("version") if n.id < root.id
        ]
        assert sum(len(json.dumps(n.payload)) for n in preceding) > 26000
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"
        selection = KnowledgeStore(session).reading().current("paper")
        assert selection.data["units"] and selection.data["coverage_gaps"]
