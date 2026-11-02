"""Offline P2 acceptance: source boundaries, writes, review history and recovery."""

import asyncio
import json
import sqlite3
import time
from pathlib import Path

import pymupdf
import pytest
from alembic import command
from alembic.config import Config
from researchgraph import extraction
from researchgraph.knowledge_contracts import ExtractionBatch
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, KnowledgeOperation, ModelRun
from researchgraph.knowledge_store import DOMAIN_VERSION, KnowledgeError, KnowledgeStore
from researchgraph.models import AttachmentRevision, Chunk, Job, Paper, Project, now
from researchgraph.providers import ConfiguredProvider, MockProvider
from researchgraph.storage import SCHEMA_HEAD, make_engine
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import queue, wait_job


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "Synthetic methods.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), "Methods")
        page.insert_text((40, 85), "Our method uses shared memory in cooperative tasks.")
        page.insert_text((40, 130), "Results: accuracy improves to 81% under this protocol.")
        page.insert_text((40, 175), "Prior work by Smith et al reports 72%. Not significant.")
        doc.save(path)
    return path


@pytest.fixture
def seeded(tmp_path):
    """Independent source records, no user's runtime database or external providers."""
    with client(tmp_path) as api:
        engine = api.app.state.engine
        with Session(engine) as session, session.begin():
            session.add(Project(id="project", name="Synthetic", description="", created_at=now()))
            session.flush()
            session.add(
                Paper(id="paper", project_id="project", title="Synthetic", created_at=now())
            )
            session.flush()
            session.add(
                AttachmentRevision(
                    id="version",
                    paper_id="paper",
                    sha256="a" * 64,
                    parser_version="test",
                    page_count=1,
                    warnings=[],
                    created_at=now(),
                )
            )
            session.flush()
            session.add(
                Chunk(
                    id="paragraph",
                    revision_id="version",
                    page_index=0,
                    page_label="1",
                    block_index=0,
                    text=(
                        "Our method achieves accuracy 81% with 3 agents. "
                        "Prior work by Smith et al reports 72%."
                    ),
                    bbox=[0.0, 0.0, 100.0, 100.0],
                )
            )
            session.add(
                Job(
                    id="job",
                    kind="knowledge_extract",
                    project_id="project",
                    status="running",
                    attempt=1,
                    created_at=now(),
                    updated_at=now(),
                )
            )
            session.flush()
            KnowledgeStore(session).ensure_document("version")
            session.add(
                ModelRun(
                    id="run",
                    job_id="job",
                    document_version_id="version",
                    provider="mock",
                    model="fixture",
                    prompt_name="P02",
                    prompt_hash="b" * 64,
                    schema_version=DOMAIN_VERSION,
                    input_hash="c" * 64,
                    parameters={},
                    status="received",
                    raw_output='{"original":true}',
                    created_at=now(),
                )
            )
        with Session(engine) as session:
            eid = session.scalar(select(EvidenceSpan.id))
        yield api, engine, eid


def batch(eid):
    return {
        "paper_id": "paper",
        "schema_version": DOMAIN_VERSION,
        "concepts": [{"local_ref": "c", "canonical_name": "memory", "evidence_span_ids": [eid]}],
        "methods": [{"local_ref": "m", "name": "shared memory", "evidence_span_ids": [eid]}],
        "experiments": [
            {
                "local_ref": "e",
                "label": "cooperation",
                "method_local_refs": ["m"],
                "evidence_span_ids": [eid],
            }
        ],
        "claims": [
            {
                "local_ref": "cl",
                "statement": "Our method improves accuracy.",
                "origin": "author_claim",
                "claim_type": "empirical_claim",
                "modality": "conditional",
                "method_local_refs": ["m"],
                "experiment_local_ref": "e",
                "evidence": [{"evidence_span_id": eid}],
                "conditions": [],
            }
        ],
        "findings": [
            {
                "local_ref": "f",
                "statement": "Accuracy is 81%.",
                "value": "81",
                "unit": "%",
                "metric_name": "accuracy",
                "experiment_local_ref": "e",
                "evidence_span_ids": [eid],
            }
        ],
    }


def apply(engine, data, eid, key="operation"):
    with Session(engine) as session, session.begin():
        return KnowledgeStore(session).apply(data, "version", {eid}, "run", key)


def test_typed_store_unknown_conditions_numerical_review_and_dedup(seeded):
    _, engine, eid = seeded
    first = apply(engine, batch(eid), eid)
    second = apply(engine, batch(eid), eid, "another-run")
    assert first["node_ids"] == second["node_ids"] and second["created_ids"] == []
    with Session(engine) as session:
        nodes = session.scalars(select(KnowledgeNode)).all()
        assert {n.kind for n in nodes} == {
            "claim",
            "method",
            "concept",
            "experiment",
            "finding",
            "metric",
            "condition",
        }
        assert all(n.review_status != "accepted" for n in nodes)
        unknowns = [n for n in nodes if n.kind == "condition"]
        assert {n.dimension for n in unknowns} == {"task_type", "dataset", "metric"}
        assert all(n.value is None and n.known_state == "unknown" for n in unknowns)
        finding = next(n for n in nodes if n.kind == "finding")
        assert (
            finding.source_status == "source_verified" and finding.review_status == "needs_review"
        )


@pytest.mark.parametrize(
    "attack",
    [
        "unknown_evidence",
        "other_paper",
        "invalid_ref",
        "duplicate_ref",
        "persistent_id",
        "bad_json_shape",
    ],
)
def test_invalid_batch_cannot_partially_write(seeded, attack):
    _, engine, eid = seeded
    data = batch(eid)
    if attack == "unknown_evidence":
        data["claims"][0]["evidence"][0]["evidence_span_id"] = "ev-does-not-exist"
    elif attack == "other_paper":
        data["paper_id"] = "other"
    elif attack == "invalid_ref":
        data["claims"][0]["method_local_refs"] = ["missing"]
    elif attack == "duplicate_ref":
        data["claims"][0]["local_ref"] = "m"
    elif attack == "persistent_id":
        data["claims"][0]["id"] = "model-decides-id"
    elif attack == "bad_json_shape":
        data["claims"] = "not a list"
    with pytest.raises(ValueError):
        apply(engine, data, eid)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("quote", "invented"),
        ("start_offset", 4),
        ("end_offset", 9999),
        ("text_sha256", "x" * 64),
        ("page_index", 9),
    ],
)
def test_invalid_anchor_blocks_store(seeded, field, value):
    _, engine, eid = seeded
    with Session(engine) as session, session.begin():
        setattr(session.get(EvidenceSpan, eid), field, value)
    with pytest.raises(KnowledgeError, match="不匹配"):
        apply(engine, batch(eid), eid)


def test_cited_claim_and_wrong_number_are_reviewable_not_certified(seeded):
    _, engine, eid = seeded
    data = batch(eid)
    data["claims"][0]["origin"] = "cited_claim"
    data["claims"][0]["evidence"][0]["role"] = "cited_other"
    data["findings"][0]["value"] = "900"
    data["findings"][0]["unit"] = "milliseconds"
    apply(engine, data, eid)
    with Session(engine) as session:
        claim = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "claim"))
        finding = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "finding"))
        assert claim.origin == "cited_claim" and "attribution_review_required" in claim.issues
        assert {"value_not_in_evidence", "unit_not_in_evidence"} <= set(finding.issues)
        assert finding.review_status == "needs_review"


def test_review_conflict_original_model_and_accepted_survive_reextraction(seeded):
    api, engine, eid = seeded
    result = apply(engine, batch(eid), eid)
    data = api.get("/api/v1/revisions/version/knowledge").json()
    claim = next(n for n in data["items"] if n["kind"] == "claim")
    request = {
        "node_id": claim["id"],
        "expected_revision": 1,
        "expected_graph_revision": data["graph_revision"],
        "action": "accept",
        "reason": "Compared with source",
    }
    accepted = post(api, "/knowledge/reviews", request, "accept-claim").json()
    assert accepted["review_status"] == "accepted"
    assert post(api, "/knowledge/reviews", request, "accept-claim").json() == accepted
    assert post(api, "/knowledge/reviews", request, "stale-review").status_code == 409
    request.update(
        action="revise",
        expected_revision=2,
        expected_graph_revision=data["graph_revision"] + 1,
        payload={
            **claim["payload"],
            "statement": "The method improves accuracy only in the reported setting.",
        },
    )
    revised = post(api, "/knowledge/reviews", request, "revise-claim").json()
    assert revised["revision"] == 3 and revised["review_status"] == "needs_review"
    again = apply(engine, batch(eid), eid, "later-extraction")
    assert again["created_ids"] == [] and again["node_ids"] == result["node_ids"]
    detail = api.get(f"/api/v1/knowledge/nodes/{claim['id']}").json()
    assert detail["node"]["text"] == revised["text"]
    assert detail["model_run"]["raw_output"] == '{"original":true}'
    assert len(detail["reviews"]) == 2
    assert detail["reviews"][1]["before"]["review_status"] == "accepted"


def test_mock_offline_pdf_to_review_preview_and_restart(tmp_path, source):
    original = source.read_bytes()
    data = tmp_path / "data"
    with client(data, worker=True) as api:
        project = post(api, "/projects", {"name": "Offline lifecycle"}).json()["id"]
        imported = wait_job(api, queue(api, project, source, "import-knowledge", "managed"))
        assert imported["status"] == "succeeded", imported
        version = imported["result"]["revision_id"]
        structure = api.get(f"/api/v1/revisions/{version}/structure").json()
        assert [s["quote"].strip() for s in structure["evidence"]] == [
            "Methods",
            "Our method uses shared memory in cooperative tasks.",
            "Results: accuracy improves to 81% under this protocol.",
            "Prior work by Smith et al reports 72%. Not significant.",
        ]
        extracted = wait_job(
            api,
            post(
                api, "/knowledge/extract", {"document_version_id": version}, "extract-paper"
            ).json(),
        )
        assert extracted["status"] == "succeeded", extracted
        knowledge = api.get(f"/api/v1/revisions/{version}/knowledge").json()
        assert {"claim", "method", "finding", "condition"} <= {
            n["kind"] for n in knowledge["items"]
        }
        claim = next(n for n in knowledge["items"] if n["kind"] == "claim")
        detail = api.get(f"/api/v1/knowledge/nodes/{claim['id']}").json()
        preview = api.get(f"/api/v1/evidence/{detail['evidence'][0]['id']}/preview")
        assert preview.status_code == 200 and preview.json()["data_url"].startswith(
            "data:image/png;base64,"
        )
        review = post(
            api,
            "/knowledge/reviews",
            {
                "node_id": claim["id"],
                "expected_revision": 1,
                "expected_graph_revision": knowledge["graph_revision"],
                "action": "reject",
                "reason": "Offline mock, not scientific extraction",
            },
            "reject-mock",
        )
        assert review.status_code == 200
        repeat = wait_job(
            api,
            post(
                api, "/knowledge/extract", {"document_version_id": version}, "repeat-extract"
            ).json(),
        )
        assert repeat["status"] == "succeeded"
        assert len(api.get(f"/api/v1/revisions/{version}/knowledge").json()["items"]) == len(
            knowledge["items"]
        )
    with client(data) as api:
        detail = api.get(f"/api/v1/knowledge/nodes/{claim['id']}").json()
        assert detail["node"]["review_status"] == "rejected" and len(detail["reviews"]) == 1
        assert api.get(f"/api/v1/revisions/{version}/chunks").json()["items"]
    assert source.read_bytes() == original


@pytest.mark.parametrize("mode", ["timeout", "failure", "invalid_json", "invalid_evidence"])
def test_model_failures_preserved_without_fake_success(tmp_path, source, monkeypatch, mode):
    class Broken(MockProvider):
        async def complete(self, prompt, data, schema):
            if schema["title"] == "PaperOutline":
                return await super().complete(prompt, data, schema)
            if mode == "timeout":
                raise TimeoutError()
            if mode == "failure":
                raise ValueError("provider refused")
            if mode == "invalid_json":
                return "not JSON"
            output = json.loads(await super().complete(prompt, data, schema))
            output["claims"][0]["evidence"][0]["evidence_span_id"] = "ev-999"
            return json.dumps(output)

    monkeypatch.setattr(extraction, "provider_for", lambda *_: Broken())
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Failed extraction"}).json()["id"]
        imported = wait_job(api, queue(api, project, source, "failure-import"))
        version = imported["result"]["revision_id"]
        failed = wait_job(
            api,
            post(
                api, "/knowledge/extract", {"document_version_id": version}, "failed-extract"
            ).json(),
        )
        assert failed["status"] == "failed", failed
        runs = api.get(f"/api/v1/revisions/{version}/runs").json()
        assert runs[0]["status"] in {"validation_failed", "failed"} and runs[0]["error"]
        assert api.get(f"/api/v1/revisions/{version}/knowledge").json()["items"] == []
        monkeypatch.setattr(extraction, "provider_for", lambda *_: MockProvider())
        retry = post(api, f"/jobs/{failed['id']}/retry", key="retry-extraction").json()
        assert wait_job(api, retry)["status"] == "succeeded"


def test_extraction_separates_outline_ids_from_citable_evidence(tmp_path, source, monkeypatch):
    paragraph_ids = set()
    inputs = []

    class Inspecting(MockProvider):
        async def complete(self, prompt, data, schema):
            if schema["title"] == "PaperOutline":
                assert len(data["sections"]) <= 8
                assert all(s["context"] for s in data["sections"])
                paragraph_ids.update(data["allowed_paragraph_ids"])
            else:
                assert paragraph_ids
                assert not paragraph_ids.intersection(data["allowed_evidence_ids"])
                assert all(set(e) == {"id", "quote"} for e in data["evidence_texts"])
                inputs.append(data)
            return await super().complete(prompt, data, schema)

    monkeypatch.setattr(extraction, "provider_for", lambda *_: Inspecting())
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Evidence namespaces"}).json()["id"]
        imported = wait_job(api, queue(api, project, source, "namespace-import"))
        version = imported["result"]["revision_id"]
        result = wait_job(
            api, post(api, "/knowledge/extract", {"document_version_id": version}).json()
        )
        assert result["status"] == "succeeded", result
        assert inputs
        runs = api.get(f"/api/v1/revisions/{version}/runs").json()
        p02 = next(r for r in runs if r["prompt_name"].startswith("P02"))
        assert p02["input_hash"] == extraction.digest(inputs[0])
        aliases = p02["parameters"]["input_manifest"]["evidence_aliases"]
        assert set(aliases) == set(inputs[0]["allowed_evidence_ids"])
        assert all(key.startswith("ev") for key in aliases)
        claim = next(
            n
            for n in api.get(f"/api/v1/revisions/{version}/knowledge").json()["items"]
            if n["kind"] == "claim"
        )
        detail = api.get(f"/api/v1/knowledge/nodes/{claim['id']}").json()
        assert detail["evidence"][0]["id"] in aliases.values()


def test_short_evidence_ids_are_exact_and_cannot_rewrite_other_fields():
    resolved = extraction.resolve_evidence_aliases(
        {"statement": "ev0001", "evidence_span_ids": ["ev0001"]}, {"ev0001": "real-id"}
    )
    assert resolved == {"statement": "ev0001", "evidence_span_ids": ["real-id"]}
    for invalid in ("ev1", "real-id", "ev0002"):
        with pytest.raises(ValueError, match="白名单"):
            extraction.resolve_evidence_aliases(
                {"evidence_span_id": invalid}, {"ev0001": "real-id"}
            )


def test_failed_later_batch_preserves_saved_progress(tmp_path, monkeypatch):
    source = tmp_path / "Large synthetic.pdf"
    with pymupdf.open() as document:
        for page_index in range(14):
            page = document.new_page()
            page.insert_textbox(
                (40, 40, 550, 800),
                f"Synthetic page marker {page_index}. "
                + "Our synthetic method improves accuracy in the toy task. " * 65,
                fontsize=11,
            )
        document.save(source)

    class LaterFailure(MockProvider):
        def __init__(self):
            self.calls = []
            self.outline_calls = 0
            self.fail_later_batch = True

        async def complete(self, prompt, data, schema):
            if schema["title"] == "ExtractionBatch":
                signature = extraction.digest(data)
                self.calls.append(signature)
                # The second batch remains unavailable across all bounded
                # retries; the first batch must still remain committed.
                if self.fail_later_batch and len(self.calls) >= 2:
                    raise TimeoutError()
            elif schema["title"] == "PaperOutline":
                self.outline_calls += 1
            return await super().complete(prompt, data, schema)

    provider = LaterFailure()
    monkeypatch.setattr(extraction, "provider_for", lambda *_: provider)
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Partial progress"}).json()["id"]
        imported = wait_job(api, queue(api, project, source, "large-import"))
        version = imported["result"]["revision_id"]
        job = wait_job(
            api, post(api, "/knowledge/extract", {"document_version_id": version}).json()
        )
        assert job["status"] == "failed", job
        assert job["result"]["completed_batches"] == "1"
        # This fixture is deliberately sized to the seven-batch recovery case.
        # Keeping the exact count catches accidental changes to the chunking
        # contract that would alter resume semantics and token costs.
        assert job["result"]["total_batches"] == "7"
        assert api.get(f"/api/v1/revisions/{version}/knowledge").json()["items"]
        first_batch_signature = provider.calls[0]
        saved_outline_calls = provider.outline_calls
        provider.fail_later_batch = False
        retry = post(api, f"/jobs/{job['id']}/retry", key="resume-partial-extraction").json()
        recovered = wait_job(api, retry)
        assert recovered["status"] == "succeeded", recovered
        assert recovered["result"]["completed_batches"] == recovered["result"]["total_batches"]
        assert provider.calls.count(first_batch_signature) == 1
        assert provider.outline_calls == saved_outline_calls
        with Session(api.app.state.engine) as session:
            persisted_node_ids = {
                node_id
                for operation in session.scalars(
                    select(KnowledgeOperation).where(KnowledgeOperation.key.like("extraction:%"))
                )
                for node_id in operation.response["node_ids"]
            }
        assert int(recovered["result"]["knowledge_count"]) == len(persisted_node_ids)


def test_cancel_model_does_not_kill_worker_or_publish(tmp_path, source, monkeypatch):
    class Slow(MockProvider):
        async def complete(self, prompt, data, schema):
            await asyncio.sleep(20)
            return await super().complete(prompt, data, schema)

    monkeypatch.setattr(extraction, "provider_for", lambda *_: Slow())
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Cancel extraction"}).json()["id"]
        imported = wait_job(api, queue(api, project, source, "cancel-import"))
        version = imported["result"]["revision_id"]
        job = post(
            api, "/knowledge/extract", {"document_version_id": version}, "slow-extract"
        ).json()
        deadline = time.monotonic() + 3
        while (
            not api.get(f"/api/v1/revisions/{version}/runs").json() and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert (
            post(api, f"/jobs/{job['id']}/cancel", key="cancel-model").json()["status"]
            == "cancelled"
        )
        diagnostic = post(api, "/jobs", {"kind": "diagnostics"}, "after-cancel").json()
        assert wait_job(api, diagnostic)["status"] == "succeeded"
        assert api.get(f"/api/v1/revisions/{version}/knowledge").json()["items"] == []


def test_0004_migration_preserves_old_sources_and_creates_backup(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).parents[2] / "services/engine/researchgraph/migrations"),
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0004")
        connection.exec_driver_sql("INSERT INTO projects VALUES ('p','legacy','','now')")
        connection.exec_driver_sql("INSERT INTO papers VALUES ('paper','p','old paper','now')")
        connection.exec_driver_sql(
            "INSERT INTO attachment_revisions VALUES ('v','paper',?,'legacy',1,'[]','now')",
            ("a" * 64,),
        )
        connection.exec_driver_sql(
            "INSERT INTO chunks VALUES ('chunk','v',0,'1',0,"
            "'Old source stays unchanged','[1,2,30,40]')"
        )
    engine.dispose()
    with client(tmp_path) as api:
        assert (
            api.get("/api/v1/revisions/v/chunks").json()["items"][0]["text"]
            == "Old source stays unchanged"
        )
        assert (
            api.get("/api/v1/revisions/v/structure").json()["evidence"][0]["paragraph_id"]
            == "chunk"
        )
        assert api.get("/api/v1/health").json()["schema_version"] == SCHEMA_HEAD
    (backup,) = (tmp_path / "backups").glob("*.sqlite3")
    with sqlite3.connect(backup) as db:
        assert db.execute("select version_num from alembic_version").fetchone()[0] == "0004"
        assert db.execute("select text from chunks").fetchone()[0] == "Old source stays unchanged"


def test_provider_requires_explicit_configuration_and_dto_has_no_commands(monkeypatch):
    monkeypatch.delenv("RGS_MODEL_BASE_URL", raising=False)
    with pytest.raises(ValueError):
        ConfiguredProvider()
    data = batch("ev")
    data["sql"] = "DROP TABLE papers"
    with pytest.raises(ValueError):
        ExtractionBatch.model_validate(data)


def test_new_source_preserves_accepted_knowledge_and_old_anchor(seeded):
    api, engine, eid = seeded
    apply(engine, batch(eid), eid)
    knowledge = api.get("/api/v1/revisions/version/knowledge").json()
    claim = next(n for n in knowledge["items"] if n["kind"] == "claim")
    accepted = post(
        api,
        "/knowledge/reviews",
        {
            "node_id": claim["id"],
            "expected_revision": 1,
            "expected_graph_revision": knowledge["graph_revision"],
            "action": "accept",
            "reason": "Source checked",
        },
        "accept-before-update",
    ).json()
    with Session(engine) as session, session.begin():
        session.add(
            AttachmentRevision(
                id="new-version",
                paper_id="paper",
                sha256="d" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        session.flush()
        KnowledgeStore(session).source_version_added("paper", "new-version")
    detail = api.get(f"/api/v1/knowledge/nodes/{claim['id']}").json()
    assert detail["node"]["review_status"] == "accepted"
    assert detail["node"]["payload"] == accepted["payload"]
    assert detail["evidence"][0]["id"] == eid
    assert detail["node"]["document_version_id"] == "version"
    assert "new_document_version_available" in detail["node"]["issues"]


def test_invalid_human_revision_is_422_and_atomic(seeded):
    api, engine, eid = seeded
    apply(engine, batch(eid), eid)
    knowledge = api.get("/api/v1/revisions/version/knowledge").json()
    claim = next(n for n in knowledge["items"] if n["kind"] == "claim")
    response = post(
        api,
        "/knowledge/reviews",
        {
            "node_id": claim["id"],
            "expected_revision": 1,
            "expected_graph_revision": knowledge["graph_revision"],
            "action": "revise",
            "reason": "Invalid semantic payload",
            "payload": {**claim["payload"], "origin": "scientific_fact"},
        },
        "invalid-review-payload",
    )
    assert response.status_code == 422
    detail = api.get(f"/api/v1/knowledge/nodes/{claim['id']}").json()
    assert detail["node"] == claim and detail["reviews"] == []
