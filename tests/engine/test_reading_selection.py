import asyncio

import pytest
import test_knowledge
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun, ReviewDecision
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, text_hash
from researchgraph.models import Chunk, Job
from researchgraph.providers import MockProvider, ProviderError
from researchgraph.reading_models import CandidateMetadata, ReadingSelection
from researchgraph.reading_pipeline import finish_reading
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_reading_extraction import candidate_batch, save


def setup_job(engine):
    with Session(engine) as session, session.begin():
        session.get(Job, "job").payload = {"document_version_id": "version", "density": "standard"}


def test_unit_selection_and_density_do_not_rewrite_knowledge(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        assert len(current.data["units"]) == 1
        assert len(current.data["units"][0]["memberships"]) == 3
        assert [e["graph_role"] for e in current.data["entries"]].count("core") == 1
        assert session.scalar(select(func.count()).select_from(ReviewDecision)) == 0
        count = session.scalar(select(func.count()).select_from(KnowledgeNode))
        reading.publish(
            version_id="version",
            snapshot=current.snapshot_hash,
            unit_ids=current.data["integration_unit_ids"],
            proposal=current.data["selection_proposal"],
            density="concise",
            expected_revision=1,
            key="density-test",
        )
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == count
        with pytest.raises(KnowledgeError, match="选择已更新"):
            reading.publish(
                version_id="version",
                snapshot=current.snapshot_hash,
                unit_ids=current.data["integration_unit_ids"],
                proposal=current.data["selection_proposal"],
                density="detailed",
                expected_revision=1,
                key="stale-density",
            )


def test_failed_selection_reuses_integration_response(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)

    class Failing(MockProvider):
        calls = []
        fail = True

        async def complete(self, prompt, data, schema):
            self.calls.append(schema["title"])
            if schema["title"] == "CoreSelectionProposal" and self.fail:
                raise ProviderError("timeout", "synthetic timeout", timeout_phase="total")
            return await super().complete(prompt, data, schema)

    provider = Failing()
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "job", provider))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ReadingSelection)) == 0
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 4
    provider.fail = False
    asyncio.run(finish_reading(engine, "job", provider))
    assert provider.calls.count("PaperIntegrationProposal") == 1
    assert provider.calls.count("CoreSelectionProposal") == 2
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"
        assert session.scalar(select(func.count()).select_from(ModelRun)) == 4


def test_unreachable_member_rejected_and_old_graph_kept(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        nodes = reading.nodes("version")
        root = next(n.id for n in nodes if n.kind == "claim")
        proposal = {
            "contract_version": "reading-integration-1.0",
            "document_version_id": "version",
            "input_revision": int(current.snapshot_hash[:12], 16),
            "units": [
                {
                    "local_ref": "u",
                    "root_claim_id": root,
                    "member_ids": ["nonexistent"],
                    "rationale": "bad",
                }
            ],
        }
        with pytest.raises(KnowledgeError, match="不存在"):
            reading.integrate(
                proposal=proposal,
                version_id="version",
                snapshot=current.snapshot_hash,
                run_id="run",
                key="bad-unit",
            )
        assert reading.current("paper").id == current.id


def test_integration_completes_multihop_support_omitted_by_model_without_guessing(seeded):
    import copy
    import json

    _, engine, eid = seeded
    data = candidate_batch(eid)
    experiment = copy.deepcopy(data["items"][1])
    experiment.update(
        local_ref="e",
        kind="Experiment",
        protocol={"original": "Evaluate with 3 agents", "language": "en"},
    )
    experiment.pop("method_role")
    unrelated = copy.deepcopy(data["items"][1])
    unrelated.update(local_ref="unrelated", summary={"original": "Other method", "language": "en"})
    data["items"] += [experiment, unrelated]
    data["links"] = [
        dict(
            source_local_ref=source, target_local_ref=target, relation=relation, evidence_ids=[eid]
        )
        for source, target, relation in [
            ("c", "e", "SUPPORTED_BY"),
            ("e", "m", "ASSOCIATED_METHOD"),
            ("e", "f", "REPORTS_FINDING"),
            ("m", "d", "HAS_CONDITION"),
        ]
    ]
    save(engine, eid, data)
    setup_job(engine)

    class OmittedMembers(MockProvider):
        async def complete(self, prompt, data, schema):
            result = json.loads(await super().complete(prompt, data, schema))
            if schema["title"] == "PaperIntegrationProposal":
                for unit in result["units"]:
                    unit["member_ids"] = []
            return json.dumps(result)

    asyncio.run(finish_reading(engine, "job", OmittedMembers()))
    with Session(engine) as session:
        reading = KnowledgeStore(session).reading()
        units = reading.current("paper").data["units"]
        assert len(units) == 1
        members = units[0]["memberships"]
        assert len(members) == 4
        kinds = {session.get(KnowledgeNode, m["member_id"]).kind for m in members}
        assert kinds == {"method", "finding", "condition", "experiment"}
        condition = next(
            m for m in members if session.get(KnowledgeNode, m["member_id"]).kind == "condition"
        )
        assert len(condition["association_ids"]) == 3
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 6


def test_support_does_not_cross_other_claim_or_invalid_association(seeded):
    import copy

    from researchgraph.graph_models import SourceAssertion
    from researchgraph.knowledge_models import KnowledgeDependency
    from researchgraph.reading_support import reachable_supports, support_paths

    _, engine, eid = seeded
    data = candidate_batch(eid)
    second = copy.deepcopy(data["items"][0])
    second.update(local_ref="c2", statement={"original": "Other claim", "language": "en"})
    data["items"].append(second)
    data["links"] = [
        dict(
            source_local_ref="c2",
            target_local_ref="m",
            relation="ASSOCIATED_METHOD",
            evidence_ids=[eid],
        )
    ]
    save(engine, eid, data)
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        nodes = {n.id: n for n in reading.nodes("version")}
        first = next(n.id for n in nodes.values() if n.kind == "claim" and n.text != "Other claim")
        other = next(n.id for n in nodes.values() if n.text == "Other claim")
        method = next(n.id for n in nodes.values() if n.kind == "method")
        condition = next(n.id for n in nodes.values() if n.kind == "condition")
        session.add(KnowledgeDependency(node_id=first, dependee_id=other, role="explicit"))
        session.add(
            SourceAssertion(
                id="invalid-association",
                project_id="project",
                source_id=first,
                target_id=method,
                relation="ASSOCIATED_METHOD",
                evidence_ids=["nonexistent"],
                model_run_id="run",
            )
        )
        session.add(
            SourceAssertion(
                id="wrong-endpoint",
                project_id="project",
                source_id=first,
                target_id=condition,
                relation="ASSOCIATED_METHOD",
                evidence_ids=[eid],
                model_run_id="run",
            )
        )
        session.flush()
        assert reachable_supports(first, nodes, support_paths(reading, "version", nodes)) == {
            first: []
        }


def test_new_pipeline_offline_end_to_end(seeded):
    _, engine, _ = seeded
    from researchgraph.extraction import run_extraction

    with Session(engine) as session, session.begin():
        session.get(Job, "job").payload = {
            "document_version_id": "version",
            "pipeline": "paper-reading-v1",
            "provider": "mock",
            "allow_network": False,
        }
    asyncio.run(run_extraction(engine, "job"))
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"
        assert KnowledgeStore(session).reading().current("paper").data["units"]


def test_identical_new_job_reuses_semantic_stages(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)

    class Counting(MockProvider):
        calls = 0

        async def complete(self, prompt, data, schema):
            self.calls += 1
            return await super().complete(prompt, data, schema)

    provider = Counting()
    asyncio.run(finish_reading(engine, "job", provider))
    assert provider.calls == 2
    from researchgraph.models import now

    with Session(engine) as session, session.begin():
        session.add(
            Job(
                id="second-job",
                kind="knowledge_extract",
                project_id="project",
                status="running",
                attempt=1,
                created_at=now(),
                updated_at=now(),
                payload={"document_version_id": "version", "density": "standard"},
            )
        )
    asyncio.run(finish_reading(engine, "second-job", provider))
    assert provider.calls == 2


# Explicit alias keeps the shared fixture registered when lint removes unused imports.
seeded = test_knowledge.seeded


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize(
    "fault", ["missing", "empty", "wrong_member", "reverse", "type", "project", "evidence"]
)
def test_store_publish_rechecks_actual_paths_even_when_operation_is_cached(seeded, cached, fault):
    from researchgraph.graph_models import SourceAssertion
    from researchgraph.models import Project, now
    from researchgraph.reading_models import CandidateMetadata, ReadingMember

    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        data, original_id = current.data, current.id
        member = session.scalar(
            select(ReadingMember).where(ReadingMember.unit_id == data["integration_unit_ids"][0])
        )
        edge = session.get(SourceAssertion, member.association_ids[0])
        if fault == "missing":
            member.association_ids = ["invented-association"]
        elif fault == "empty":
            member.association_ids = []
        elif fault == "wrong_member":
            edge.target_id = next(
                m.node_id
                for m in session.scalars(select(ReadingMember))
                if m.node_id != member.node_id
            )
        elif fault == "reverse":
            edge.source_id, edge.target_id = edge.target_id, edge.source_id
        elif fault == "type":
            session.get(KnowledgeNode, member.node_id).kind = "claim"
        elif fault == "project":
            session.add(
                Project(
                    id="other-project", name="Synthetic unrelated", description="", created_at=now()
                )
            )
            session.flush()
            edge.project_id = "other-project"
        else:
            edge.evidence_ids = ["missing-evidence"]
        session.flush()
        metadata_before = {
            m.node_id: dict(m.quality) for m in session.scalars(select(CandidateMetadata))
        }
        with pytest.raises(KnowledgeError) as caught:
            reading.publish(
                version_id="version",
                snapshot=current.snapshot_hash,
                unit_ids=data["integration_unit_ids"],
                proposal=data["selection_proposal"],
                density="standard",
                expected_revision=0 if cached else current.revision,
                key="reading:job:publish" if cached else "corrupt-support-test",
            )
        assert caught.value.code == "SUPPORT_CONTEXT_CHANGED"
        assert reading.current("paper").id == original_id
        assert {
            m.node_id: m.quality for m in session.scalars(select(CandidateMetadata))
        } == metadata_before


def test_shared_multihop_support_remains_valid_for_two_claim_units(seeded):
    import copy

    _, engine, eid = seeded
    data = candidate_batch(eid)
    second = copy.deepcopy(data["items"][0])
    second.update(
        local_ref="c2", statement={"original": "Independent second conclusion", "language": "en"}
    )
    experiment = copy.deepcopy(data["items"][1])
    experiment.update(
        local_ref="e", kind="Experiment", protocol={"original": "Shared protocol", "language": "en"}
    )
    experiment.pop("method_role")
    data["items"] += [second, experiment]
    data["links"] = [
        dict(
            source_local_ref=source, target_local_ref=target, relation=relation, evidence_ids=[eid]
        )
        for source, target, relation in [
            ("c", "e", "SUPPORTED_BY"),
            ("c2", "e", "SUPPORTED_BY"),
            ("e", "m", "ASSOCIATED_METHOD"),
            ("e", "f", "REPORTS_FINDING"),
            ("m", "d", "HAS_CONDITION"),
        ]
    ]
    save(engine, eid, data)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        selected = reading.publish(
            version_id="version",
            snapshot=current.snapshot_hash,
            unit_ids=current.data["integration_unit_ids"],
            proposal=current.data["selection_proposal"],
            density="standard",
            expected_revision=current.revision,
            key="shared-support-publish",
        )
        assert len(selected["units"]) == 2
        memberships = [u["memberships"] for u in selected["units"]]
        assert {m["member_id"] for m in memberships[0]} == {m["member_id"] for m in memberships[1]}
        assert all(len(members) == 4 for members in memberships)
        assert all(max(len(m["association_ids"]) for m in members) == 3 for members in memberships)


@pytest.mark.parametrize(
    "fault", ["node_version", "node_paper", "payload_evidence", "node_evidence", "anchor_version"]
)
def test_support_paths_reject_corrupt_identity_or_node_evidence(seeded, fault):
    from researchgraph.knowledge_models import EvidenceSpan, NodeEvidence
    from researchgraph.models import AttachmentRevision, Paper, now
    from researchgraph.reading_support import support_paths, valid_support_node

    _, engine, eid = seeded
    save(engine, eid)
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        nodes = {n.id: n for n in reading.nodes("version")}
        method = next(n for n in nodes.values() if n.kind == "method")
        root = next(n for n in nodes.values() if n.kind == "claim")
        if fault in {"node_version", "anchor_version"}:
            session.add(
                AttachmentRevision(
                    id="other-version",
                    paper_id="paper",
                    sha256="d" * 64,
                    parser_version="synthetic",
                    page_count=1,
                    warnings=[],
                    created_at=now(),
                )
            )
            session.flush()
            if fault == "node_version":
                method.document_version_id = "other-version"
            else:
                session.get(EvidenceSpan, eid).document_version_id = "other-version"
        elif fault == "node_paper":
            session.add(
                Paper(
                    id="other-paper",
                    project_id="project",
                    title="Synthetic other",
                    created_at=now(),
                )
            )
            session.flush()
            method.paper_id = "other-paper"
        elif fault == "payload_evidence":
            method.payload = {**method.payload, "evidence_ids": ["missing-node-evidence"]}
        else:
            session.delete(session.get(NodeEvidence, (method.id, eid)))
        session.flush()
        assert not valid_support_node(reading, "version", method)
        assert not any(
            source == root.id and target == method.id
            for source, target, _ in support_paths(reading, "version", nodes)
        )


@pytest.mark.parametrize(
    "role,target_kind,valid",
    [
        ("USES_METHOD", "method", True),
        ("HAS_CONDITION", "condition", True),
        ("USES_METHOD", "condition", False),
        ("explicit", "method", False),
    ],
)
def test_dependency_paths_enforce_registered_role_and_endpoint_types(
    seeded, role, target_kind, valid
):
    from researchgraph.knowledge_models import KnowledgeDependency
    from researchgraph.reading_support import support_paths

    _, engine, eid = seeded
    save(engine, eid)
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        nodes = {n.id: n for n in reading.nodes("version")}
        root = next(n.id for n in nodes.values() if n.kind == "claim")
        target = next(n.id for n in nodes.values() if n.kind == target_kind)
        session.add(KnowledgeDependency(node_id=root, dependee_id=target, role=role))
        session.flush()
        expected = (root, target, f"dependency:{root}:{target}:{role}")
        assert (expected in support_paths(reading, "version", nodes)) is valid


def save_claim_quotes(engine, eid, quotes, *, method_quote_index=None):
    """Create exact source anchors; their scientific content is deliberately untrusted."""
    with Session(engine) as session, session.begin():
        paragraph = session.get(Chunk, "paragraph")
        paragraph.text = "\n".join(quotes)
        first = session.get(EvidenceSpan, eid)
        ids, offset = [], 0
        for index, quote in enumerate(quotes):
            span = (
                first
                if index == 0
                else EvidenceSpan(
                    id=f"extra-context-{index}",
                    document_version_id=first.document_version_id,
                    section_id=first.section_id,
                    paragraph_id=first.paragraph_id,
                    page_index=first.page_index,
                    normalization="identity-v1",
                    bbox_list=first.bbox_list,
                )
            )
            span.start_offset, span.end_offset = offset, offset + len(quote)
            span.quote, span.text_sha256 = quote, text_hash(paragraph.text)
            if index:
                session.add(span)
            ids.append(span.id)
            offset += len(quote) + 1
        data = candidate_batch(eid)
        for item in data["items"]:
            item["evidence_ids"] = ids
            if item["kind"] == "Method" and method_quote_index is not None:
                item["evidence_ids"] = [ids[method_quote_index]]
        run = session.get(ModelRun, "run")
        run.schema_version, run.prompt_name = "reading-1.0", "P02_reading_extract"
        session.flush()
        KnowledgeStore(session).reading().apply_candidates(
            candidate=data,
            version_id="version",
            paper_id="paper",
            chunk_id="chunk",
            allowed=set(ids),
            run_id="run",
            key="reading-context-fixture",
        )


def retained_context_state(session):
    return {
        "nodes": [
            (n.id, n.payload, n.source_status, n.review_status, n.revision)
            for n in session.scalars(select(KnowledgeNode).order_by(KnowledgeNode.id))
        ],
        "anchors": [
            (s.id, s.quote, s.start_offset, s.end_offset, s.text_sha256, s.bbox_list)
            for s in session.scalars(select(EvidenceSpan).order_by(EvidenceSpan.id))
        ],
        "raw": session.get(ModelRun, "run").raw_output,
    }


@pytest.mark.parametrize(
    "quotes",
    [
        ["K"],
        ["2"],
        ["_"],
        ["K", "2", "_"],
        [" \t "],
        [r"\alpha + \beta = 2"],
        [r"\begin{equation} x_i^2 = \frac{1}{2} \end{equation}"],
        ["𝑥 + 𝑦 ≤ 3", "∑", "−1.25e−3"],
    ],
)
def test_fragment_only_claims_stay_retrievable_with_all_source_material_retained(seeded, quotes):
    _, engine, eid = seeded
    save_claim_quotes(engine, eid, quotes)
    setup_job(engine)
    with Session(engine) as session:
        before = retained_context_state(session)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session:
        reading = KnowledgeStore(session).reading()
        root = next(n for n in reading.nodes("version") if n.kind == "claim")
        assert reading.source_valid(root)  # An exact anchor is not readable scientific context.
        current = reading.current("paper")
        assert not current.data["units"] and current.data["build_state"] == "partial"
        assert all(e["graph_role"] == "retrieval_only" for e in current.data["entries"])
        quality = session.get(CandidateMetadata, root.id).quality
        assert quality["blocking_issues"] == ["引用仅含公式/标记碎片，缺少可解释原文上下文"]
        assert quality["evidence_completeness"] == "insufficient"
        assert retained_context_state(session) == before


@pytest.mark.parametrize(
    "quotes",
    [
        ["准确率提升"],
        ["lower bound"],
        ["AI"],
        [r"\alpha + \beta = 2", "该上界成立"],
        [r"\frac{x}{2}", "The bound holds."],
        [r"Let $K=2$"],
    ],
)
def test_short_readable_context_and_theoretical_formula_context_can_be_core(seeded, quotes):
    _, engine, eid = seeded
    save_claim_quotes(engine, eid, quotes)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session:
        reading = KnowledgeStore(session).reading()
        root = next(n for n in reading.nodes("version") if n.kind == "claim")
        assert len(reading.current("paper").data["units"]) == 1
        assert session.get(CandidateMetadata, root.id).quality["blocking_issues"] == []


@pytest.mark.parametrize("mode", ["ranked", "provisional"])
def test_fragment_gate_cannot_be_overridden_by_include_preference_or_preview(seeded, mode):
    _, engine, eid = seeded
    save_claim_quotes(engine, eid, ["K", "2", "_"])
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        root = next(n.id for n in reading.nodes("version") if n.kind == "claim")
        reading.set_preference(root, "include_core", "Synthetic display preference")
        data = reading.publish(
            version_id="version",
            snapshot=current.snapshot_hash,
            unit_ids=current.data["integration_unit_ids"],
            proposal=current.data["selection_proposal"],
            density="detailed",
            expected_revision=current.revision,
            selection_mode=mode,
            key="fragment-preference:" + mode,
        )
        assert not data["units"]
        assert all(e["graph_role"] == "retrieval_only" for e in data["entries"])
        assert (
            session.get(CandidateMetadata, root).quality["evidence_completeness"] == "insufficient"
        )


def test_fragment_core_in_historical_cache_is_not_republished_or_rewritten(seeded, monkeypatch):
    from researchgraph import reading_selection

    _, engine, eid = seeded
    save_claim_quotes(engine, eid, ["K", "2", "_"])
    setup_job(engine)
    # Simulate an existing selection produced before the readable-context gate.
    with monkeypatch.context() as old_policy:
        old_policy.setattr(reading_selection, "_fragment_claim", lambda *args: False)
        asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        old_id, old_data = current.id, current.data
        before = retained_context_state(session)
        assert current.data["units"]
        with pytest.raises(KnowledgeError) as caught:
            reading.publish(
                version_id="version",
                snapshot=current.snapshot_hash,
                unit_ids=current.data["integration_unit_ids"],
                proposal=current.data["selection_proposal"],
                density="standard",
                expected_revision=0,
                key="reading:job:publish",
            )
        assert caught.value.code == "CORE_EVIDENCE_CONTEXT_REQUIRED"
        assert reading.current("paper").id == old_id
        assert reading.current("paper").data == old_data
        assert retained_context_state(session) == before


def test_formula_only_support_is_retained_when_claim_has_readable_context(seeded):
    _, engine, eid = seeded
    save_claim_quotes(engine, eid, ["K", "The bound holds."], method_quote_index=0)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session:
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        method = next(n for n in reading.nodes("version") if n.kind == "method")
        assert reading.source_valid(method)
        assert any(
            e["candidate_id"] == method.id and e["graph_role"] == "supporting"
            for e in current.data["entries"]
        )


@pytest.mark.parametrize("recommendation", ["needs_context", "keep_retrievable"])
def test_insufficient_model_support_is_never_labeled_sufficient(seeded, recommendation):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        proposal = {
            **current.data["selection_proposal"],
            "recommendations": [
                {
                    **hint,
                    "recommendation": recommendation,
                    "reasons": ["insufficient_support"],
                    "rationale": "Source is exact but does not establish this conclusion.",
                }
                for hint in current.data["selection_proposal"]["recommendations"]
            ],
        }
        data = reading.publish(
            version_id="version",
            snapshot=current.snapshot_hash,
            unit_ids=current.data["integration_unit_ids"],
            proposal=proposal,
            density="standard",
            expected_revision=current.revision,
            key="insufficient-model-support:" + recommendation,
        )
        root = next(n.id for n in reading.nodes("version") if n.kind == "claim")
        quality = session.get(CandidateMetadata, root).quality
        assert quality["evidence_completeness"] == "insufficient"
        assert all(e["graph_role"] != "core" for e in data["entries"])


@pytest.mark.parametrize("member_has_issue", [False, True])
def test_existing_member_issues_remain_visible_in_unit_quality_without_blocking(
    seeded, member_has_issue
):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    with Session(engine) as session, session.begin():
        method = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "method"))
        if member_has_issue:
            method.issues = ["numeric_value_may_be_misread", "numeric_value_may_be_misread"]
        member_id, original_issues = method.id, list(method.issues)
        root = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "claim"))
        assert root.issues == []
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session:
        current = KnowledgeStore(session).reading().current("paper")
        assert len(current.data["units"]) == 1
        unit = current.data["units"][0]
        quality = session.get(CandidateMetadata, unit["root_claim_id"]).quality
        expected = [f"支撑 {member_id}：numeric_value_may_be_misread"] if member_has_issue else []
        assert quality["caveats"] == unit["caveats"] == expected
        assert quality["evidence_completeness"] == ("limited" if member_has_issue else "sufficient")
        assert quality["blocking_issues"] == []
        assert session.get(KnowledgeNode, member_id).issues == original_issues
        assert session.get(ModelRun, "run").raw_output == '{"original":true}'
