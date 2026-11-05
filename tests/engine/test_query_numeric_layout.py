"""P07 v2 layout guards preserve v1 history; all input is synthetic/offline."""

import json
from copy import deepcopy

import pytest
import test_knowledge
from researchgraph.knowledge_store import KnowledgeError, text_hash
from researchgraph.models import Chunk, Job
from researchgraph.query_answer_wire import PROMPT, SCIENTIFIC_PROMPT, bind_answer
from researchgraph.query_context import build_context, validate_context
from researchgraph.query_models import QueryModelRun, QueryRun
from researchgraph.query_numeric_layout import (
    DISPLAY_NOTICE,
    NUMERIC_PLACEHOLDER,
    RISK_WARNING,
    freeze_layout,
    warnings_by_reference,
)
from researchgraph.query_presentation import source_presentation
from researchgraph.query_retrieval import retrieve
from researchgraph.structure_models import DocumentParse
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_query_answers import OfflineProvider, configure, enqueue, run, view
from test_query_retrieval import request
from test_reading_evidence_quality import make_layout

seeded = test_knowledge.seeded


def numeric_source(engine, eid):
    make_layout(engine, eid)
    with Session(engine) as session, session.begin():
        artifact = session.get(DocumentParse, "parse")
        data = deepcopy(artifact.data)
        data.update(
            parser_version=artifact.parser_version,
            sections=[
                {
                    "id": "s0",
                    "title": "Methods",
                    "parent_id": None,
                    "role": "body",
                    "excluded": False,
                }
            ],
            tables=[],
        )
        data["blocks"][0].update(block_index=0, section_ref="s0", excluded=False)
        artifact.data = data


def prepare_numeric(api):
    response = api.post(
        "/api/v1/projects/project/query/prepare",
        json={**request("212", purpose="model"), "source_kinds": ["chunk"]},
        headers={"Idempotency-Key": "numeric-layout-prepare"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def output(text, ref=None):
    def make(data):
        source = ref or data["evidence_context"]["references"][0]["ref"]
        return json.dumps(
            {
                "passages": [
                    {
                        "text": text,
                        "attribution": "model_synthesis",
                        "source_refs": [source],
                        "limitations": [],
                    }
                ],
                "limitations": [],
            },
            ensure_ascii=False,
        )

    return make


@pytest.mark.parametrize("text", ["分支因子为212。", "212ms", "212.0", "２１２ 个", "212%"])
def test_new_answer_refuses_flattened_value_keeps_raw_and_never_resends(seeded, text):
    api, engine, eid = seeded
    numeric_source(engine, eid)
    configure(engine)
    prepared = prepare_numeric(api)
    qid = prepared["query_id"]
    context = prepared["snapshot"]["context"]
    assert context["numeric_layout"]["sources"][0]["risk_blocks"][0][
        "collapsed_numeric_tokens"
    ] == ["212"]
    provider = OfflineProvider(engine, output=output(text))
    run(engine, enqueue(engine, qid), provider)
    result = view(engine, qid)
    assert result.status == "failed" and result.error_code == "QUERY_NUMERIC_LAYOUT_UNRESOLVED"
    assert result.answer is None and not result.can_continue and provider.calls == 1
    with Session(engine) as session:
        recorded = session.scalar(select(QueryModelRun))
        assert recorded.prompt_name == SCIENTIFIC_PROMPT and text in recorded.raw_output
        assert recorded.parameters["raw_complete"] and recorded.parameters["raw_sha256"]
    assert view(engine, qid).request_count == 1
    with pytest.raises(KnowledgeError, match="来源或配置冲突"):
        enqueue(engine, qid, "numeric-no-resend", continuing=True)
    assert provider.calls == 1


def test_unambiguous_answer_remains_legal_and_records_layout_prompt(seeded):
    api, engine, eid = seeded
    numeric_source(engine, eid)
    configure(engine)
    prepared = prepare_numeric(api)
    qid = prepared["query_id"]
    provider = OfflineProvider(
        engine, output=output("原文的分支因子存在上下标歧义，数值未知，需核对 PDF。")
    )
    run(engine, enqueue(engine, qid), provider)
    assert view(engine, qid).status == "succeeded"
    with Session(engine) as session:
        assert session.scalar(select(QueryModelRun)).prompt_name == SCIENTIFIC_PROMPT


def test_unknown_layout_is_frozen_as_unknown_not_clean(seeded):
    api, engine, _ = seeded
    configure(engine)
    response = api.post(
        "/api/v1/projects/project/query/prepare",
        json=request("accuracy", purpose="model"),
        headers={"Idempotency-Key": "unknown-layout-prepare"},
    )
    assert response.status_code == 200, response.text
    context = response.json()["snapshot"]["context"]
    assert context["numeric_layout"]["sources"][0]["status"] == "unknown"
    assert context["numeric_layout"]["sources"][0]["chunk_checks"][0]["status"] == "unknown"


def test_layout_is_revalidated_and_source_geometry_change_rejects_cache(seeded):
    api, engine, eid = seeded
    numeric_source(engine, eid)
    configure(engine)
    prepared = prepare_numeric(api)
    with Session(engine) as session:
        validate_context(
            session,
            prepared["snapshot"]["context"],
            prepared["snapshot"]["retrieval"],
            model_snapshot=prepared["snapshot"]["model"],
        )
    with Session(engine) as session, session.begin():
        artifact = session.get(DocumentParse, "parse")
        data = deepcopy(artifact.data)
        data["blocks"][0]["lines"][0]["spans"][1]["size"] = 9.5
        artifact.data = data
    with Session(engine) as session, pytest.raises(KnowledgeError, match="已变化"):
        validate_context(
            session,
            prepared["snapshot"]["context"],
            prepared["snapshot"]["retrieval"],
            model_snapshot=prepared["snapshot"]["model"],
        )


def test_old_v1_snapshot_raw_and_prompt_signature_are_unchanged_on_replay(seeded):
    api, engine, eid = seeded
    numeric_source(engine, eid)
    configure(engine)
    prepared = prepare_numeric(api)
    qid = prepared["query_id"]
    with Session(engine) as session, session.begin():
        query = session.get(QueryRun, qid)
        snapshot = deepcopy(query.snapshot)
        old = build_context(
            session, query.request, snapshot["retrieval"], model_snapshot=snapshot["model"]
        )
        assert "numeric_layout" not in old
        snapshot["context"] = old
        query.snapshot, query.input_hash = snapshot, old["input_hash"]
        legacy_hash = old["input_hash"]
    provider = OfflineProvider(engine, output=output("旧协议原响应212，保持历史内容。"))
    run(engine, enqueue(engine, qid), provider)
    before = view(engine, qid).answer.model_dump(mode="json")
    with Session(engine) as session:
        recorded = session.scalar(select(QueryModelRun))
        assert recorded.prompt_name == PROMPT
        raw, parameters, manifest = (
            recorded.raw_output,
            deepcopy(recorded.parameters),
            deepcopy(recorded.manifest),
        )
        assert session.get(QueryRun, qid).input_hash == legacy_hash
    assert enqueue(engine, qid, "legacy-zero-call-replay", continuing=True)
    assert view(engine, qid).answer.model_dump(mode="json") == before and provider.calls == 1
    with Session(engine) as session:
        recorded = session.scalar(select(QueryModelRun))
        assert (recorded.raw_output, recorded.parameters, recorded.manifest) == (
            raw,
            parameters,
            manifest,
        )
        assert session.get(QueryRun, qid).input_hash == legacy_hash


def test_node_only_preview_uses_real_evidence_layout_and_old_display_warns(seeded):
    _, engine, eid = seeded
    numeric_source(engine, eid)
    with Session(engine) as session:
        layout = freeze_layout(
            session,
            [
                {
                    "ref": "N",
                    "type": "node",
                    "id": "synthetic-node",
                    "document_version_id": "version",
                    "evidence_ids": [eid],
                }
            ],
        )
        assert RISK_WARNING in warnings_by_reference(layout)["N"]
        found = retrieve(session, "project", "212", [], source_kinds=["chunk"])
        context = build_context(session, request("212"), found)
        assert "numeric_layout" not in context
        before = deepcopy(context)
        display = source_presentation(session, "project", found, context)
        assert any(RISK_WARNING in v["layout_warnings"] for v in display["references"].values())
        assert context == before and not session.dirty


def test_valid_other_reference_cannot_launder_known_number_or_saved_wrapper():
    context = {
        "references": [{"ref": "S1", "type": "chunk", "paper_id": "p", "document_version_id": "v"}],
        "numeric_layout": {
            "sources": [
                {"risk_blocks": [{"source_refs": ["S9"], "collapsed_numeric_tokens": ["212"]}]}
            ]
        },
    }
    raw = output("结果212毫秒", "S1")({})
    with pytest.raises(KnowledgeError, match="上下标"):
        bind_answer(raw, context, query_id="q", answer_id="a", revision=1)
    value = json.loads(output("安全的有据解释", "S1")({}))
    value["limitations"] = ["该数量为212ms"]
    context.update(status="ready", input_hash="a" * 64)
    answer = bind_answer(json.dumps(value), context, query_id="q", answer_id="a", revision=1)
    assert answer.limitations[0] == f"该数量为{NUMERIC_PLACEHOLDER}ms"
    assert DISPLAY_NOTICE in answer.limitations


def legacy_completed(seeded, *, caution_only=False):
    api, engine, eid = seeded
    numeric_source(engine, eid)
    configure(engine)
    prepared = prepare_numeric(api)
    qid = prepared["query_id"]
    with Session(engine) as session, session.begin():
        query = session.get(QueryRun, qid)
        snapshot = deepcopy(query.snapshot)
        old = build_context(
            session, query.request, snapshot["retrieval"], model_snapshot=snapshot["model"]
        )
        snapshot["context"] = old
        query.snapshot, query.input_hash = snapshot, old["input_hash"]

    def two_passages(data):
        value = json.loads(output("数值未知。" if caution_only else "数值212毫秒")(data))
        if caution_only:
            value["passages"][0]["limitations"] = ["212ms是有歧义的原文数字，不得照用。"]
        value["passages"].extend(
            json.loads(output("该数值存在版式歧义，具体数值未知。")(data))["passages"]
        )
        return json.dumps(value, ensure_ascii=False)

    provider = OfflineProvider(engine, output=two_passages)
    run(engine, enqueue(engine, qid), provider)
    result = view(engine, qid)
    assert result.status == "succeeded" and provider.calls == 1
    return api, engine, qid, result, provider


def save_body(result, selected):
    answer = result.answer
    return {
        "source_query_id": result.query_id,
        "answer_version_id": answer.answer_version_id,
        "selected_passage_refs": selected,
        "expected_input_hash": answer.input_hash,
        "kind": "synthesis",
    }


def test_v1_new_save_checks_only_selected_passages_without_changing_old_answer(seeded):
    api, engine, qid, result, provider = legacy_completed(seeded)
    before = result.answer.model_dump(mode="json")
    prefix = f"/api/v1/projects/project/query/runs/{qid}/save"
    bad = api.post(
        prefix, json=save_body(result, ["A00001"]), headers={"Idempotency-Key": "v1-bad-new-save"}
    )
    assert bad.json()["error"]["code"] == "QUERY_NUMERIC_LAYOUT_UNRESOLVED"
    safe = api.post(
        prefix, json=save_body(result, ["A00002"]), headers={"Idempotency-Key": "v1-safe-new-save"}
    )
    assert safe.status_code == 200, safe.text
    assert view(engine, qid).answer.model_dump(mode="json") == before and provider.calls == 1
    replay = api.post(
        prefix,
        json=save_body(result, ["A00002"]),
        headers={"Idempotency-Key": "v1-safe-new-key-save"},
    )
    assert replay.status_code == 200 and replay.json()["saved_id"] == safe.json()["saved_id"]


def test_v1_saved_replay_new_and_same_key_cannot_bypass_current_numeric_gate(seeded, monkeypatch):
    from researchgraph import query_save

    api, engine, qid, result, provider = legacy_completed(seeded)
    prefix = f"/api/v1/projects/project/query/runs/{qid}/save"
    body = save_body(result, ["A00001"])
    # Construct a pre-guard saved record, then restore the current production
    # boundary. Historical read/raw is retained, while explicit writes recheck.
    with monkeypatch.context() as old_runtime:
        old_runtime.setattr(query_save, "_check_selected_numeric_layout", lambda *args: None)
        response = api.post(prefix, json=body, headers={"Idempotency-Key": "old-save"})
        assert response.status_code == 200, response.text
    before = view(engine, qid).answer.model_dump(mode="json")
    for key in ("old-save", "old-save-new"):
        response = api.post(prefix, json=body, headers={"Idempotency-Key": key})
        assert response.json()["error"]["code"] == "QUERY_NUMERIC_LAYOUT_UNRESOLVED"
    assert view(engine, qid).answer.model_dump(mode="json") == before and provider.calls == 1


def caution_output(data):
    value = json.loads(output("原文数值存在版式歧义，具体数值未知，需核对PDF。")(data))
    value["passages"][0]["limitations"] = ["不要将２１２.０ms或212当成普通数字；Ａ Å ①不改。"]
    value["limitations"] = ["原文212%存在歧义。"]
    return json.dumps(value, ensure_ascii=False)


def test_cautions_are_deterministically_masked_raw_preserved_and_save_revalidates(seeded):
    api, engine, eid = seeded
    numeric_source(engine, eid)
    configure(engine)
    qid = prepare_numeric(api)["query_id"]
    provider = OfflineProvider(engine, output=caution_output)
    run(engine, enqueue(engine, qid), provider)
    result = view(engine, qid)
    assert result.status == "succeeded" and result.request_count == provider.calls == 1
    assert "数值未知" in result.answer.passages[0].text
    caveats = result.answer.passages[0].caveats
    assert (
        caveats[0]
        == f"不要将{NUMERIC_PLACEHOLDER}ms或{NUMERIC_PLACEHOLDER}当成普通数字；Ａ Å ①不改。"
    )
    assert DISPLAY_NOTICE in caveats and DISPLAY_NOTICE in result.answer.limitations
    with Session(engine) as session:
        model = session.scalar(select(QueryModelRun))
        raw = model.raw_output
        assert raw == caution_output(
            {"evidence_context": session.get(QueryRun, qid).snapshot["context"]}
        )
        audit = deepcopy(model.parameters["display_normalization"])
        assert audit["raw_sha256"] == text_hash(raw)
        assert audit["replacement_count"] == 3
        assert audit["offset_unit"] == "unicode-codepoint-zero-based-half-open"
        assert audit["fields"][0]["path"] == "passages.0.limitations.0"
        assert audit["fields"][0]["spans"][0]["start"] == 3
    body = save_body(result, ["A00001"])
    url = f"/api/v1/projects/project/query/runs/{qid}/save"
    first = api.post(url, json=body, headers={"Idempotency-Key": "safe-caution-save"})
    assert first.status_code == 200, first.text
    replay = api.post(url, json=body, headers={"Idempotency-Key": "safe-caution-replay"})
    assert replay.status_code == 200 and replay.json()["saved_id"] == first.json()["saved_id"]
    with Session(engine) as session, session.begin():
        model = session.scalar(select(QueryModelRun))
        changed = deepcopy(model.parameters)
        changed["display_normalization"]["replacement_count"] += 1
        model.parameters = changed
    from researchgraph import query_answers

    with Session(engine) as session, pytest.raises(KnowledgeError, match="替换审计"):
        query_answers.validate_answer(session, "project", qid)
    rejected = api.post(url, json=body, headers={"Idempotency-Key": "safe-caution-save"})
    assert rejected.json()["error"]["code"] == "QUERY_SAVED_INVALID"
    assert provider.calls == 1


def old_caution_failure(seeded, monkeypatch):
    from researchgraph import query_answers
    from researchgraph.query_numeric_layout import validate_numeric_layout

    api, engine, eid = seeded
    numeric_source(engine, eid)
    configure(engine)
    qid = prepare_numeric(api)["query_id"]
    original = query_answers.bind_answer

    def former_guard(raw, context, **kwargs):
        wire = json.loads(raw)
        validate_numeric_layout([], context["numeric_layout"], wire["limitations"])
        return original(raw, context, **kwargs)

    provider = OfflineProvider(engine, output=caution_output)
    jid = enqueue(engine, qid)
    with monkeypatch.context() as old:
        old.setattr(query_answers, "bind_answer", former_guard)
        run(engine, jid, provider)
    with Session(engine) as session:
        model = session.scalar(select(QueryModelRun))
        before = (
            model.raw_output,
            deepcopy(model.manifest),
            deepcopy(model.parameters),
            model.error,
        )
        old_job = deepcopy(session.get(Job, jid).result)
    return api, engine, qid, jid, old_job, before, provider


def test_former_numeric_failure_recovers_raw_without_new_slot_or_network(seeded, monkeypatch):
    api, engine, qid, old_jid, old_result, before, provider = old_caution_failure(
        seeded, monkeypatch
    )
    assert view(engine, qid).can_continue
    recovery = enqueue(engine, qid, "recover-only", continuing=True)
    with Session(engine) as session:
        payload = session.get(Job, recovery).payload
        assert payload["recovery_only"] and payload["request_budget"] == 1
    no_network = OfflineProvider(engine, error=AssertionError("network forbidden"))
    run(engine, recovery, no_network)
    result = view(engine, qid)
    assert result.status == "succeeded" and result.request_count == 1
    assert result.model_runs[0].error_code is None and result.model_runs[0].error is None
    assert no_network.calls == 0 and provider.calls == 1
    with Session(engine) as session:
        model = session.scalar(select(QueryModelRun))
        assert (model.raw_output, model.manifest) == before[:2]
        assert model.parameters["recovered_validation"]["error"] == before[3]
        assert model.parameters["recovered_validation"]["status"] == "validation_failed"
        old = session.get(Job, old_jid)
        assert old.status == "failed" and old.result == old_result
    body = save_body(result, ["A00001"])
    url = f"/api/v1/projects/project/query/runs/{qid}/save"
    assert (
        api.post(url, json=body, headers={"Idempotency-Key": "recovered-save"}).status_code == 200
    )
    assert view(engine, qid).answer == result.answer


@pytest.mark.parametrize("change", ["raw", "source"])
def test_recovery_only_rejects_changed_raw_or_source_without_fallback(seeded, monkeypatch, change):
    _, engine, qid, _, _, _, _ = old_caution_failure(seeded, monkeypatch)
    recovery = enqueue(engine, qid, "recover-only", continuing=True)
    with Session(engine) as session, session.begin():
        if change == "raw":
            model = session.scalar(select(QueryModelRun))
            model.raw_output += " "
            model.parameters = {**model.parameters, "raw_sha256": text_hash(model.raw_output)}
        else:
            session.get(Chunk, "paragraph").text += " changed"
    provider = OfflineProvider(engine, error=AssertionError("network forbidden"))
    run(engine, recovery, provider)
    with Session(engine) as session:
        assert session.get(Job, recovery).status == "failed"
        assert len(list(session.scalars(select(QueryModelRun)))) == 1
    assert provider.calls == 0


def test_v1_new_save_rejects_even_caution_only_risky_value(seeded):
    api, engine, qid, result, provider = legacy_completed(seeded, caution_only=True)
    before = result.answer.model_dump(mode="json")
    response = api.post(
        f"/api/v1/projects/project/query/runs/{qid}/save",
        json=save_body(result, ["A00001"]),
        headers={"Idempotency-Key": "caution-save"},
    )
    assert response.json()["error"]["code"] == "QUERY_NUMERIC_LAYOUT_UNRESOLVED"
    assert view(engine, qid).answer.model_dump(mode="json") == before and provider.calls == 1


def test_real_warning_shape_masks_all_known_tokens_but_preserves_unknown_status():
    context = {
        "references": [{"ref": "S1", "type": "chunk", "paper_id": "p", "document_version_id": "v"}],
        "numeric_layout": {
            "sources": [
                {
                    "status": "partial",
                    "risk_blocks": [
                        {"collapsed_numeric_tokens": ["10123", "10126", "1016", "212"]}
                    ],
                }
            ]
        },
        "status": "ready",
        "input_hash": "a" * 64,
    }
    before = deepcopy(context)
    value = json.loads(output("数值未知；原文有指数排版歧义。", "S1")({}))
    value["passages"][0]["limitations"] = ["10123、10126、1016、212均不可照用。"]
    value["passages"] = [deepcopy(value["passages"][0]) for _ in range(6)]
    value["limitations"] = ["请核对10123、10126、1016、２１２.０ms。"]
    raw = json.dumps(value, ensure_ascii=False)
    answer = bind_answer(raw, context, query_id="q", answer_id="a", revision=1)
    from researchgraph.query_answer_wire import display_normalization

    audit = display_normalization(raw, context, answer)
    assert audit["replacement_count"] == 28  # Six passage lists and one global list.
    assert all(p.text == "数值未知；原文有指数排版歧义。" for p in answer.passages)
    assert "２１２.０" in raw and "10126" in raw
    assert context == before and context["numeric_layout"]["sources"][0]["status"] == "partial"
