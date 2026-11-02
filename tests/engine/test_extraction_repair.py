"""Regression for a real provider's dangling local_ref, using synthetic sources."""

import json

import pytest
from pydantic import ValidationError
from researchgraph import unified_extraction
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.providers import MockProvider
from researchgraph.unified_contracts import KnowledgeExtractionBatch
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_extraction_refinement import document
from test_ingest import queue, wait_job


def test_old_failure_reuses_response_repairs_once_and_resumes_seven_batches(tmp_path, monkeypatch):
    document(tmp_path / "paper.pdf", 7)
    real_plan = unified_extraction.plan_sections
    monkeypatch.setattr(
        unified_extraction, "plan_sections", lambda spans, **_: real_plan(spans, legacy=True)
    )
    calls = []
    raw_outputs = []

    class TypoProvider(MockProvider):
        async def complete(self, prompt, data, schema):
            calls.append(schema["title"])
            if schema["title"] == "LocalLinkRepair":
                return json.dumps(
                    {
                        "repairs": [
                            {"link_index": 0, "source_local_ref": "cl0", "target_local_ref": "m0"}
                        ]
                    }
                )
            raw = await super().complete(prompt, data, schema)
            if len(calls) == 2:
                value = json.loads(raw)
                value["links"][0]["source_local_ref"] = "claim_typo_missing"
                raw = json.dumps(value)
            raw_outputs.append(raw)
            return raw

    provider = TypoProvider()
    monkeypatch.setattr(unified_extraction, "provider_for", lambda *_: provider)
    real_validate = unified_extraction.validate_or_repair

    async def old_validate(engine, job_id, provider, run_id, raw, data, manifest):
        return run_id, KnowledgeExtractionBatch.model_validate_json(raw)

    monkeypatch.setattr(unified_extraction, "validate_or_repair", old_validate)
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Repair regression"}).json()["id"]
        imported = wait_job(api, queue(api, project, tmp_path / "paper.pdf", "repair-import"))
        body = {"document_version_id": imported["result"]["revision_id"], "pipeline": "unified-v3"}
        failed = wait_job(api, post(api, "/knowledge/extract", body, "repair-extract").json())
        assert failed["status"] == "failed" and failed["result"]["completed_batches"] == "1", failed
        assert "links[0].source_local_ref" in failed["error"]
        assert "claim_typo_missing" in failed["error"]
        with Session(api.app.state.engine) as session:
            old_nodes = {n.id: n.payload for n in session.scalars(select(KnowledgeNode))}
        monkeypatch.setattr(unified_extraction, "validate_or_repair", real_validate)
        resumed = wait_job(api, post(api, f"/jobs/{failed['id']}/retry", key="repair-retry").json())
        assert resumed["status"] == "succeeded", resumed
        assert resumed["result"]["completed_batches"] == "7"
        assert (
            calls
            == ["KnowledgeExtractionBatch"] * 2
            + ["LocalLinkRepair"]
            + ["KnowledgeExtractionBatch"] * 5
        )
        with Session(api.app.state.engine) as session:
            runs = list(session.scalars(select(ModelRun).where(ModelRun.job_id == failed["id"])))
            invalid = next(r for r in runs if r.status == "validation_failed")
            repair = next(r for r in runs if r.prompt_name == "P02_local_link_repair")
            assert invalid.raw_output == raw_outputs[1]
            assert repair.status == "succeeded"
            assert repair.parameters["input_manifest"]["repair_of_run_id"] == invalid.id
            for node_id, original in old_nodes.items():
                assert session.get(KnowledgeNode, node_id).payload == original
        repeat = wait_job(api, post(api, "/knowledge/extract", body, "repair-repeat").json())
        assert repeat["status"] == "succeeded" and len(calls) == 8


@pytest.mark.parametrize(
    "bad",
    ["invalid_json", "new_ref", "changed_valid", "decline", "unknown_evidence", "wrong_version"],
)
def test_repair_cannot_invent_or_rewrite_and_retries_have_no_extra_calls(
    tmp_path, monkeypatch, bad
):
    document(tmp_path / "paper.pdf", 1)
    calls = []

    class InvalidRepair(MockProvider):
        async def complete(self, prompt, data, schema):
            calls.append(schema["title"])
            if schema["title"] == "LocalLinkRepair":
                if bad == "invalid_json":
                    return "{"
                if bad == "decline":
                    return '{"repairs":[]}'
                return json.dumps(
                    {
                        "repairs": [
                            {
                                "link_index": 0,
                                "source_local_ref": "invented" if bad == "new_ref" else "cl0",
                                "target_local_ref": "c0" if bad == "changed_valid" else "m0",
                            }
                        ]
                    }
                )
            value = json.loads(await super().complete(prompt, data, schema))
            value["links"][0]["source_local_ref"] = "missing"
            if bad == "unknown_evidence":
                value["items"][0]["evidence_ids"] = ["ev9999"]
            if bad == "wrong_version":
                value["document_version_id"] = "another-paper"
            return json.dumps(value)

    monkeypatch.setattr(unified_extraction, "provider_for", lambda *_: InvalidRepair())
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Restricted repair"}).json()["id"]
        imported = wait_job(api, queue(api, project, tmp_path / "paper.pdf", "restricted-import"))
        job = wait_job(
            api,
            post(
                api,
                "/knowledge/extract",
                {
                    "document_version_id": imported["result"]["revision_id"],
                    "pipeline": "unified-v3",
                },
                "restricted-extract",
            ).json(),
        )
        assert job["status"] == "failed", job
        expected_calls = 1 if bad in {"unknown_evidence", "wrong_version"} else 2
        assert len(calls) == expected_calls
        retry = wait_job(api, post(api, f"/jobs/{job['id']}/retry", key="restricted-retry").json())
        assert retry["status"] == "failed" and len(calls) == expected_calls
        with Session(api.app.state.engine) as session:
            assert not list(session.scalars(select(KnowledgeNode)))


def test_validation_error_excludes_private_input():
    from researchgraph.extraction_repair import validation_message

    with pytest.raises(ValidationError) as caught:
        KnowledgeExtractionBatch.model_validate({"document_version_id": "private text"})
    assert "private text" not in validation_message(caught.value)
