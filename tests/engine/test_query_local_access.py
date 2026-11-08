"""HTTP responses need local consent even when the frozen task has model-use consent."""

import copy
import json

import pytest
import test_knowledge
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.query_models import QueryAnswerVersion, QueryModelRun, QueryRun
from researchgraph.query_retrieval import retrieve
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_query_answers import OfflineProvider, configure, enqueue, run
from test_query_graph import production
from test_query_retrieval import notes, request, science_rows

seeded = test_knowledge.seeded
PREFIX = "/api/v1/projects/project/query"
PRIVATE_NOTE = "Private synthetic note about accuracy"
PRIVATE_ANSWER = "Private generated interpretation from the selected note."


@pytest.fixture
def note_query(seeded, tmp_path):
    api, engine, eid = seeded
    production(engine, eid)
    configure(engine)
    notes(engine, tmp_path)
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).query().set_note_grant("project", "root", True, True)
    body = request("accuracy", purpose="model", include_personal=True, source_kinds=["note"])
    response = api.post(
        PREFIX + "/prepare", json=body, headers={"Idempotency-Key": "note-local-access-prepare"}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert PRIVATE_NOTE in response.text
    with Session(engine) as session:
        scientific = science_rows(session)
    return api, engine, body, result, scientific


def revoke_local(engine):
    with Session(engine) as session, session.begin():
        changed = KnowledgeStore(session).query().set_note_grant("project", "root", False, True)
        assert changed["allow_model"] and not changed["allow_local"]


def assert_redacted(response):
    assert response.status_code in {403, 409, 422}, response.text
    assert PRIVATE_NOTE not in response.text and PRIVATE_ANSWER not in response.text
    assert "reading.md" not in response.text


@pytest.mark.parametrize(
    "route,old_page_hash", [("/search", False), ("/search/page", False), ("/search/page", True)]
)
def test_model_purpose_search_and_all_result_pages_need_independent_local_note_consent(
    note_query, route, old_page_hash
):
    api, engine, body, _, before = note_query
    page = api.post(PREFIX + "/search/page", json={"request": body})
    assert page.status_code == 200 and PRIVATE_NOTE in page.text
    revoke_local(engine)
    payload = body if route == "/search" else {"request": body}
    if old_page_hash:
        payload["expected_result_hash"] = page.json()["result_hash"]
    assert_redacted(api.post(PREFIX + route, json=payload))
    with Session(engine) as session:
        # The scientific state remains untouched; purpose='model' still has its own grant.
        found = retrieve(
            session,
            "project",
            "accuracy",
            [],
            include_personal=True,
            purpose="model",
            source_kinds=["note"],
        )
        assert any(hit["text"] == PRIVATE_NOTE for hit in found["hits"])
        assert science_rows(session) == before


@pytest.mark.parametrize("action", ["idempotent_prepare", "get_run", "fresh_prepare"])
def test_existing_and_new_preparation_http_views_cannot_replay_local_revoked_note_text(
    note_query, action
):
    api, engine, body, prepared, before = note_query
    qid = prepared["query_id"]
    with Session(engine) as session:
        frozen = copy.deepcopy(session.get(QueryRun, qid).snapshot)
        fingerprint = session.get(QueryRun, qid).input_hash
        run_count = session.scalar(select(func.count()).select_from(QueryRun))
    revoke_local(engine)
    if action == "get_run":
        response = api.get(PREFIX + f"/runs/{qid}")
    else:
        key = "note-local-access-prepare" if action == "idempotent_prepare" else "new-local-denied"
        response = api.post(PREFIX + "/prepare", json=body, headers={"Idempotency-Key": key})
    assert_redacted(response)
    with Session(engine) as session:
        original = session.get(QueryRun, qid)
        assert original.input_hash == fingerprint and original.snapshot == frozen
        assert session.scalar(select(func.count()).select_from(QueryRun)) == run_count
        assert science_rows(session) == before


def test_answer_http_read_checks_local_permission_without_touching_frozen_answer_or_model_raw(
    note_query,
):
    api, engine, _, prepared, before = note_query
    qid = prepared["query_id"]

    def output(data):
        note = next(r for r in data["evidence_context"]["references"] if r["type"] == "note")
        return json.dumps(
            {
                "passages": [
                    {
                        "text": PRIVATE_ANSWER,
                        "attribution": "user_view",
                        "source_refs": [note["ref"]],
                        "limitations": [],
                    }
                ],
                "limitations": [],
            }
        )

    provider = OfflineProvider(engine, output=output)
    run(engine, enqueue(engine, qid), provider)
    assert provider.calls == 1
    allowed = api.get(PREFIX + f"/runs/{qid}/answer")
    assert allowed.status_code == 200 and PRIVATE_ANSWER in allowed.text
    with Session(engine) as session:
        query = session.get(QueryRun, qid)
        frozen_query, fingerprint = copy.deepcopy(query.snapshot), query.input_hash
        answer = session.scalar(
            select(QueryAnswerVersion).where(QueryAnswerVersion.query_run_id == qid)
        )
        frozen_answer = copy.deepcopy(answer.data)
        model = session.get(QueryModelRun, answer.model_run_id)
        raw, parameters = model.raw_output, copy.deepcopy(model.parameters)
    revoke_local(engine)
    assert_redacted(api.get(PREFIX + f"/runs/{qid}/answer"))
    # Reading twice cannot spend a new model slot or normalize/rewrite any original data.
    assert_redacted(api.get(PREFIX + f"/runs/{qid}/answer"))
    with Session(engine) as session:
        query = session.get(QueryRun, qid)
        answer = session.scalar(
            select(QueryAnswerVersion).where(QueryAnswerVersion.query_run_id == qid)
        )
        model = session.get(QueryModelRun, answer.model_run_id)
        assert query.input_hash == fingerprint and query.snapshot == frozen_query
        assert answer.data == frozen_answer and model.raw_output == raw
        assert model.parameters == parameters
        assert len(list(session.scalars(select(QueryModelRun)))) == 1
        assert science_rows(session) == before
    assert provider.calls == 1
