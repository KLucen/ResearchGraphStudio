"""P4 HTTP integration on isolated SQLite with workers disabled and offline provider injection."""

import asyncio
import base64
import json

import pytest
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.models import AttachmentRevision, Chunk, Job, Paper, Project, now
from researchgraph.providers import ProviderError
from researchgraph.query_answers import execute
from researchgraph.query_models import QueryAnswerVersion, QueryModelRun, QueryRun
from researchgraph.query_saved_models import QuerySavedKnowledge
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_query_answers import OfflineProvider, configure, run
from test_query_retrieval import science_rows

PREFIX = "/api/v1/projects/project/query"


def seed(api):
    engine = api.app.state.engine
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Project(id="project", name="Synthetic API", description="", created_at=now()),
                Project(id="other", name="Other", description="", created_at=now()),
            ]
        )
        session.flush()
        session.add(
            Paper(id="paper", project_id="project", title="Synthetic API", created_at=now())
        )
        session.flush()
        session.add(
            AttachmentRevision(
                id="version",
                paper_id="paper",
                sha256="a" * 64,
                parser_version="synthetic-api",
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
                text="Accuracy reaches 81% under the reported 20 K condition.",
                bbox=[0.0, 0.0, 100.0, 80.0],
            )
        )
        session.flush()
        KnowledgeStore(session).ensure_document("version")
    configure(engine)
    return engine


@pytest.fixture
def api_setup(tmp_path):
    # test_engine.client explicitly sets create_app(start_worker=False).
    with client(tmp_path / "data") as api:
        yield api, seed(api)


def prepare(api, *, question="accuracy", key="query-prepare-api", **updates):
    body = {"project_id": "project", "question": question, "purpose": "model", **updates}
    response = api.post(PREFIX + "/prepare", json=body, headers={"Idempotency-Key": key})
    assert response.status_code == 200, response.text
    return response.json()


def generate(api, qid, key="query-generate-api", **updates):
    return api.post(
        PREFIX + f"/runs/{qid}/generate",
        json={"allow_network": True, **updates},
        headers={"Idempotency-Key": key},
    )


def command(prepared, answer, **changes):
    return {
        "source_query_id": prepared["query_id"],
        "answer_version_id": answer["answer_version_id"],
        "selected_passage_refs": [answer["passages"][0]["local_ref"]],
        "expected_input_hash": prepared["input_hash"],
        "kind": "synthesis",
        **changes,
    }


def save(api, body, key="query-save-api"):
    return api.post(
        PREFIX + f"/runs/{body['source_query_id']}/save",
        json=body,
        headers={"Idempotency-Key": key},
    )


def error(response, code, status=422):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code, response.text


def test_http_prepare_generate_execute_save_retrieve_and_restart(tmp_path):
    data = tmp_path / "data"
    with client(data) as api:
        engine = seed(api)
        with Session(engine) as session:
            before = science_rows(session)
        prepared = prepare(api)
        qid = prepared["query_id"]
        assert prepared["status"] == "prepared"
        assert prepared["snapshot"]["prompt"]["generation_enabled"] is False
        assert prepare(api) == prepared
        queued = generate(api, qid)
        assert queued.status_code == 202, queued.text
        jid = queued.json()["id"]
        assert queued.json()["status"] == "queued"
        pending = api.get(PREFIX + f"/runs/{qid}/answer").json()
        assert pending["status"] == "queued" and pending["request_count"] == 0
        provider = OfflineProvider(engine)
        run(engine, jid, provider)
        answered = api.get(PREFIX + f"/runs/{qid}/answer")
        assert answered.status_code == 200, answered.text
        answer_view = answered.json()
        assert answer_view["status"] == "succeeded"
        assert answer_view["request_count"] == provider.calls == 1
        assert answer_view["model_runs"][0]["usage"]["total_tokens"] == 158
        assert answer_view["model_runs"][0]["cost_known"] is False
        repeated = generate(api, qid)
        assert repeated.status_code == 202, repeated.text
        assert repeated.json()["status"] == "succeeded"
        with Session(engine) as session:
            assert science_rows(session) == before
            model = session.scalar(select(QueryModelRun))
            raw = model.raw_output
            assert model.parameters["raw_complete"] is True
        body = command(prepared, answer_view["answer"])
        saved_response = save(api, body)
        assert saved_response.status_code == 200, saved_response.text
        saved = saved_response.json()
        sid = saved["saved_id"]
        assert saved["content_state"] == "valid" and saved["file_state"] == "not_exported"
        assert save(api, body).json() == saved
        assert save(api, body, "after-disconnection").json() == saved
        assert api.get(PREFIX + "/saved").json()["items"] == [saved]
        assert api.get(PREFIX + f"/saved/{sid}").json() == saved
        error(api.get(f"/api/v1/projects/other/query/saved/{sid}"), "QUERY_SAVED_NOT_FOUND", 404)
        graph = api.get(PREFIX + "/derived-graph").json()
        assert sid in {n["id"] for n in graph["nodes"]}
        assert all(e["epistemic_status"] == "derived_reference" for e in graph["edges"])
        searched = api.post(
            PREFIX + "/search",
            json={"project_id": "project", "question": "实验条件", "source_kinds": ["synthesis"]},
        )
        assert searched.status_code == 200, searched.text
        assert searched.json()["hits"]
        assert provider.calls == 1
        with Session(engine) as session:
            after = science_rows(session)
            assert after.pop("graph_revisions") != before.pop("graph_revisions")
            assert after == before
            assert session.scalar(select(func.count()).select_from(QuerySavedKnowledge)) == 1
            assert session.scalar(select(func.count()).select_from(QueryAnswerVersion)) == 1
    with client(data) as reopened:
        assert reopened.get(PREFIX + f"/runs/{qid}/answer").json() == answer_view
        assert reopened.get(PREFIX + f"/saved/{sid}").json() == saved
        assert reopened.get(PREFIX + "/runs").json()["items"][0]["query_id"] == qid
        assert reopened.get(PREFIX + "/runs").json()["items"][0]["status"] == "succeeded"
        assert sid in {n["id"] for n in reopened.get(PREFIX + "/derived-graph").json()["nodes"]}
        with Session(reopened.app.state.engine) as session:
            assert session.scalar(select(QueryModelRun)).raw_output == raw


def test_http_explicit_purpose_network_scope_and_foreign_answers_are_rejected(api_setup):
    api, engine = api_setup
    local = prepare(api, purpose="local")
    error(generate(api, local["query_id"]), "QUERY_PURPOSE_REQUIRED")
    prepared = prepare(api, key="purpose-model-prepare")
    qid = prepared["query_id"]
    for body in ({}, {"allow_network": False}, {"allow_network": True, "provider": "mock"}):
        response = api.post(
            PREFIX + f"/runs/{qid}/generate",
            json=body,
            headers={"Idempotency-Key": "invalid-network-shape"},
        )
        error(response, "INVALID_INPUT")
    error(generate(api, "forged-query-id"), "QUERY_NOT_FOUND", 404)
    foreign = api.post(
        f"/api/v1/projects/other/query/runs/{qid}/generate",
        json={"allow_network": True},
        headers={"Idempotency-Key": "foreign-generate"},
    )
    error(foreign, "QUERY_NOT_FOUND", 404)
    assert api.get(f"/api/v1/projects/other/query/runs/{qid}/answer").status_code == 404
    scope = api.post(
        PREFIX + "/prepare",
        json={"project_id": "other", "question": "accuracy"},
        headers={"Idempotency-Key": "cross-project-prepare"},
    )
    error(scope, "QUERY_SCOPE_MISMATCH")
    jid = generate(api, qid).json()["id"]
    provider = OfflineProvider(engine)
    run(engine, jid, provider)
    answer = api.get(PREFIX + f"/runs/{qid}/answer").json()["answer"]
    body = command(prepared, answer)
    mismatched = api.post(
        PREFIX + "/runs/other-query/save", json=body, headers={"Idempotency-Key": "bad-save-route"}
    )
    error(mismatched, "QUERY_SCOPE_MISMATCH")
    foreign_save = api.post(
        f"/api/v1/projects/other/query/runs/{qid}/save",
        json=body,
        headers={"Idempotency-Key": "cross-project-save"},
    )
    error(foreign_save, "QUERY_SAVE_SCOPE_INVALID")
    error(save(api, {**body, "answer_version_id": "forged"}), "QUERY_SAVE_SCOPE_INVALID")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(QueryModelRun)) == 1
        assert session.scalar(select(func.count()).select_from(QuerySavedKnowledge)) == 0


def test_http_cancel_before_dispatch_and_general_retry_returns_actual_successor(api_setup):
    api, engine = api_setup
    prepared = prepare(api)
    qid = prepared["query_id"]
    jid = generate(api, qid).json()["id"]
    cancelled = post(api, f"/jobs/{jid}/cancel", key="query-cancel-before-send")
    assert cancelled.json()["status"] == "cancelled"
    provider = OfflineProvider(engine)
    # An already-cancelled worker entry must not reserve or send any request.
    asyncio.run(execute(engine, jid, testing_provider=provider))
    assert provider.calls == 0
    view = api.get(PREFIX + f"/runs/{qid}/answer").json()
    assert view["status"] == "cancelled" and view["request_count"] == 0
    retried = post(api, f"/jobs/{jid}/retry", key="query-general-retry")
    assert retried.status_code == 200, retried.text
    next_id = retried.json()["id"]
    assert next_id != jid and retried.json()["status"] == "queued"
    run(engine, next_id, provider)
    assert provider.calls == 1
    replay = post(api, f"/jobs/{jid}/retry", key="query-general-retry")
    assert replay.json()["id"] == next_id
    assert replay.json()["status"] == "succeeded"
    assert api.get(f"/api/v1/jobs/{jid}").json()["status"] == "cancelled"
    assert api.get(PREFIX + f"/runs/{qid}/answer").json()["request_count"] == 1


@pytest.mark.parametrize("second_success", [True, False])
def test_http_timeout_general_retry_consumes_only_explicit_second_slot(api_setup, second_success):
    api, engine = api_setup
    prepared = prepare(api)
    qid = prepared["query_id"]
    jid = generate(api, qid).json()["id"]
    first_provider = OfflineProvider(engine, error=ProviderError("timeout", "test timeout"))
    run(engine, jid, first_provider)
    first = api.get(PREFIX + f"/runs/{qid}/answer").json()
    assert first["status"] == "failed" and first["can_continue"] is True
    assert first["request_count"] == first_provider.calls == 1
    assert first["error_code"] == "QUERY_MODEL_TIMEOUT"
    repeated = generate(api, qid, "plain-generate-again")
    assert repeated.status_code == 202, repeated.text
    assert repeated.json()["id"] == jid
    retry = post(api, f"/jobs/{jid}/retry", key="explicit-query-second-slot")
    assert retry.status_code == 200, retry.text
    successor = retry.json()["id"]
    assert successor != jid
    provider = OfflineProvider(
        engine, error=None if second_success else ProviderError("timeout", "second timeout")
    )
    run(engine, successor, provider)
    final = api.get(PREFIX + f"/runs/{qid}/answer").json()
    assert final["request_count"] == 2 and provider.calls == 1
    assert final["can_continue"] is False
    assert final["status"] == ("succeeded" if second_success else "failed")
    replay = post(api, f"/jobs/{jid}/retry", key="explicit-query-second-slot")
    assert replay.json()["id"] == successor
    assert replay.json()["status"] == final["status"]
    if not second_success:
        error(
            post(api, f"/jobs/{jid}/retry", key="third-slot-forbidden"),
            "QUERY_REQUEST_LIMIT",
        )
    with Session(engine) as session:
        assert session.get(Job, jid).status == "failed"
        runs = list(session.scalars(select(QueryModelRun).order_by(QueryModelRun.created_at)))
        assert len(runs) == 2
        assert [r.parameters["dispatch"]["sequence"] for r in runs] == [1, 2]
        assert all(r.parameters["cost_known"] is False for r in runs)


def test_http_history_keyset_ties_new_insert_scope_and_invalid_cursors(api_setup):
    api, engine = api_setup
    old = [prepare(api, question=f"accuracy {i}", key=f"history-prepare-{i}") for i in range(4)]
    old_ids = {q["query_id"] for q in old}
    with Session(engine) as session, session.begin():
        for row in session.scalars(select(QueryRun)):
            row.created_at = "2026-11-04T01:00:00+00:00"
    first = api.get(PREFIX + "/runs?limit=2")
    assert first.status_code == 200, first.text
    first = first.json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    newest = prepare(api, question="accuracy newest", key="history-insert-after-page")
    with Session(engine) as session, session.begin():
        session.get(QueryRun, newest["query_id"]).created_at = "2026-11-04T02:00:00+00:00"
    second = api.get(PREFIX + "/runs", params={"limit": 2, "cursor": first["next_cursor"]})
    assert second.status_code == 200, second.text
    second = second.json()
    ids = [item["query_id"] for item in [*first["items"], *second["items"]]]
    assert len(ids) == len(set(ids)) == 4 and set(ids) == old_ids
    assert newest["query_id"] not in ids
    assert second["next_cursor"] is None
    assert api.get("/api/v1/projects/other/query/runs").json()["items"] == []
    for cursor in (
        "%broken",
        base64.urlsafe_b64encode(json.dumps(["only-one"]).encode()).decode(),
        base64.urlsafe_b64encode(json.dumps([False, "id"]).encode()).decode(),
        "x" * 501,
    ):
        error(api.get(PREFIX + "/runs", params={"cursor": cursor}), "QUERY_CURSOR_INVALID")
    for limit in (0, 51):
        error(api.get(PREFIX + "/runs", params={"limit": limit}), "INVALID_INPUT")


def test_http_invalid_raw_is_retained_and_only_explicit_continue_uses_second_slot(api_setup):
    api, engine = api_setup
    prepared = prepare(api)
    qid = prepared["query_id"]
    jid = generate(api, qid).json()["id"]
    invalid_raw = '{"passages":[],"limitations":["test"],"waiver":null}'
    provider = OfflineProvider(engine, output=invalid_raw)
    run(engine, jid, provider)
    failed = api.get(PREFIX + f"/runs/{qid}/answer").json()
    assert failed["status"] == "failed" and failed["answer"] is None
    assert failed["error_code"] == "QUERY_SCHEMA_INVALID" and failed["can_continue"] is True
    assert failed["request_count"] == provider.calls == 1
    retried = generate(api, qid, "continue-invalid-raw", continue_requested=True)
    assert retried.status_code == 202, retried.text
    successor = retried.json()["id"]
    assert successor != jid
    corrected = OfflineProvider(engine)
    run(engine, successor, corrected)
    result = api.get(PREFIX + f"/runs/{qid}/answer").json()
    assert result["status"] == "succeeded" and result["request_count"] == 2
    assert corrected.calls == 1 and provider.calls == 1
    with Session(engine) as session:
        runs = list(session.scalars(select(QueryModelRun).order_by(QueryModelRun.created_at)))
        assert len(runs) == 2 and runs[0].raw_output == invalid_raw
        assert runs[0].status == "validation_failed" and runs[1].status == "succeeded"
        assert session.scalar(select(func.count()).select_from(QueryAnswerVersion)) == 1


def test_http_cancel_during_request_keeps_consumed_slot_and_publishes_nothing(api_setup):
    api, engine = api_setup
    prepared = prepare(api)
    qid = prepared["query_id"]
    jid = generate(api, qid).json()["id"]

    def cancel():
        response = post(api, f"/jobs/{jid}/cancel", key="inflight-query-cancel")
        assert response.status_code == 200, response.text

    provider = OfflineProvider(engine, action=cancel)
    run(engine, jid, provider)
    result = api.get(PREFIX + f"/runs/{qid}/answer").json()
    assert result["status"] == "cancelled" and result["answer"] is None
    assert result["request_count"] == provider.calls == 1
    assert result["can_continue"] is True
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(QueryAnswerVersion)) == 0
        assert session.scalar(select(func.count()).select_from(QueryModelRun)) == 1
        assert session.scalar(select(func.count()).select_from(QuerySavedKnowledge)) == 0


def test_http_changed_source_refuses_dispatch_and_cached_preparation(api_setup):
    api, engine = api_setup
    prepared = prepare(api)
    qid = prepared["query_id"]
    with Session(engine) as session, session.begin():
        session.get(Chunk, "paragraph").text += " changed after prepare"
    error(generate(api, qid), "QUERY_CONTEXT_CHANGED")
    assert api.get(PREFIX + f"/runs/{qid}/answer").status_code == 422
    assert api.get(PREFIX + f"/runs/{qid}").status_code == 422
    replay = api.post(
        PREFIX + "/prepare",
        json={"project_id": "project", "question": "accuracy", "purpose": "model"},
        headers={"Idempotency-Key": "query-prepare-api"},
    )
    error(replay, "QUERY_CONTEXT_CHANGED")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(QueryModelRun)) == 0
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_http_note_permission_state_revocation_blocks_cached_answer_save_and_saved_graph(
    api_setup, tmp_path
):
    api, engine = api_setup
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "reading.md"
    original = b"Private synthetic accuracy interpretation."
    note.write_bytes(original)
    root_response = post(
        api,
        "/integrations/obsidian/roots",
        {"project_id": "project", "path": str(vault)},
        key="query-root-authorize",
    )
    assert root_response.status_code == 200, root_response.text
    root_id = root_response.json()["id"]
    root_url = f"/api/v1/integrations/obsidian/{root_id}"
    roots_url = "/api/v1/projects/project/note-roots"
    assert api.get(roots_url).json()[0]["query_permissions"] == {
        "allow_local": True,
        "allow_model": False,
    }
    grant = api.put(
        root_url + "/query-permissions",
        json={"allow_local": False, "allow_model": True},
        headers={"Idempotency-Key": "query-permission-model-only"},
    )
    assert grant.status_code == 200, grant.text
    assert api.get(roots_url).json()[0]["query_permissions"] == {
        "allow_local": False,
        "allow_model": True,
    }
    grant = api.put(
        root_url + "/query-permissions",
        json={"allow_local": True, "allow_model": True},
        headers={"Idempotency-Key": "query-permission-both"},
    )
    assert grant.status_code == 200
    assert (
        post(api, f"/integrations/obsidian/{root_id}/scan", key="query-note-scan").status_code
        == 200
    )
    prepared = prepare(api, include_personal=True, source_kinds=["note"])
    qid = prepared["query_id"]
    jid = generate(api, qid).json()["id"]
    provider = OfflineProvider(engine)
    run(engine, jid, provider)
    result = api.get(PREFIX + f"/runs/{qid}/answer").json()
    assert (
        result["status"] == "succeeded" and result["answer"]["knowledge_status"] == "mixed_sources"
    )
    body = command(prepared, result["answer"])
    saved = save(api, body)
    assert saved.status_code == 200, saved.text
    sid = saved.json()["saved_id"]
    assert api.get(PREFIX + "/saved").json()["items"] == []
    assert api.get(PREFIX + "/saved?include_personal=true").json()["items"]
    with Session(engine) as session:
        revision = KnowledgeStore(session).graph_revision("project")
    revoked = post(api, f"/integrations/obsidian/{root_id}/revoke", key="query-note-revoke")
    assert revoked.status_code == 200, revoked.text
    root = api.get(roots_url).json()[0]
    assert root["active"] is False and root["query_permissions"] == {
        "allow_local": False,
        "allow_model": False,
    }
    assert api.get(PREFIX + f"/runs/{qid}/answer").status_code == 422
    assert api.get(PREFIX + f"/runs/{qid}").status_code == 422
    cached = api.post(
        PREFIX + "/prepare",
        json={
            "project_id": "project",
            "question": "accuracy",
            "purpose": "model",
            "include_personal": True,
            "source_kinds": ["note"],
        },
        headers={"Idempotency-Key": "query-prepare-api"},
    )
    assert cached.status_code == 422
    assert save(api, body).status_code == 422
    assert save(api, body, "new-key-after-revocation").status_code == 422
    assert api.get(PREFIX + f"/saved/{sid}?include_personal=true").status_code == 422
    assert api.get(PREFIX + "/saved?include_personal=true").json()["items"] == []
    assert api.get(PREFIX + "/derived-graph?include_personal=true").json() == {
        "nodes": [],
        "edges": [],
    }
    with Session(engine) as session:
        assert KnowledgeStore(session).graph_revision("project") == revision
        assert session.scalar(select(func.count()).select_from(QuerySavedKnowledge)) == 1
    assert provider.calls == 1 and note.read_bytes() == original
