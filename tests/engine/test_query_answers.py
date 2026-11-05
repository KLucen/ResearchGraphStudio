"""Q05 isolated P07 execution and failure recovery; no real provider or private files."""

import asyncio
import json
from threading import Event

import pytest
import test_knowledge
from researchgraph import query_answers as answers
from researchgraph.knowledge_models import AuthorizedRoot
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.model_settings import GlobalModelRole, ModelParameters, ModelProfile
from researchgraph.models import Chunk, Job, now
from researchgraph.providers import ProviderError
from researchgraph.query_answer_wire import (
    assert_prompt_contract,
    bind_answer,
    generated_rules,
    output_schema,
)
from researchgraph.query_models import QueryAnswerVersion, QueryModelRun, QueryRun
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_query_graph import production, second_paper
from test_query_retrieval import notes, request, science_rows

seeded = test_knowledge.seeded


def configure(engine):
    with Session(engine) as session, session.begin():
        session.add(
            ModelProfile(
                id="query-profile",
                project_id=None,
                name="Isolated test model",
                provider="compatible",
                base_url="https://isolated.example/v1",
                model="synthetic-p07",
                parameters=ModelParameters().model_dump(),
                credential_ref=None,
                secret_refs=[],
                active=True,
                updated_at=now(),
            )
        )
        session.flush()
        session.add(GlobalModelRole(role="reasoning", profile_id="query-profile"))


def prepare(api, *, question="accuracy", purpose="model", include_personal=False):
    response = api.post(
        "/api/v1/projects/project/query/prepare",
        json=request(question, purpose=purpose, include_personal=include_personal),
        headers={"Idempotency-Key": "prepare-answer-" + question + purpose},
    )
    assert response.status_code == 200, response.text
    return response.json()["query_id"]


def enqueue(engine, qid, key="answer-first", *, continuing=False):
    with Session(engine) as session, session.begin():
        return answers.enqueue(session, qid, "project", key, continue_requested=continuing).id


def run(engine, jid, provider, stop=None):
    with Session(engine) as session, session.begin():
        job = session.get(Job, jid)
        job.status = "running"
        job.attempt += 1
    asyncio.run(answers.execute(engine, jid, stop, testing_provider=provider))


def view(engine, qid):
    with Session(engine) as session:
        return answers.get_answer(session, "project", qid)


class OfflineProvider:
    """Explicit test injection, with a dispatch-count assertion at the I/O boundary."""

    name, model, total_timeout = "compatible", "synthetic-p07", 3

    def __init__(self, engine, *, output=None, action=None, error=None):
        self.engine, self.output, self.action, self.error = engine, output, action, error
        self.calls = 0
        self.usage = {"prompt_tokens": 121, "completion_tokens": 37, "total_tokens": 158}
        self.request_metadata = {"finish_reason": "stop"}
        self.partial_output = None

    async def complete(self, prompt, data, schema):
        self.calls += 1
        with Session(self.engine) as session:
            latest = session.scalar(select(QueryModelRun).order_by(QueryModelRun.created_at.desc()))
            assert latest is not None and latest.status == "running"
            assert latest.parameters["dispatch"]["policy"] == "persist-before-io-no-resend-1"
        assert_prompt_contract(prompt)
        context = data["evidence_context"]
        refs = [ref["ref"] for ref in context["references"]]
        assert schema == output_schema(refs)
        assert data["contract_rules"] == generated_rules(refs)
        if self.action:
            self.action()
        if self.error:
            raise self.error
        if self.output is not None:
            return self.output(data) if callable(self.output) else self.output
        direct = next(ref for ref in context["references"] if ref["type"] in {"chunk", "note"})
        return json.dumps(
            {
                "passages": [
                    {
                        "text": "在所述实验条件下，作者报告了性能改善。",
                        "attribution": "user_view"
                        if direct["type"] == "note"
                        else "model_synthesis",
                        "source_refs": [direct["ref"]],
                        "limitations": ["仅限所述条件"],
                    }
                ],
                "limitations": [],
            },
            ensure_ascii=False,
        )


@pytest.fixture
def prepared(seeded):
    api, engine, eid = seeded
    production(engine, eid)
    configure(engine)
    return api, engine, prepare(api)


def test_answer_executes_once_and_read_save_boundaries_revalidate(prepared):
    _, engine, qid = prepared
    with Session(engine) as session:
        before = science_rows(session)
    jid = enqueue(engine, qid)
    assert enqueue(engine, qid) == jid
    assert enqueue(engine, qid, "parallel-click") == jid
    provider = OfflineProvider(engine)
    run(engine, jid, provider)
    result = view(engine, qid)
    assert result.status == "succeeded" and result.answer.knowledge_status == "source_grounded"
    assert result.answer.passages[0].local_ref == "A00001"
    assert result.request_count == provider.calls == 1
    assert result.model_runs[0].usage["total_tokens"] == 158
    assert result.model_runs[0].finish_reason == "stop"
    assert result.model_runs[0].duration_seconds is not None
    assert result.model_runs[0].cost_known is False
    assert not result.can_continue
    with Session(engine) as session:
        assert science_rows(session) == before
        row = answers.validate_answer(session, "project", qid)
        assert row.data == result.answer.model_dump(mode="json")
        model = session.get(QueryModelRun, row.model_run_id)
        assert model.raw_output and model.parameters["raw_complete"]
        assert len(list(session.scalars(select(QueryAnswerVersion)))) == 1
    assert enqueue(engine, qid, "again", continuing=True) == jid
    with Session(engine) as session, session.begin():
        session.get(Chunk, "paragraph").text += " changed"
    with Session(engine) as session, pytest.raises(KnowledgeError):
        answers.validate_answer(session, "project", qid)


@pytest.mark.parametrize(
    "bad,code",
    [
        ("{broken", "QUERY_JSON_INVALID"),
        ('{"passages":[],"limitations":["x"],"limitations":["y"]}', "QUERY_JSON_INVALID"),
        ('{"passages":[],"limitations":[NaN]}', "QUERY_JSON_INVALID"),
        ('{"passages":[],"limitations":["x"],"waiver":null}', "QUERY_SCHEMA_INVALID"),
        (
            '{"passages":[{"text":"x","attribution":"model_synthesis","source_refs":'
            '["S99999"],"limitations":[]}],"limitations":[]}',
            "QUERY_REFERENCE_UNKNOWN",
        ),
        (
            '{"passages":[{"text":"x","attribution":"model_synthesis","source_refs":'
            '[],"limitations":[]}],"limitations":[]}',
            "QUERY_SCHEMA_INVALID",
        ),
        ('{"passages":[],"limitations":[]}', "QUERY_SCHEMA_INVALID"),
    ],
)
def test_invalid_output_is_retained_but_never_published_or_automatically_resent(
    prepared, bad, code
):
    _, engine, qid = prepared
    jid = enqueue(engine, qid)
    provider = OfflineProvider(engine, output=bad)
    run(engine, jid, provider)
    result = view(engine, qid)
    assert result.status == "failed" and result.error_code == code
    assert result.answer is None and provider.calls == 1
    with Session(engine) as session:
        model = session.scalar(select(QueryModelRun))
        assert model.raw_output == bad and model.status == "validation_failed"
    # Requeueing the same job without a new explicit continuation cannot charge again.
    run(engine, jid, provider)
    assert provider.calls == 1


def test_timeout_continuation_consumes_second_slot_and_hard_stops(prepared):
    _, engine, qid = prepared
    first = enqueue(engine, qid)
    provider = OfflineProvider(engine, error=ProviderError("timeout", "unsafe provider text"))
    run(engine, first, provider)
    result = view(engine, qid)
    assert result.can_continue and result.error_code == "QUERY_MODEL_TIMEOUT"
    assert "unsafe" not in result.error
    assert enqueue(engine, qid, "not-authorized-to-repeat") == first
    second = enqueue(engine, qid, "explicit-continue", continuing=True)
    assert second != first
    run(engine, second, provider)
    assert provider.calls == view(engine, qid).request_count == 2
    assert not view(engine, qid).can_continue
    with pytest.raises(KnowledgeError, match="上限"):
        enqueue(engine, qid, "third", continuing=True)
    with Session(engine) as session:
        assert session.get(Job, first).status == "failed"
        assert all(run.raw_output is None for run in session.scalars(select(QueryModelRun)))


def test_complete_received_raw_survives_crash_and_resumes_without_new_call(prepared, monkeypatch):
    _, engine, qid = prepared
    first = enqueue(engine, qid)
    provider = OfflineProvider(engine)
    original = answers._publish

    def crash(*args):
        raise RuntimeError("simulated stop after durable receive")

    monkeypatch.setattr(answers, "_publish", crash)
    run(engine, first, provider)
    with Session(engine) as session:
        saved = session.scalar(select(QueryModelRun))
        raw, finished_at = saved.raw_output, saved.finished_at
        assert saved.status == "received"
    monkeypatch.setattr(answers, "_publish", original)
    second = enqueue(engine, qid, "recover-raw", continuing=True)
    run(engine, second, provider)
    assert provider.calls == 1 and view(engine, qid).status == "succeeded"
    with Session(engine) as session:
        saved = session.scalar(select(QueryModelRun))
        assert saved.raw_output == raw and saved.finished_at == finished_at
        assert session.get(Job, first).status == "failed"


@pytest.mark.parametrize("change", ["raw", "manifest", "model", "prompt", "dispatch"])
def test_answer_lineage_tampering_is_rejected_without_another_call(prepared, change):
    _, engine, qid = prepared
    provider = OfflineProvider(engine)
    run(engine, enqueue(engine, qid), provider)
    with Session(engine) as session, session.begin():
        model = session.scalar(select(QueryModelRun))
        if change == "raw":
            model.raw_output += " "
        elif change == "manifest":
            model.manifest = {**model.manifest, "query_input_hash": "f" * 64}
        elif change == "model":
            model.model = "another-model"
        elif change == "prompt":
            model.prompt_hash = "0" * 64
        else:
            model.parameters = {**model.parameters, "dispatch": {"sequence": 2}}
    with pytest.raises(KnowledgeError):
        view(engine, qid)
    assert provider.calls == 1


def test_no_evidence_is_a_deterministic_insufficient_answer_without_model(seeded):
    api, engine, _ = seeded
    qid = prepare(api, question="unmatched_string_qwerty")
    provider = OfflineProvider(engine)
    run(engine, enqueue(engine, qid), provider)
    result = view(engine, qid)
    assert result.status == "insufficient" and result.answer.passages == []
    assert result.answer.limitations and provider.calls == result.request_count == 0
    with Session(engine) as session:
        assert answers.validate_answer(session, "project", qid).model_run_id is None


def test_model_purpose_and_scope_are_required_before_queueing(seeded):
    api, engine, _ = seeded
    qid = prepare(api, purpose="local")
    with pytest.raises(KnowledgeError) as exc:
        enqueue(engine, qid)
    assert exc.value.code == "QUERY_PURPOSE_REQUIRED"
    with Session(engine) as session, session.begin(), pytest.raises(KnowledgeError):
        answers.enqueue(session, qid, "other", "cross-project")


@pytest.mark.parametrize("when", ["queued", "during_call", "get"])
def test_note_revocation_blocks_queued_returned_and_cached_answers(seeded, tmp_path, when):
    api, engine, _ = seeded
    configure(engine)
    notes(engine, tmp_path)
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).query().set_note_grant("project", "root", True, True)
    qid = prepare(api, question="Private", include_personal=True)
    jid = enqueue(engine, qid)

    def revoke():
        with Session(engine) as session, session.begin():
            session.get(AuthorizedRoot, "root").active = False

    provider = OfflineProvider(engine, action=revoke if when == "during_call" else None)
    if when == "queued":
        revoke()
    run(engine, jid, provider)
    if when == "get":
        assert view(engine, qid).answer.passages[0].attribution == "user_view"
        revoke()
    with pytest.raises(KnowledgeError):
        view(engine, qid)
    with pytest.raises(KnowledgeError):
        enqueue(engine, qid, "after-revoke", continuing=True)
    assert provider.calls == (0 if when == "queued" else 1)
    if when == "during_call":
        with Session(engine) as session:
            model = session.scalar(select(QueryModelRun))
            assert model.status == "received" and model.error is None
            assert model.parameters["reuse_diagnostic"]["code"] == "QUERY_PERMISSION_CHANGED"
            assert session.scalar(select(QueryAnswerVersion)) is None


def test_cancellation_closes_inflight_task_and_cannot_publish(prepared):
    _, engine, qid = prepared
    jid = enqueue(engine, qid)
    stopped = Event()

    class HangingProvider(OfflineProvider):
        async def complete(self, prompt, data, schema):
            self.calls += 1
            stopped.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                self.closed = True
                raise

    provider = HangingProvider(engine)
    provider.closed = False
    run(engine, jid, provider, stopped)
    assert provider.closed and provider.calls == 1
    assert view(engine, qid).answer is None
    with Session(engine) as session:
        assert session.get(Job, jid).status == "cancelled"


def test_cross_paper_comparison_preserves_synthesis_attribution(seeded):
    api, engine, eid = seeded
    production(engine, eid)
    second_paper(engine)
    configure(engine)
    qid = prepare(api)

    def cross_output(data):
        chunks = [r for r in data["evidence_context"]["references"] if r["type"] == "chunk"]
        assert len({r["paper_id"] for r in chunks}) == 2
        return json.dumps(
            {
                "passages": [
                    {
                        "text": "两篇论文条件不同，不能仅比较同名指标。",
                        "attribution": "model_synthesis",
                        "source_refs": [r["ref"] for r in chunks],
                        "limitations": ["不作数值排序"],
                    }
                ],
                "limitations": [],
            }
        )

    run(engine, enqueue(engine, qid), OfflineProvider(engine, output=cross_output))
    assert view(engine, qid).answer.passages[0].attribution == "model_synthesis"
    with Session(engine) as session:
        context = session.get(QueryRun, qid).snapshot["context"]
        bad = json.loads(cross_output({"evidence_context": context}))
        bad["passages"][0]["attribution"] = "paper_author"
        with pytest.raises(KnowledgeError):
            bind_answer(json.dumps(bad), context, query_id=qid, answer_id="test", revision=1)


def test_prompt_contract_drift_is_detected_before_dispatch(prepared, monkeypatch, tmp_path):
    _, engine, qid = prepared
    drifted = tmp_path / "P07.md"
    drifted.write_text(
        answers.LAYOUT_PROMPT_PATH.read_text(encoding="utf-8").replace(
            "output_schema_sha256:", "incorrect_schema_hash:"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(answers, "LAYOUT_PROMPT_PATH", drifted)
    with pytest.raises(ValueError, match="Schema"):
        enqueue(engine, qid)
    with Session(engine) as session:
        assert session.scalar(select(QueryModelRun)) is None


def test_frozen_answer_uses_original_model_even_after_settings_change(prepared):
    _, engine, qid = prepared
    jid = enqueue(engine, qid)
    with Session(engine) as session, session.begin():
        profile = session.get(ModelProfile, "query-profile")
        profile.model = "different-model-now"
    run(engine, jid, OfflineProvider(engine))
    with Session(engine) as session:
        assert session.scalar(select(QueryModelRun)).model == "synthetic-p07"
        answers.validate_answer(session, "project", qid)


@pytest.mark.parametrize(
    "category,code",
    [
        ("client", "QUERY_MODEL_CLIENT"),
        ("structured_output_refused", "QUERY_MODEL_REFUSED"),
        ("output_limit", "QUERY_MODEL_OUTPUT_LIMIT"),
        ("context_limit", "QUERY_MODEL_CONTEXT_LIMIT"),
    ],
)
def test_refusal_and_truncation_keep_partial_but_do_not_publish(prepared, category, code):
    _, engine, qid = prepared
    provider = OfflineProvider(engine, error=ProviderError(category, "provider error"))
    provider.partial_output = '{"passages":[]}'
    run(engine, enqueue(engine, qid), provider)
    result = view(engine, qid)
    assert result.answer is None and result.error_code == code
    assert result.can_continue is (category == "output_limit")
    with Session(engine) as session:
        model = session.scalar(select(QueryModelRun))
        assert model.raw_output == provider.partial_output
        assert not model.parameters["raw_complete"]


def test_two_invalid_complete_responses_cannot_create_another_paid_attempt(prepared):
    _, engine, qid = prepared
    provider = OfflineProvider(engine, output='{"waiver":null}')
    run(engine, enqueue(engine, qid), provider)
    run(engine, enqueue(engine, qid, "second-invalid", continuing=True), provider)
    assert provider.calls == 2 and not view(engine, qid).can_continue
    with pytest.raises(KnowledgeError) as exc:
        enqueue(engine, qid, "third-invalid", continuing=True)
    assert exc.value.code == "QUERY_REQUEST_LIMIT"


def test_provider_credential_is_never_saved_in_raw_or_metadata(prepared):
    _, engine, qid = prepared
    provider = OfflineProvider(engine, output="TEST_ONLY_SENTINEL_SECRET")
    provider.key = "TEST_ONLY_SENTINEL_SECRET"
    provider.request_metadata = {"unexpected": "TEST_ONLY_SENTINEL_SECRET"}
    run(engine, enqueue(engine, qid), provider)
    assert view(engine, qid).error_code == "QUERY_CREDENTIAL_IN_OUTPUT"
    with Session(engine) as session:
        model = session.scalar(select(QueryModelRun))
        assert model.raw_output is None
        assert "TEST_ONLY_SENTINEL_SECRET" not in json.dumps(model.parameters)


def test_cancel_before_send_does_not_reserve_or_call(prepared):
    _, engine, qid = prepared
    provider = OfflineProvider(engine)
    stopped = Event()
    stopped.set()
    run(engine, enqueue(engine, qid), provider, stopped)
    assert provider.calls == view(engine, qid).request_count == 0


def test_model_declared_insufficient_answer_is_not_a_fake_scientific_passage(prepared):
    _, engine, qid = prepared
    provider = OfflineProvider(
        engine,
        output=json.dumps(
            {
                "passages": [],
                "limitations": ["所选证据未覆盖该问题"],
            }
        ),
    )
    run(engine, enqueue(engine, qid), provider)
    result = view(engine, qid)
    assert result.status == "insufficient" and result.answer.passages == []
    assert result.request_count == 1 and not result.can_continue


@pytest.mark.parametrize("attribution", ["paper_author", "model_synthesis"])
def test_personal_note_cannot_become_a_scientific_answer(seeded, tmp_path, attribution):
    api, engine, _ = seeded
    configure(engine)
    notes(engine, tmp_path)
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).query().set_note_grant("project", "root", True, True)
    qid = prepare(api, question="Private", include_personal=True)

    def wrong(data):
        ref = next(r for r in data["evidence_context"]["references"] if r["type"] == "note")
        return json.dumps(
            {
                "passages": [
                    {
                        "text": "Notes are not paper evidence",
                        "attribution": attribution,
                        "source_refs": [ref["ref"]],
                        "limitations": [],
                    }
                ],
                "limitations": [],
            }
        )

    run(engine, enqueue(engine, qid), OfflineProvider(engine, output=wrong))
    result = view(engine, qid)
    assert result.answer is None and result.error_code == "QUERY_GROUNDING_INVALID"


def test_unknown_user_view_requires_a_note_root(prepared):
    _, engine, qid = prepared

    def wrong(data):
        ref = next(r for r in data["evidence_context"]["references"] if r["type"] == "chunk")
        return json.dumps(
            {
                "passages": [
                    {
                        "text": "personal judgment",
                        "attribution": "user_view",
                        "source_refs": [ref["ref"]],
                        "limitations": [],
                    }
                ],
                "limitations": [],
            }
        )

    run(engine, enqueue(engine, qid), OfflineProvider(engine, output=wrong))
    assert view(engine, qid).error_code == "QUERY_ATTRIBUTION_INVALID"


def test_only_an_explicit_citation_attribution_can_restate_cited_candidate(seeded):
    api, engine, eid = seeded
    production(engine, eid)
    second_paper(engine, citation=True)
    configure(engine)
    qid = prepare(api)
    with Session(engine) as session:
        context = session.get(QueryRun, qid).snapshot["context"]
        cited = next(
            r
            for r in context["references"]
            if r["type"] == "node" and r["authorship"] == "cited_other"
        )
        wire = {
            "passages": [
                {
                    "text": "This paper reports a prior author's result",
                    "attribution": "paper_author",
                    "source_refs": [cited["ref"]],
                    "limitations": [],
                }
            ],
            "limitations": [],
        }
        with pytest.raises(KnowledgeError) as exc:
            bind_answer(json.dumps(wire), context, query_id=qid, answer_id="test", revision=1)
        assert exc.value.code == "QUERY_ATTRIBUTION_INVALID"
        wire["passages"][0]["attribution"] = "citation_report"
        bound = bind_answer(json.dumps(wire), context, query_id=qid, answer_id="test", revision=1)
        assert bound.passages[0].attribution == "citation_report"


def test_capacity_insufficiency_stops_before_any_request(seeded):
    api, engine, eid = seeded
    production(engine, eid)
    configure(engine)
    with Session(engine) as session, session.begin():
        profile = session.get(ModelProfile, "query-profile")
        profile.parameters = ModelParameters(
            capabilities={
                "context_window": 1024,
                "max_output_tokens": 900,
                "source": "endpoint_metadata",
            }
        ).model_dump()
    qid = prepare(api)
    provider = OfflineProvider(engine)
    run(engine, enqueue(engine, qid), provider)
    result = view(engine, qid)
    assert result.status == "insufficient" and result.request_count == provider.calls == 0
    assert "容量" in "".join(result.answer.limitations)


def test_source_change_during_response_keeps_raw_received_and_never_publishes(prepared):
    _, engine, qid = prepared

    def change_source():
        with Session(engine) as session, session.begin():
            session.get(Chunk, "paragraph").text = "different immutable source"

    provider = OfflineProvider(engine, action=change_source)
    jid = enqueue(engine, qid)
    run(engine, jid, provider)
    with Session(engine) as session:
        assert session.scalar(select(QueryAnswerVersion)) is None
        model = session.scalar(select(QueryModelRun))
        assert model.status == "received" and model.error is None
        assert model.parameters["reuse_diagnostic"]["code"] in {
            "QUERY_SEED_INVALID",
            "INVALID_ANCHOR",
            "QUERY_CONTEXT_CHANGED",
        }
    with pytest.raises(KnowledgeError):
        enqueue(engine, qid, "cannot-pay-to-fix-source", continuing=True)
    assert provider.calls == 1


def test_collapsed_active_submission_still_freezes_its_idempotency_key(prepared):
    api, engine, qid = prepared
    jid = enqueue(engine, qid)
    assert enqueue(engine, qid, "second-click-key") == jid
    other = prepare(api, question="method")
    with pytest.raises(KnowledgeError) as exc:
        enqueue(engine, other, "second-click-key")
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
