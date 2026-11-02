import copy

import pytest
import test_knowledge
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun, ReviewDecision
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def candidate_batch(eid, version="version", chunk="chunk"):
    def item(ref, kind, text, **fields):
        source = {"original": text, "language": "en", "zh": "合成样例"}
        return dict(
            local_ref=ref,
            kind=kind,
            label=source,
            summary=source,
            origin="paper_author",
            evidence_ids=[eid],
            **fields,
        )

    return {
        "contract_version": "reading-extraction-1.0",
        "document_version_id": version,
        "chunk_id": chunk,
        "items": [
            item(
                "c",
                "Claim",
                "Our method achieves accuracy 81% with 3 agents.",
                statement={"original": "Accuracy 81% with 3 agents", "language": "en"},
                contribution_type="empirical_result",
                modality="conditional",
            ),
            item("m", "Method", "Our method", method_role="proposed"),
            item(
                "f",
                "Finding",
                "Accuracy 81%",
                result={"original": "81%", "language": "en"},
                reported_value="81",
                unit="%",
            ),
            item(
                "d",
                "Condition",
                "3 agents",
                dimension="agents",
                state="known",
                value={"original": "3", "language": "en"},
            ),
        ],
        "links": [
            dict(source_local_ref="c", target_local_ref=ref, relation=rel, evidence_ids=[eid])
            for ref, rel in [
                ("m", "ASSOCIATED_METHOD"),
                ("f", "SUPPORTED_BY"),
                ("d", "HAS_CONDITION"),
            ]
        ],
    }


def save(engine, eid, data=None, key="reading-test"):
    with Session(engine) as session, session.begin():
        return (
            KnowledgeStore(session)
            .reading()
            .apply_candidates(
                candidate=data or candidate_batch(eid),
                version_id="version",
                paper_id="paper",
                chunk_id="chunk",
                allowed={eid},
                run_id="run",
                key=key,
            )
        )


def test_reading_dedup_evidence_and_original_model_preserved(seeded):
    _, engine, eid = seeded
    first = save(engine, eid)
    assert save(engine, eid, key="another-operation")["node_ids"] == first["node_ids"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 4
        assert session.scalar(select(func.count()).select_from(ReviewDecision)) == 0
        assert session.get(ModelRun, "run").raw_output == '{"original":true}'
        assert all(n.review_status == "unreviewed" for n in session.scalars(select(KnowledgeNode)))


@pytest.mark.parametrize("fault", ["evidence", "version", "offset", "extra", "condition"])
def test_invalid_reading_batch_is_atomic(seeded, fault):
    _, engine, eid = seeded
    data = candidate_batch(eid)
    if fault == "evidence":
        data["items"][0]["evidence_ids"] = ["invented"]
    elif fault == "version":
        data["document_version_id"] = "other"
    elif fault == "offset":
        with Session(engine) as session, session.begin():
            session.get(EvidenceSpan, eid).end_offset -= 1
    elif fault == "extra":
        data["items"][0]["findings_placeholder"] = None
    else:
        data["items"][-1]["state"] = "unknown"
    with pytest.raises((KnowledgeError, ValueError)):
        save(engine, eid, data)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 0


def test_theory_has_argument_without_invented_experiment(seeded):
    _, engine, eid = seeded
    data = candidate_batch(eid)
    data["items"] = data["items"][:1] + [
        dict(
            local_ref="a",
            kind="Argument",
            label={"original": "Proof", "language": "en"},
            summary={"original": "Proof", "language": "en"},
            origin="paper_author",
            evidence_ids=[eid],
            argument_type="proof",
        )
    ]
    data["items"][0]["contribution_type"] = "theoretical_result"
    data["links"] = [
        dict(
            source_local_ref="c", target_local_ref="a", relation="SUPPORTED_BY", evidence_ids=[eid]
        )
    ]
    save(engine, eid, copy.deepcopy(data))
    with Session(engine) as session:
        assert set(session.scalars(select(KnowledgeNode.kind))) == {"claim", "argument"}


def test_quarantine_only_invalid_association_not_source_or_fields():
    import json

    from researchgraph.reading_validation import validate_batch

    data = candidate_batch("ev")
    data["links"].append(
        {
            "source_local_ref": "f",
            "target_local_ref": "d",
            "relation": "HAS_CONDITION",
            "evidence_ids": ["ev"],
        }
    )
    result, isolated = validate_batch(json.dumps(data), {"ev"})
    assert len(result.items) == 4 and len(result.links) == 3 and len(isolated) == 1
    assert result.warnings
    data["links"][-1]["evidence_ids"] = ["invented"]
    with pytest.raises(ValueError, match="whitelist"):
        validate_batch(json.dumps(data), {"ev"})


@pytest.mark.parametrize(
    "name", ["extraction_methodological", "extraction_theoretical", "extraction_review"]
)
def test_runtime_contract_accepts_nonexperimental_reference_types(name):
    from pathlib import Path

    from researchgraph.reading_contracts import KnowledgeExtractionBatch

    batch = KnowledgeExtractionBatch.model_validate_json(
        (Path("docs/examples") / (name + ".json")).read_text(encoding="utf-8")
    )
    assert batch.items
    assert not any(item.kind == "Experiment" for item in batch.items)


# Explicit alias keeps the shared fixture registered when lint removes unused imports.
seeded = test_knowledge.seeded
