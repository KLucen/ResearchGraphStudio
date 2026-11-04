import asyncio
import copy
import json

import pytest
import test_knowledge
from researchgraph import reading_wire, unified_extraction
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.models import Job
from researchgraph.providers import MockProvider
from researchgraph.reading_scope import current_nodes
from researchgraph.reading_validation import validate_batch
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import post
from test_reading_extraction import candidate_batch, save

seeded = test_knowledge.seeded


def test_waiver_preserves_note_without_relaxing_scientific_validation():
    data = candidate_batch("evidence")
    data["waiver"] = "Only the supplied evidence identifiers were used."
    raw = json.dumps(data)
    audit = []
    batch, _ = validate_batch(raw, {"evidence"}, wire_changes=audit)
    assert len(batch.items) == 4 and batch.warnings[-1].endswith(data["waiver"])
    assert audit == [{"path": "waiver", "rule": "envelope-note-to-warning-v1"}]
    assert json.loads(raw) == data
    data["items"][0]["evidence_ids"] = ["invented"]
    with pytest.raises(ValueError, match="whitelist"):
        validate_batch(json.dumps(data), {"evidence"})


@pytest.mark.parametrize(
    "fault", ["nested", "object", "other_extra", "missing_items", "missing_links"]
)
def test_note_handling_does_not_allow_arbitrary_extensions(fault):
    data = candidate_batch("e")
    if fault == "nested":
        data["items"][0]["waiver"] = "skip validation"
    elif fault == "object":
        data["waiver"] = {"evidence_ids": ["invented"]}
    elif fault == "other_extra":
        data["other_metadata"] = "unknown semantics"
    else:
        data.pop(fault.removeprefix("missing_"))
    with pytest.raises(ValueError):
        validate_batch(json.dumps(data), {"e"})


def test_legacy_knowledge_is_retained_but_not_used_in_new_reading(seeded):
    api, engine, eid = seeded
    save(engine, eid)
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        before = reading.snapshot("version")
        node = session.scalar(select(KnowledgeNode))
        legacy = KnowledgeNode(
            **{c.name: copy.deepcopy(getattr(node, c.name)) for c in node.__table__.columns}
        )
        legacy.id, legacy.fingerprint = "legacy-node", "legacy-fingerprint"
        # Even a payload looking like the new DTO is insufficient without provenance.
        run = session.get(ModelRun, "run")
        old = ModelRun(
            **{c.name: copy.deepcopy(getattr(run, c.name)) for c in run.__table__.columns}
        )
        old.id, old.schema_version, old.prompt_name = (
            "old-run",
            "unified-v3.1",
            "P02_unified_section_extract",
        )
        session.add(old)
        session.flush()
        legacy.model_run_id = old.id
        session.add(legacy)
        session.flush()
        assert len(reading.nodes("version")) == 4 and reading.snapshot("version") == before
    assert len(api.get("/api/v1/revisions/version/knowledge").json()["items"]) == 5
    assert (
        len(api.get("/api/v1/revisions/version/knowledge?current_schema_only=true").json()["items"])
        == 4
    )
    assert len(api.get("/api/v1/papers/paper/candidates").json()["items"]) == 4
    assert api.get("/api/v1/knowledge/nodes/legacy-node").status_code == 200
    graph = api.get("/api/v1/graph/subgraph?project_id=project&current_schema_only=true").json()
    assert "legacy-node" not in {n["id"] for n in graph["nodes"]}
    recall = post(
        api,
        "/knowledge/candidates",
        {"source_id": "legacy-node", "current_schema_only": True},
        key="legacy-recall",
    )
    assert recall.status_code >= 400


@pytest.mark.parametrize("extra_note", ["waiver", "kind_note_unused"])
def test_upgrade_replays_failed_response_without_calling_model_or_changing_history(
    seeded, monkeypatch, extra_note
):
    api, engine, _ = seeded
    # Produce a genuine frozen older plan with a received, failed envelope.
    monkeypatch.setattr(reading_wire, "PROMPT", "P02_reading_extract_compact")

    class Extra(MockProvider):
        async def complete(self, prompt, data, schema):
            raw = await super().complete(prompt, data, schema)
            if schema["title"] == "KnowledgeExtractionBatch":
                value = json.loads(raw)
                if extra_note == "kind_note_unused":
                    claim = next(item for item in value["items"] if item["kind"] == "Claim")
                    claim["kind_note_unused"] = None
                else:
                    value["waiver"] = "only source evidence"
                # Simulate the pre-fix validator by rejecting after receiving this response.
                return json.dumps(value)
            return raw

    with Session(engine) as session, session.begin():
        session.get(Job, "job").payload = {
            "document_version_id": "version",
            "pipeline": "paper-reading-v1",
            "provider": "mock",
            "allow_network": False,
        }
    from researchgraph import reading_validation

    original_validate = reading_validation.validate_batch

    def failed(*args, **kwargs):
        raise ValueError(f"Schema 校验失败：{extra_note} (extra_forbidden)")

    monkeypatch.setattr(reading_validation, "validate_batch", failed)
    monkeypatch.setattr(unified_extraction, "provider_for", lambda *a: Extra())
    with pytest.raises(ValueError, match="阶段协议或证据校验"):
        asyncio.run(unified_extraction.run_unified_extraction(engine, "job", reading=True))
    monkeypatch.setattr(reading_validation, "validate_batch", original_validate)
    monkeypatch.setattr(reading_wire, "PROMPT", "P02_reading_extract_compact_v2")
    with Session(engine) as session, session.begin():
        old = session.get(Job, "job")
        old.status, old.attempt = "failed", 3
        before = copy.deepcopy(old.payload)
        original = session.scalar(
            select(ModelRun).where(ModelRun.job_id == "job", ModelRun.status == "validation_failed")
        )
        raw, status, rid = original.raw_output, original.status, original.id
    response = post(api, "/jobs/job/retry", key="upgrade-one")
    assert response.status_code == 200, response.text
    jid = response.json()["id"]
    assert jid != "job" and post(api, "/jobs/job/retry", key="upgrade-again").json()["id"] == jid

    model_calls = []

    class NoExtraction(MockProvider):
        async def complete(self, prompt, data, schema):
            assert schema["title"] != "KnowledgeExtractionBatch", (
                "Reused response must cost zero extraction calls"
            )
            model_calls.append(schema["title"])
            return await super().complete(prompt, data, schema)

    monkeypatch.setattr(unified_extraction, "provider_for", lambda *a: NoExtraction())
    with Session(engine) as session, session.begin():
        session.get(Job, jid).status = "running"
    asyncio.run(unified_extraction.run_unified_extraction(engine, jid, reading=True))
    with Session(engine) as session:
        assert session.get(Job, jid).status == "succeeded"
        assert session.get(Job, jid).payload["unified_plan"]["prompt_name"] == reading_wire.PROMPT
        assert session.get(Job, "job").payload == before
        assert (session.get(ModelRun, rid).raw_output, session.get(ModelRun, rid).status) == (
            raw,
            status,
        )
        assert current_nodes(session, "version")
        reused = [
            r
            for r in session.scalars(select(ModelRun).where(ModelRun.job_id == jid))
            if r.parameters.get("response_reused_from")
        ]
        assert (
            len(reused) == 1
            and reused[0].raw_output == raw
            and reused[0].parameters["attempts"] == []
        )
        successor_payload = copy.deepcopy(session.get(Job, jid).payload)
        successor_result = copy.deepcopy(session.get(Job, jid).result)
        original_error = session.get(Job, "job").error
    calls_after_completion = list(model_calls)
    # Repeating the action on a historical failed row resolves to the existing
    # successful successor. It must not queue another extraction or mutate the
    # old failure/raw; the UI has to surface this successful returned task.
    for key in ("upgrade-after-success-one", "upgrade-after-success-two"):
        response = post(api, "/jobs/job/retry", key=key)
        assert response.status_code == 200, response.text
        assert response.json()["id"] == jid and response.json()["status"] == "succeeded"
        assert response.json()["result"] == successor_result
    assert model_calls == calls_after_completion
    with Session(engine) as session:
        assert session.get(Job, jid).payload == successor_payload
        assert session.get(Job, jid).status == "succeeded"
        assert session.get(Job, "job").status == "failed"
        assert session.get(Job, "job").error == original_error
        assert session.get(Job, "job").payload == before
        assert session.get(ModelRun, rid).raw_output == raw
        assert session.get(ModelRun, rid).status == status
