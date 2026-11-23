"""Failure types, safe details, and read-only projections use no external model calls."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from researchgraph.app import create_app
from researchgraph.core import KnowledgeError
from researchgraph.knowledge_connections import run_knowledge_connect
from researchgraph.knowledge_diagnostics import (
    diagnostic_for_raw,
    knowledge_diagnostic,
    project_knowledge_diagnostic,
)
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.knowledge_library_models import PaperKnowledgeVersion
from researchgraph.knowledge_sources import build_knowledge_sources
from researchgraph.knowledge_tasks import run_knowledge_extract
from researchgraph.models import Job, now
from researchgraph.paper_knowledge import knowledge_model_input, validate_knowledge_response
from researchgraph.providers import ProviderError
from researchgraph.storage import read_session
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_knowledge_connections import (
    ConnectionProvider,
    built_papers,
    connection_record,
    queue_connection,
)
from test_knowledge_extraction import (
    FixtureProvider,
    draft,
    model_fixture,
    queued,
    run_record,
    wire_draft,
)

SECRET = "PRIVATE_SENTINEL_sk_do_not_publish"


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("timeout", "transport"),
        ("network", "transport"),
        ("incomplete_stream", "transport"),
        ("rate_limit", "transport"),
        ("server", "transport"),
        ("client", "configuration"),
        ("empty_response", "protocol"),
        ("response", "protocol"),
        ("output_limit", "budget"),
        ("structured_output_unsupported", "configuration"),
        (SECRET, "unknown"),
    ],
)
def test_provider_errors_are_classified_before_their_valueerror_base(category, expected):
    result = knowledge_diagnostic(
        ProviderError(category, SECRET),
        request_sent=True,
        raw_available=False,
        provider_metadata={"http_status": 400, "unknown": SECRET, "partial_output": SECRET},
    )
    assert result["category"] == expected
    assert result["request_sent"] and not result["raw_available"]
    assert SECRET not in json.dumps(result) and "partial_output" not in result


def test_rate_limit_delay_survives_public_job_projection_without_body(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    provider = ConnectionProvider(ProviderError("rate_limit", SECRET, retry_after=92))
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    with read_session(engine) as db:
        job = db.get(Job, job_id)
        projected = project_knowledge_diagnostic(db, job, job.result)["knowledge_diagnostic"]
    assert provider.calls == 1 and projected["retry_after_seconds"] == 92
    assert "92 秒" in projected["action"] and SECRET not in json.dumps(projected)


def test_timeout_only_uses_known_phase_and_finite_numeric_metadata():
    result = knowledge_diagnostic(
        ProviderError("timeout", SECRET, timeout_phase="total"),
        request_sent=True,
        raw_available=False,
        provider_metadata={"total_timeout_seconds": 600, "phase": SECRET},
    )
    assert "600" in result["summary"] and "总时限" in result["summary"]
    assert SECRET not in json.dumps(result)
    for metadata in (
        {"timeout_phase": SECRET, "total_timeout_seconds": SECRET},
        {"timeout_phase": {"secret": SECRET}, "total_timeout_seconds": float("inf")},
    ):
        assert SECRET not in json.dumps(
            knowledge_diagnostic(
                TimeoutError(SECRET),
                request_sent=True,
                raw_available=False,
                provider_metadata=metadata,
            )
        )


def test_k2_transport_failure_keeps_actual_private_metadata_and_never_claims_format(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)

    class FailedProvider(FixtureProvider):
        async def complete(self, prompt, data, schema):
            self.calls += 1
            self.request_metadata = {
                "http_status": 401,
                "total_timeout_seconds": 60,
                "secret_field": SECRET,
            }
            self.partial_output = SECRET
            raise ProviderError("client", SECRET)

    provider = FailedProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    job, run = run_record(values[0], job_id)
    diagnostic = run.request_metadata["knowledge_diagnostic"]
    assert job.status == "failed" and run.error_code == "KNOWLEDGE_PROVIDER_CLIENT"
    assert provider.calls == 1 and run.request_sent and run.raw_response is None
    assert run.request_metadata["provider"]["secret_field"] == SECRET
    assert run.request_metadata["partial_output"] == SECRET
    assert diagnostic["category"] == "configuration" and not diagnostic["raw_available"]
    assert "HTTP 401" in diagnostic["summary"]
    with read_session(values[0]) as db:
        result = project_knowledge_diagnostic(db, db.get(Job, job_id), None)
    assert SECRET not in json.dumps(result) and "partial_output" not in json.dumps(result)
    assert result["knowledge_diagnostic"] == diagnostic


def test_k2_schema_issues_include_known_paths_and_hide_unknown_names_and_values(tmp_path):
    values = model_fixture(tmp_path)
    with Session(values[0]) as db:
        manifest = build_knowledge_sources(db, values[1], "model_parse", values[2])
    response = wire_draft(knowledge_model_input(manifest))
    node = response["graph"]["nodes"][0]
    node.pop("basis")
    node["type"] = SECRET
    node[SECRET] = SECRET
    provider = FixtureProvider(json.dumps(response))
    job_id = queued(values)
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    _, run = run_record(values[0], job_id)
    result = run.request_metadata["knowledge_diagnostic"]
    assert run.error_code == "KNOWLEDGE_RESPONSE_SCHEMA_INVALID"
    assert result["category"] == "schema" and result["raw_available"]
    assert {i["path"] for i in result["issues"]} == {
        "graph.nodes[0].type",
        "graph.nodes[0].basis",
        "graph.nodes[0]._extra_field",
    }
    assert SECRET in run.raw_response and SECRET not in json.dumps(result)
    assert manifest["sources"][0]["text"] not in json.dumps(result)


@pytest.mark.parametrize("raw", ['{"bad":', '{"x":1,"x":2}', '{"x":NaN}'])
def test_strict_json_failures_are_protocol_errors_without_raw_content(raw):
    try:
        validate_knowledge_response(raw, {})
    except ValueError as error:
        result = diagnostic_for_raw(error, raw, request_sent=True)
    assert result["code"] == "KNOWLEDGE_RESPONSE_JSON_INVALID"
    assert result["category"] == "protocol" and result["raw_available"]
    assert raw not in json.dumps(result)
    assert all(issue["path"] == "$" for issue in result["issues"])


def test_schema_issue_count_is_bounded_and_source_errors_have_specific_fixed_reasons(tmp_path):
    values = model_fixture(tmp_path)
    with Session(values[0]) as db:
        manifest = build_knowledge_sources(db, values[1], "model_parse", values[2])
    response = draft(manifest)
    response["graph"]["nodes"] *= 12
    for node in response["graph"]["nodes"]:
        node["type"] = SECRET
    try:
        validate_knowledge_response(json.dumps(response), manifest)
    except ValueError as error:
        result = diagnostic_for_raw(error, "{}", request_sent=True)
    assert len(result["issues"]) == 8 and result["issue_count"] == 12
    result = knowledge_diagnostic(
        KnowledgeError("KNOWLEDGE_QUOTE_MISMATCH", SECRET),
        request_sent=True,
        raw_available=True,
    )
    assert result["category"] == "source" and "引文" in result["summary"]
    assert SECRET not in json.dumps(result)


def test_legacy_gets_revalidate_saved_raw_without_mutation_or_disclosure(tmp_path):
    token = "k" * 40
    app = create_app(tmp_path / "knowledge", token, start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as api:
        values = model_fixture(tmp_path)
        job_id = queued(values)
        with Session(values[0]) as db, db.begin():
            run = db.scalar(
                select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
            )
            raw = json.dumps({"schema_version": "paper-knowledge-1", SECRET: SECRET})
            run.status, run.error_code, run.raw_response = (
                "failed",
                "KNOWLEDGE_RESPONSE_INVALID",
                raw,
            )
            run.request_sent = True
            run.request_metadata = {"provider": {"unknown_secret": SECRET}}
            job = db.get(Job, job_id)
            job.status, job.error, job.stage = "failed", "KNOWLEDGE_RESPONSE_INVALID", "failed"
            job.result = {"preserved": "existing"}
            project_id = job.project_id
            before = (
                run.status,
                run.error_code,
                run.raw_response,
                copy.deepcopy(run.request_metadata),
                job.status,
                job.error,
                copy.deepcopy(job.result),
            )
        detail = api.get(f"/api/v1/jobs/{job_id}")
        global_view = next(j for j in api.get("/api/v1/jobs").json() if j["id"] == job_id)
        project_view = next(
            j
            for j in api.get(f"/api/v1/projects/{project_id}/jobs").json()["items"]
            if j["id"] == job_id
        )
        assert detail.status_code == 200, detail.text
        for view in (detail.json(), global_view, project_view):
            assert view["result"]["preserved"] == "existing"
            diagnostic = view["result"]["knowledge_diagnostic"]
            assert diagnostic["code"] == "KNOWLEDGE_RESPONSE_SCHEMA_INVALID"
            assert diagnostic["raw_available"] and diagnostic["request_sent"]
            assert SECRET not in json.dumps(view)
        assert detail.json()["result"] == global_view["result"] == project_view["result"]
        with Session(values[0]) as db:
            run = db.scalar(
                select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
            )
            job = db.get(Job, job_id)
            after = (
                run.status,
                run.error_code,
                run.raw_response,
                run.request_metadata,
                job.status,
                job.error,
                job.result,
            )
            assert before == after and db.query(PaperKnowledgeVersion).count() == 0


def test_legacy_missing_raw_is_unknown_even_with_old_generic_format_code(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)
    with Session(values[0]) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
        )
        run.status, run.error_code, run.request_sent = "failed", "KNOWLEDGE_RESPONSE_INVALID", True
        job = db.get(Job, job_id)
        job.status, job.error = "failed", "KNOWLEDGE_RESPONSE_INVALID"
    with read_session(values[0]) as db:
        result = project_knowledge_diagnostic(db, db.get(Job, job_id), None)["knowledge_diagnostic"]
    assert result["category"] == "unknown" and not result["raw_available"]
    assert "未保留" in result["summary"] and "无法判定" in result["summary"]
    assert "费用未知" in result["summary"]
    assert run_record(values[0], job_id)[1].error_code == "KNOWLEDGE_RESPONSE_INVALID"


def test_k3_transport_partial_is_private_and_never_presented_as_complete_raw(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])

    class FailedProvider(ConnectionProvider):
        async def complete(self, prompt, data, schema):
            self.calls += 1
            self.partial_output = SECRET
            self.request_metadata = {"timeout_phase": "response_body", "secret": SECRET}
            raise ProviderError("incomplete_stream", SECRET)

    provider = FailedProvider()
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    job, run, requests, _ = connection_record(engine, job_id)
    assert job.status == "failed" and provider.calls == 1
    assert run.error_code == "KNOWLEDGE_PROVIDER_INCOMPLETE_STREAM"
    assert requests[0].raw_response == SECRET
    assert requests[0].usage_json["response_complete"] is False
    assert requests[0].usage_json["request_metadata"]["secret"] == SECRET
    with read_session(engine) as db:
        result = project_knowledge_diagnostic(db, db.get(Job, job_id), None)
    diagnostic = result["knowledge_diagnostic"]
    assert diagnostic["category"] == "transport" and not diagnostic["raw_available"]
    assert diagnostic["request_sent"] and SECRET not in json.dumps(result)


def test_orphan_connection_job_reports_missing_run_without_provider_call(tmp_path):
    values = model_fixture(tmp_path)
    job_id = str(uuid4())
    with Session(values[0]) as db, db.begin():
        db.add(
            Job(
                id=job_id,
                kind="knowledge_connect",
                status="queued",
                created_at=now(),
                updated_at=now(),
            )
        )
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(values[0], job_id, tmp_path, provider=provider))
    with Session(values[0]) as db:
        job = db.get(Job, job_id)
        assert job.status == "failed" and provider.calls == 0
        assert job.result["knowledge_diagnostic"]["code"] == "KNOWLEDGE_RUN_MISSING"


def test_saved_public_diagnostic_is_regenerated_from_safe_fields(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)
    provider = FixtureProvider(ProviderError("client", SECRET))
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    with Session(values[0]) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
        )
        run.request_metadata = {
            **run.request_metadata,
            "knowledge_diagnostic": {
                "version": "knowledge-diagnostic-1",
                "code": "KNOWLEDGE_PROVIDER_CLIENT",
                "summary": SECRET,
                "action": SECRET,
                "raw_response": SECRET,
                "issues": [{"path": SECRET, "code": SECRET, "message": SECRET}],
            },
        }
    with read_session(values[0]) as db:
        result = project_knowledge_diagnostic(db, db.get(Job, job_id), None)
    diagnostic = result["knowledge_diagnostic"]
    assert diagnostic["category"] == "configuration"
    assert SECRET not in json.dumps(diagnostic)
    assert all(issue["code"] == "invalid" for issue in diagnostic["issues"])


def test_k3_complete_schema_failure_retains_raw_and_surfaces_safe_details(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])

    class InvalidProvider(ConnectionProvider):
        async def complete(self, prompt, data, schema):
            self.calls += 1
            return json.dumps({"schema_version": "knowledge-connections-1", SECRET: SECRET})

    provider = InvalidProvider()
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    job, run, requests, _ = connection_record(engine, job_id)
    assert job.status == "failed" and provider.calls == 1
    assert run.error_code == "KNOWLEDGE_RESPONSE_SCHEMA_INVALID"
    assert SECRET in requests[0].raw_response
    assert requests[0].usage_json["response_complete"] is True
    with read_session(engine) as db:
        diagnostic = project_knowledge_diagnostic(db, db.get(Job, job_id), None)[
            "knowledge_diagnostic"
        ]
    assert diagnostic["raw_available"] and diagnostic["category"] == "schema"
    assert "relations" in {issue["path"] for issue in diagnostic["issues"]}
    assert SECRET not in json.dumps(diagnostic)
