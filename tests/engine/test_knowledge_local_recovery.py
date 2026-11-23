"""Anonymous relationship failures recover only through reviewed, fully revalidated isolation."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import researchgraph.knowledge_workflow_api as workflow_api
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from researchgraph.core import KnowledgeError, digest, text_hash
from researchgraph.knowledge_connection_models import KnowledgeAnalysisEvent
from researchgraph.knowledge_diagnostics import project_knowledge_diagnostic
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.knowledge_library import publish_version
from researchgraph.knowledge_library_models import LibraryPaper, PaperKnowledgeVersion
from researchgraph.knowledge_sources import build_knowledge_sources
from researchgraph.knowledge_tasks import (
    local_recovery_preview,
    recover_knowledge_locally,
    run_knowledge_extract,
    validate_local_recovery_version,
)
from researchgraph.knowledge_workflow_api import register_knowledge_workflow_api
from researchgraph.model_document_models import LlmDocumentSegment
from researchgraph.models import Job
from researchgraph.paper_knowledge import (
    LEGACY_PROMPT_VERSION,
    PREVIOUS_PROMPT_VERSION,
    PROMPT_VERSION,
    KnowledgeGraph,
    knowledge_contract,
    knowledge_model_input,
    knowledge_relation_issues,
    knowledge_relation_rules,
    validate_knowledge_response,
)
from researchgraph.paper_overview_contracts import RELATION_ENDPOINTS
from researchgraph.storage import read_session
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_knowledge_extraction import FixtureProvider, draft, model_fixture, queued, run_record


def relationship_response(manifest):
    response = draft(manifest)
    template = response["graph"]["nodes"][0]
    kinds = [
        "RESEARCH_QUESTION",
        *(["METHOD"] * 4),
        *(["CONCEPT"] * 5),
        *(["FINDING"] * 4),
        *(["CONTRIBUTION"] * 5),
    ]
    response["graph"]["nodes"] = [
        {
            **copy.deepcopy(template),
            "id": f"n{i}",
            "type": kind,
            "label_zh": f"合成知识{i}",
            "label_en": f"Synthetic {i}",
        }
        for i, kind in enumerate(kinds, 1)
    ]
    valid = [
        ("INVESTIGATES", 1, 6),
        ("USES", 1, 2),
        ("ANALYZES", 2, 6),
        ("ANALYZES", 3, 7),
        ("YIELDS", 2, 11),
        ("YIELDS", 3, 12),
        ("CONTRIBUTES_TO", 11, 15),
        ("CONTRIBUTES_TO", 12, 16),
        ("RELATED_TO", 6, 15),
    ]
    invalid = [
        ("USES", 2, 6),
        ("USES", 3, 7),
        ("USES", 4, 8),
        ("ANALYZES", 1, 3),
        ("ANALYZES", 11, 7),
        ("YIELDS", 6, 11),
        ("YIELDS", 7, 12),
        ("CONTRIBUTES_TO", 2, 15),
        ("CONTRIBUTES_TO", 3, 16),
        ("INVESTIGATES", 6, 1),
        ("RELATED_TO", 1, 2),
    ]
    response["graph"]["edges"] = [
        {
            "id": f"e{i}",
            "source": f"n{source}",
            "target": f"n{target}",
            "type": kind,
            "basis": "EXPLICIT",
            "source_refs": copy.deepcopy(template["source_refs"]),
        }
        for i, (kind, source, target) in enumerate([*valid, *invalid], 1)
    ]
    return response


def failed_relationship_run(tmp_path, mutation=None):
    values = model_fixture(tmp_path)
    with Session(values[0]) as db:
        manifest = build_knowledge_sources(db, values[1], "model_parse", values[2])
    response = relationship_response(manifest)
    if mutation:
        mutation(response)
    job_id = queued(values)
    with Session(values[0]) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
        )
        run.raw_response = json.dumps(response, ensure_ascii=False)
        run.status, run.error_code, run.request_sent = (
            "failed",
            "KNOWLEDGE_RESPONSE_SCHEMA_INVALID",
            True,
        )
        run.usage_json = {"calls": 1, "usage_source": "unknown"}
        run.request_metadata = {
            "response_complete": True,
            "knowledge_diagnostic": {
                "version": "knowledge-diagnostic-1",
                "code": "KNOWLEDGE_RESPONSE_SCHEMA_INVALID",
                "issues": [{"path": "graph", "code": "value_error", "message": "old generic"}],
            },
        }
        job = db.get(Job, job_id)
        job.status, job.stage, job.error = "failed", "failed", "KNOWLEDGE_RESPONSE_SCHEMA_INVALID"
        identity = run.id
    return values, job_id, identity


def client_for(engine, tmp_path):
    app = FastAPI()
    register_knowledge_workflow_api(app, lambda: engine, tmp_path)
    return TestClient(app)


def test_v1_prompt_and_schema_are_identical_to_frozen_baseline_and_v2_rules_match_validator():
    legacy = knowledge_contract(LEGACY_PROMPT_VERSION)
    assert (
        digest(legacy["prompt"])
        == "eca50074b825225ecda19015c15bdafc6fc885b494e5053801191c2755a7cd5d"
    )
    assert (
        digest(legacy["schema"])
        == "856b4bd4b64c2bf0acdad5f17fe5dea735165af4e9165dda919e518a24506659"
    )
    assert "description" not in legacy["schema"]["$defs"]["KnowledgeEdge"]
    current = knowledge_contract(PREVIOUS_PROMPT_VERSION)
    assert current["prompt_version"] == PREVIOUS_PROMPT_VERSION != LEGACY_PROMPT_VERSION
    for kind, pair in RELATION_ENDPOINTS.items():
        assert f"{kind}: {pair[0]} -> {pair[1]}" in current["prompt"]
        assert {
            "type": kind,
            "source_type": pair[0],
            "target_type": pair[1],
            "directional": True,
        } in current["relation_rules"]
    assert "RELATED_TO" in current["schema"]["$defs"]["KnowledgeEdge"]["description"]


def test_generated_matrix_and_issue_collector_agree_with_shared_validator_for_all_pairs(tmp_path):
    values = model_fixture(tmp_path)
    with Session(values[0]) as db:
        manifest = build_knowledge_sources(db, values[1], "model_parse", values[2])
    template = draft(manifest)
    kinds = ["RESEARCH_QUESTION", "CONCEPT", "METHOD", "CONTRIBUTION", "FINDING"]
    for source_type in kinds:
        for target_type in kinds:
            for relation in [*RELATION_ENDPOINTS, "RELATED_TO"]:
                response = copy.deepcopy(template)
                source = response["graph"]["nodes"][0]
                source["type"] = source_type
                target = {
                    **copy.deepcopy(source),
                    "id": "n2",
                    "type": target_type,
                    "label_zh": "另一知识",
                }
                response["graph"]["nodes"] = [source, target]
                response["graph"]["edges"] = [
                    {
                        "id": "e1",
                        "source": "n1",
                        "target": "n2",
                        "type": relation,
                        "basis": "EXPLICIT",
                        "source_refs": copy.deepcopy(source["source_refs"]),
                    }
                ]
                try:
                    KnowledgeGraph.model_validate(response["graph"], strict=True)
                    valid = True
                except ValidationError:
                    valid = False
                assert bool(knowledge_relation_issues(json.dumps(response))) is not valid


def test_old_generic_schema_diagnostic_projects_eleven_indexed_reasons_readonly(tmp_path):
    values, job_id, run_id = failed_relationship_run(tmp_path)
    with read_session(values[0]) as db:
        diagnostic = project_knowledge_diagnostic(db, db.get(Job, job_id), None)[
            "knowledge_diagnostic"
        ]
        preview = local_recovery_preview(db, db.get(KnowledgeExtractionRun, run_id))
    assert diagnostic["issue_count"] == 11 and len(diagnostic["issues"]) == 8
    assert diagnostic["issues"][0]["path"] == "graph.edges[9].type"
    assert "USES" in diagnostic["issues"][0]["message"]
    assert "RESEARCH_QUESTION" in diagnostic["issues"][0]["message"]
    assert preview["available"] and len(preview["excluded_edges"]) == 11
    assert [
        preview[key] for key in ("original_nodes", "original_edges", "kept_nodes", "kept_edges")
    ] == [19, 20, 19, 9]
    _, run = run_record(values[0], job_id)
    assert run.request_metadata["knowledge_diagnostic"]["issues"][0]["path"] == "graph"
    with Session(values[0]) as db:
        assert db.query(PaperKnowledgeVersion).count() == 0


def test_preview_then_publish_keeps_failed_raw_and_marks_one_grounded_partial_without_auto_analysis(
    tmp_path,
):
    values, job_id, run_id = failed_relationship_run(tmp_path)
    _, before = run_record(values[0], job_id)
    client = client_for(values[0], tmp_path)
    path = f"/api/v1/knowledge/runs/{run_id}/local-recovery"
    preview = client.get(path).json()
    assert preview["available"]
    assert client.get("/api/v1/knowledge/runs").json()["items"][0]["local_recovery"] == preview
    response = client.post(
        path,
        json={"preview_fingerprint": preview["preview_fingerprint"]},
        headers={"Idempotency-Key": "recover-one"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    job, after = run_record(values[0], job_id)
    assert job.status == after.status == "failed" and after.error_code == before.error_code
    assert after.raw_response == before.raw_response and after.request_sent == before.request_sent
    assert after.usage_json == before.usage_json and after.version_id is None
    with Session(values[0]) as db:
        version = db.get(PaperKnowledgeVersion, result["version_id"])
        assert version.evidence_status == "grounded"
        assert len(version.content_json["graph"]["nodes"]) == 20
        assert len(version.content_json["graph"]["edges"]) == 28
        assert version.content_json["coverage"]["status"] == "partial"
        assert version.content_json["coverage"]["local_recovery"][
            "original_raw_sha256"
        ] == text_hash(before.raw_response)
        validate_local_recovery_version(db, version)
        assert db.query(KnowledgeAnalysisEvent).count() == 0
        assert db.query(PaperKnowledgeVersion).count() == 1
    assert client.get(path).json()["published_version_id"] == result["version_id"]


def test_runs_only_revalidates_local_recovery_for_failed_items_on_requested_page(
    tmp_path, monkeypatch
):
    values, _, _ = failed_relationship_run(tmp_path)
    preview_calls = []

    def preview_spy(db, run):
        preview_calls.append(run.id)
        return {"available": False}

    monkeypatch.setattr(workflow_api, "local_recovery_preview", preview_spy)
    client = client_for(values[0], tmp_path)

    second_page = client.get("/api/v1/knowledge/runs?offset=1&limit=1").json()
    assert second_page == {"items": [], "total": 1}
    assert preview_calls == []

    first_page = client.get("/api/v1/knowledge/runs?limit=1").json()
    assert first_page["total"] == 1
    assert first_page["items"][0]["local_recovery"] == {"available": False}
    assert len(preview_calls) == 1
    selected_job = first_page["items"][0]["job_id"]
    preview_calls.clear()
    missing = str(uuid4())
    assert client.get("/api/v1/knowledge/runs", params={"job_ids": missing}).json() == {
        "items": [],
        "total": 0,
    }
    assert preview_calls == []
    assert (
        client.get("/api/v1/knowledge/runs", params={"job_ids": f"{missing},{selected_job}"}).json()
        == first_page
    )
    assert len(preview_calls) == 1
    assert client.get("/api/v1/knowledge/runs", params={"job_ids": "invalid"}).status_code == 422


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["graph"]["nodes"][0]["source_refs"][0].update(quote="not in original"),
        lambda r: r["graph"]["edges"][0]["source_refs"][0].update(quote="not in original"),
        lambda r: r["paper_card"].update(method_summary=123),
        lambda r: r["graph"]["nodes"][1].update(id="n1"),
        lambda r: r["graph"]["edges"][-1].update(unknown_field="do not silently drop"),
    ],
)
def test_remaining_schema_or_source_problems_block_local_recovery(tmp_path, mutation):
    values, _, run_id = failed_relationship_run(tmp_path, mutation)
    client = client_for(values[0], tmp_path)
    path = f"/api/v1/knowledge/runs/{run_id}/local-recovery"
    assert client.get(path).json()["available"] is False
    response = client.post(
        path, json={"preview_fingerprint": "a" * 64}, headers={"Idempotency-Key": "bad-recovery"}
    )
    assert response.status_code == 409
    with Session(values[0]) as db:
        assert db.query(PaperKnowledgeVersion).count() == 0


def test_fingerprint_and_source_reread_prevent_unreviewed_or_stale_recovery(tmp_path):
    values, _, run_id = failed_relationship_run(tmp_path)
    client = client_for(values[0], tmp_path)
    path = f"/api/v1/knowledge/runs/{run_id}/local-recovery"
    preview = client.get(path).json()
    response = client.post(
        path, json={"preview_fingerprint": "a" * 64}, headers={"Idempotency-Key": "wrong-plan"}
    )
    assert response.status_code == 409 and "KNOWLEDGE_LOCAL_RECOVERY_STALE" in response.text
    with Session(values[0]) as db, db.begin():
        segment = db.scalar(
            select(LlmDocumentSegment).where(
                LlmDocumentSegment.parse_id == values[2], LlmDocumentSegment.chapter_ref == "c0"
            )
        )
        segment.text += " changed source"
    response = client.post(
        path,
        json={"preview_fingerprint": preview["preview_fingerprint"]},
        headers={"Idempotency-Key": "changed-source"},
    )
    assert response.status_code == 409 and "KNOWLEDGE_SOURCE_CHANGED" in response.text


def test_replay_revalidates_without_restoring_an_older_current_version(tmp_path):
    values, _, run_id = failed_relationship_run(tmp_path)
    with Session(values[0]) as db, db.begin():
        run = db.get(KnowledgeExtractionRun, run_id)
        fingerprint = local_recovery_preview(db, run)["preview_fingerprint"]
        first = recover_knowledge_locally(db, run, fingerprint)
        content = validate_knowledge_response(
            json.dumps(draft(run.source_manifest)), run.source_manifest
        )
        later = publish_version(
            db,
            paper_id=run.paper_id,
            source_kind=run.source_kind,
            source_id=run.source_id,
            source_fingerprint=run.source_manifest["source_fingerprint"],
            content_json=content,
            source_snapshot_json=run.source_manifest,
        )
        later_id = later.id
    with Session(values[0]) as db, db.begin():
        run = db.get(KnowledgeExtractionRun, run_id)
        second = recover_knowledge_locally(db, run, fingerprint)
        assert first["version_id"] == second["version_id"] != later_id
        assert db.get(LibraryPaper, run.library_paper_id).current_version_id == later_id
        assert db.query(PaperKnowledgeVersion).count() == 2


def test_recovered_version_revalidates_original_raw_and_does_not_trust_rehashed_tampering(tmp_path):
    values, _, run_id = failed_relationship_run(tmp_path)
    with Session(values[0]) as db, db.begin():
        run = db.get(KnowledgeExtractionRun, run_id)
        result = recover_knowledge_locally(
            db, run, local_recovery_preview(db, run)["preview_fingerprint"]
        )
        version_id = result["version_id"]
        run.raw_response += " "
    with Session(values[0]) as db, pytest.raises(KnowledgeError, match="审计"):
        validate_local_recovery_version(db, db.get(PaperKnowledgeVersion, version_id))


@pytest.mark.parametrize("version", [LEGACY_PROMPT_VERSION, PREVIOUS_PROMPT_VERSION])
def test_old_queued_contract_dispatches_and_reuses_its_cache_after_v3(tmp_path, version):
    values = model_fixture(tmp_path)
    job_id = queued(values)
    contract = knowledge_contract(version)
    with Session(values[0]) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
        )
        run.request_metadata = (
            {} if version == LEGACY_PROMPT_VERSION else {"request_contract": contract}
        )
        cache = digest(
            {
                "input": run.input_hash,
                "config": {k: v for k, v in run.model_snapshot.items() if k != "credential_ref"},
                "prompt": contract["prompt"],
                "schema": contract["schema"],
            }
        )
        run.cache_key = cache

    class LegacyProvider(FixtureProvider):
        async def complete(self, prompt, data, schema):
            self.calls += 1
            assert prompt == contract["prompt"] and schema == contract["schema"]
            assert ("relation_rules" in data) == (version == PREVIOUS_PROMPT_VERSION)
            return json.dumps(draft(data))

    provider = LegacyProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    job, run = run_record(values[0], job_id)
    assert job.status == "succeeded" and run.cache_key == cache and provider.calls == 1
    with Session(values[0]) as db:
        assert db.get(PaperKnowledgeVersion, run.version_id).prompt_version == version
    assert queued(values) == job_id


def test_new_queue_freezes_new_rules_and_detects_contract_mutation_before_network(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)
    with Session(values[0]) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
        )
        contract = run.request_metadata["request_contract"]
        assert contract["prompt_version"] == PROMPT_VERSION
        assert contract["relation_rules"] == knowledge_relation_rules()
        assert (
            knowledge_model_input(run.source_manifest)["relation_rules"]
            == contract["relation_rules"]
        )
        changed = copy.deepcopy(run.request_metadata)
        changed["request_contract"]["prompt"] = "tampered"
        run.request_metadata = changed
    provider = FixtureProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    _, run = run_record(values[0], job_id)
    assert run.error_code == "KNOWLEDGE_CONTEXT_CHANGED" and provider.calls == 0


def _failed_quote_run(tmp_path, *, edge_only=False, unknown_source=False):
    values = model_fixture(tmp_path)
    job_id = queued(values)
    with Session(values[0]) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
        )
        response = relationship_response(run.source_manifest)
        response["graph"]["edges"] = response["graph"]["edges"][:9]
        if edge_only:
            response["graph"]["edges"][0]["source_refs"][0]["occurrence_index"] = 99
        else:
            response["graph"]["nodes"][15]["source_refs"][0]["quote"] = run.source_manifest[
                "sources"
            ][1]["text"]
        if unknown_source:
            response["graph"]["nodes"][16]["source_refs"][0]["source_id"] = "s999"
        run.request_metadata = {"request_contract": knowledge_contract(PREVIOUS_PROMPT_VERSION)}
        run.raw_response = json.dumps(response, ensure_ascii=False)
        run.status, run.request_sent = "received", True
        run.usage_json = {"calls": 1, "usage_source": "unknown"}
        run_id = run.id
    provider = FixtureProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    job, run = run_record(values[0], job_id)
    assert job.status == run.status == "failed"
    assert run.error_code == "KNOWLEDGE_QUOTE_MISMATCH"
    assert provider.prepares == provider.calls == 0
    return values, job_id, run_id


def test_quote_recovery_rejects_wrong_source_and_preserves_verified_subgraph(tmp_path):
    values, job_id, run_id = _failed_quote_run(tmp_path)
    _, before = run_record(values[0], job_id)
    client = client_for(values[0], tmp_path)
    path = f"/api/v1/knowledge/runs/{run_id}/local-recovery"
    preview = client.get(path).json()
    assert preview["available"] and preview["version"] == "knowledge-local-recovery-2"
    assert (preview["original_nodes"], preview["kept_nodes"]) == (19, 18)
    assert (preview["original_edges"], preview["kept_edges"]) == (9, 8)
    (excluded_node,) = preview["excluded_nodes"]
    assert excluded_node["path"] == "graph.nodes[15].source_refs[0].quote"
    assert preview["excluded_edges"][0]["code"] == "depends_on_excluded_node"
    with Session(values[0]) as db:
        assert db.query(PaperKnowledgeVersion).count() == 0
    body = {"preview_fingerprint": preview["preview_fingerprint"]}
    headers = {"Idempotency-Key": "recover-exact-quotes"}
    saved = client.post(path, json=body, headers=headers)
    assert saved.status_code == 200, saved.text
    version_id = saved.json()["version_id"]
    assert client.post(path, json=body, headers=headers).json()["version_id"] == version_id
    job, after = run_record(values[0], job_id)
    assert job.status == after.status == before.status == "failed"
    assert after.raw_response == before.raw_response and after.usage_json == before.usage_json
    assert after.error_code == before.error_code and after.request_sent == before.request_sent
    with Session(values[0]) as db:
        version = db.get(PaperKnowledgeVersion, version_id)
        assert version.prompt_version == PREVIOUS_PROMPT_VERSION
        assert version.content_json["coverage"]["local_recovery"]["excluded_node_indices"] == [15]
        assert not any(version.content_json["paper_card"].values())
        assert db.query(PaperKnowledgeVersion).count() == 1
        assert db.query(KnowledgeAnalysisEvent).count() == 0
        assert db.get(LibraryPaper, after.library_paper_id).current_version_id == version_id
        validate_local_recovery_version(db, version)


def test_quote_recovery_isolates_edge_and_keeps_existing_current_version(tmp_path):
    values, _, run_id = _failed_quote_run(tmp_path, edge_only=True)
    with Session(values[0]) as db, db.begin():
        run = db.get(KnowledgeExtractionRun, run_id)
        current = publish_version(
            db,
            paper_id=run.paper_id,
            source_kind=run.source_kind,
            source_id=run.source_id,
            source_fingerprint=run.source_manifest["source_fingerprint"],
            content_json=validate_knowledge_response(
                json.dumps(draft(run.source_manifest)), run.source_manifest
            ),
            source_snapshot_json=run.source_manifest,
        )
        preview = local_recovery_preview(db, run)
        assert preview["excluded_nodes"] == [] and preview["kept_nodes"] == 19
        assert preview["excluded_edges"][0]["code"] == "quote_mismatch"
        recovered = recover_knowledge_locally(db, run, preview["preview_fingerprint"])
        assert recovered["version_id"] != current.id
        assert db.get(LibraryPaper, current.library_paper_id).current_version_id == current.id


def test_quote_recovery_refuses_an_additional_unknown_source(tmp_path):
    values, _, run_id = _failed_quote_run(tmp_path, unknown_source=True)
    with read_session(values[0]) as db:
        preview = local_recovery_preview(db, db.get(KnowledgeExtractionRun, run_id))
        assert preview["available"] is False
        assert preview["blocking_diagnostic"]["code"] == "KNOWLEDGE_SOURCE_REF_INVALID"
