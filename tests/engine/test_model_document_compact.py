"""Compact note slots keep full source validation and frozen legacy protocols."""

import asyncio
import json
from copy import deepcopy

import pytest
from researchgraph.import_plan_models import ImportSession
from researchgraph.model_document_api import (
    execute_document_postprocess,
    queue_model_document_output,
    register_model_document_api,
)
from researchgraph.model_document_models import (
    LlmDocumentOutput,
    LlmDocumentOutputLocalRecovery,
    LlmDocumentSegment,
)
from researchgraph.model_document_reading import (
    compact_document_spec,
    expand_compact_document_output,
    normalize_reading_highlight_aliases,
    recover_reading_highlights,
    validate_reading_output,
    validate_translation_output,
)
from researchgraph.models import Job
from researchgraph.providers import ProviderError
from researchgraph.schemas import ImportPlan
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_model_document_outputs import Provider
from test_model_document_overview import _fixture
from test_model_document_reading import reading_payload


@pytest.fixture
def segments():
    return [
        {
            "id": "p1",
            "kind": "paragraph",
            "chapter_ref": "intro",
            "ordinal": 0,
            "text": "A result follows.",
        },
        {
            "id": "p2",
            "kind": "paragraph",
            "chapter_ref": "results",
            "ordinal": 1,
            "text": "A result follows.",
        },
    ]


def _notes(source):
    full = reading_payload(source)
    return {
        "slots": {
            str(index): {
                key: value
                for key, value in item.items()
                if key not in {"paragraph_id", "translation_zh", "related_graph_node_ids"}
            }
            for index, item in enumerate(full["paragraphs"], 1)
        },
        "paper_argument": full["paper_argument"],
    }


def test_compact_notes_bind_complete_numbered_slots_without_repeating_source_ids(segments):
    prompt, context, schema = compact_document_spec(segments, "paper_reading")
    assert [p["slot"] for p in context["paragraphs"]] == ["1", "2"]
    assert all("paragraph_id" not in p for p in context["paragraphs"])
    assert context["paragraphs"][0]["text_en"] == context["paragraphs"][1]["text_en"]
    assert "不翻译" in prompt
    assert schema["properties"]["slots"]["required"] == ["1", "2"]
    assert schema["properties"]["slots"]["additionalProperties"] is False
    assert schema["$defs"]["Slot"]["additionalProperties"] is False
    assert schema["$defs"]["Slot"]["properties"]["highlights"]["items"] == {
        "$ref": "#/$defs/ArgumentHighlight"
    }
    notes = _notes(segments)
    notes["slots"] = dict(reversed(list(notes["slots"].items())))
    expanded = expand_compact_document_output(json.dumps(notes), segments, "paper_reading")
    result = validate_reading_output(expanded, segments)
    assert [p.paragraph_id for p in result.paragraphs] == ["p1", "p2"]
    assert all(
        p.translation_zh is None and p.related_graph_node_ids == [] for p in result.paragraphs
    )


def test_compact_v4_prompt_names_canonical_enums_while_v3_prompt_is_unchanged(segments):
    v3_prompt, _context, schema = compact_document_spec(segments, "paper_reading")
    legacy_prompt, _legacy_context, _legacy_schema = compact_document_spec(
        segments, "paper_reading", explicit_highlight_types=False
    )
    v4_prompt, _v4_context, v4_schema = compact_document_spec(
        segments, "paper_reading", explicit_highlight_types=True
    )
    assert v3_prompt == legacy_prompt
    assert v4_schema == schema
    highlight_enum = v4_schema["$defs"]["ArgumentHighlight"]["properties"]["type"]["enum"]
    assert set(highlight_enum) == {
        "THESIS",
        "CONCEPT",
        "EVIDENCE",
        "COUNTERARGUMENT",
        "METHOD",
    }
    for name in highlight_enum:
        assert name in v4_prompt
    assert "作者的中心主张、假设或关键结论" in v4_prompt
    assert "不得使用CLAIM或其他同义词" in v4_prompt
    for name in v4_schema["$defs"]["Slot"]["properties"]["paragraph_function"]["enum"]:
        assert name in v4_prompt


@pytest.mark.parametrize("contract_version", [2, 3, 4])
def test_exact_claim_alias_normalization_changes_only_highlight_type(segments, contract_version):
    full = reading_payload(segments)
    full["paragraphs"][0]["highlights"][0]["type"] = "CLAIM"
    if contract_version == 2:
        payload = full
    else:
        payload = _notes(segments)
        payload["slots"]["1"]["highlights"][0]["type"] = "CLAIM"
    raw = json.dumps(payload)
    before = deepcopy(payload)
    normalized, audit = normalize_reading_highlight_aliases(raw, contract_version=contract_version)
    assert raw == json.dumps(payload)
    if contract_version == 2:
        before["paragraphs"][0]["highlights"][0]["type"] = "THESIS"
        assert normalized == before
        assert audit == [
            {
                "rule": "reading-highlight-claim-to-thesis-1",
                "path": "paragraphs[0].highlights[0].type",
                "from": "CLAIM",
                "to": "THESIS",
            }
        ]
        recovered, recovery_audit = recover_reading_highlights(
            raw, segments, contract_version=contract_version
        )
        assert recovered.paragraphs[0].highlights[0].type == "THESIS"
        assert recovery_audit == audit
    else:
        before["slots"]["1"]["highlights"][0]["type"] = "THESIS"
        assert normalized == before
        assert audit == [
            {
                "rule": "reading-highlight-claim-to-thesis-1",
                "path": "slots.1.highlights[0].type",
                "from": "CLAIM",
                "to": "THESIS",
            }
        ]
        recovered, recovery_audit = recover_reading_highlights(
            raw, segments, contract_version=contract_version
        )
        assert recovered.paragraphs[0].highlights[0].type == "THESIS"
        assert recovery_audit == audit


@pytest.mark.parametrize("alias", ["claim", " CLAIM ", "THESIS "])
def test_noncanonical_highlight_aliases_are_not_normalized(segments, alias):
    notes = _notes(segments)
    notes["slots"]["1"]["highlights"][0]["type"] = alias
    raw = json.dumps(notes)
    normalized, audit = normalize_reading_highlight_aliases(raw, contract_version=4)
    assert normalized["slots"]["1"]["highlights"][0]["type"] == alias
    assert audit == []
    with pytest.raises(ValueError):
        recover_reading_highlights(raw, segments, contract_version=4)


def test_explicit_recovery_quarantines_only_source_missing_quotes(segments):
    full = reading_payload(segments)
    full["paragraphs"][0]["highlights"] = [
        {"type": "CLAIM", "quote_en": "fabricated quote", "occurrence_index": 0},
        {"type": "EVIDENCE", "quote_en": "result", "occurrence_index": 1},
        {"type": "METHOD", "quote_en": "result", "occurrence_index": 0},
    ]
    raw = json.dumps(full)
    recovered, audit = recover_reading_highlights(raw, segments, contract_version=2)
    assert [item.type for item in recovered.paragraphs[0].highlights] == ["METHOD"]
    assert audit == [
        {
            "rule": "reading-highlight-claim-to-thesis-1",
            "path": "paragraphs[0].highlights[0].type",
            "from": "CLAIM",
            "to": "THESIS",
        },
        {
            "rule": "reading-highlight-source-quote-quarantine-1",
            "path": "paragraphs[0].highlights[0]",
            "code": "QUOTE_NOT_IN_SOURCE",
        },
        {
            "rule": "reading-highlight-source-quote-quarantine-1",
            "path": "paragraphs[0].highlights[1]",
            "code": "QUOTE_NOT_IN_SOURCE",
        },
    ]


def test_explicit_recovery_quarantines_out_of_range_occurrence_without_expanding_search(segments):
    full = reading_payload(segments)
    full["paragraphs"][0]["highlights"][0]["occurrence_index"] = 10**30
    recovered, audit = recover_reading_highlights(json.dumps(full), segments, contract_version=2)
    assert recovered.paragraphs[0].highlights == []
    assert audit == [
        {
            "rule": "reading-highlight-source-quote-quarantine-1",
            "path": "paragraphs[0].highlights[0]",
            "code": "QUOTE_NOT_IN_SOURCE",
        }
    ]


@pytest.mark.parametrize(
    "change",
    [
        "wrong_id",
        "missing_slot",
        "extra_slot",
        "unknown_enum",
        "unknown_highlight_type",
        "extra_field",
    ],
)
def test_explicit_recovery_rejects_non_quote_contract_errors(segments, change):
    if change == "wrong_id":
        payload = reading_payload(segments)
        payload["paragraphs"][0]["paragraph_id"] = "outside"
        version = 2
    else:
        payload = _notes(segments)
        if change == "missing_slot":
            payload["slots"].pop("2")
        elif change == "extra_slot":
            payload["slots"]["3"] = deepcopy(payload["slots"]["1"])
        elif change == "unknown_enum":
            payload["slots"]["1"]["paragraph_function"] = "UNRECOGNIZED"
        elif change == "unknown_highlight_type":
            payload["slots"]["1"]["highlights"][0]["type"] = "CLAIM_LIKE"
        else:
            payload["slots"]["1"]["unexpected"] = "value"
        version = 4
    with pytest.raises(ValueError):
        recover_reading_highlights(json.dumps(payload), segments, contract_version=version)


@pytest.mark.parametrize("raw", ['{"slots":{},"slots":{}}', '{"slots":{"1":NaN}}'])
def test_alias_normalization_rejects_duplicate_and_nonfinite_json(segments, raw):
    with pytest.raises(ValueError):
        normalize_reading_highlight_aliases(raw, contract_version=4)


@pytest.mark.parametrize(
    "change",
    ["missing", "extra", "renumber", "list", "envelope", "field", "enum", "quote", "occurrence"],
)
def test_compact_notes_reject_coverage_schema_and_source_errors(segments, change):
    notes = _notes(segments)
    if change == "missing":
        notes["slots"].pop("2")
    elif change == "extra":
        notes["slots"]["3"] = notes["slots"]["1"]
    elif change == "renumber":
        notes["slots"]["01"] = notes["slots"].pop("1")
    elif change == "list":
        notes["slots"] = list(notes["slots"].values())
    elif change == "envelope":
        notes["paragraphs"] = []
    elif change == "field":
        notes["slots"]["1"]["paragraph_id"] = "p2"
    elif change == "enum":
        notes["slots"]["1"]["paragraph_function"] = "UNRECOGNIZED"
    elif change == "quote":
        notes["slots"]["1"]["highlights"][0]["quote_en"] = "fabricated quotation"
    else:
        notes["slots"]["1"]["highlights"][0]["occurrence_index"] = 1
    with pytest.raises(ValueError):
        expanded = expand_compact_document_output(json.dumps(notes), segments, "paper_reading")
        validate_reading_output(expanded, segments)


def test_compact_duplicate_keys_nonfinite_and_unsupported_kind_are_rejected(segments):
    raw = json.dumps(_notes(segments))
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        expand_compact_document_output(
            raw.replace('"slots":', '"slots":{},"slots":'), segments, "paper_reading"
        )
    with pytest.raises(ValueError, match="Non-finite"):
        expand_compact_document_output(
            raw.replace('"occurrence_index": 0', '"occurrence_index": NaN'),
            segments,
            "paper_reading",
        )
    with pytest.raises(ValueError, match="SLOT_KIND"):
        compact_document_spec(segments, "paper_overview")
    with pytest.raises(ValueError, match="SLOT_KIND"):
        expand_compact_document_output(raw, segments, "paper_overview")


@pytest.mark.parametrize("value", ["接下来给出一个结果。", "A result follows.", "", "  ", None, 1])
def test_compact_translation_binds_original_text_and_checks_translation(segments, value):
    _prompt, context, schema = compact_document_spec(segments, "translation")
    assert "materials" not in context
    assert "source_text" not in json.dumps(schema)
    raw = json.dumps({"slots": {"2": value, "1": value}})
    expanded = expand_compact_document_output(raw, segments, "translation")
    if value == "接下来给出一个结果。":
        result = validate_translation_output(expanded, segments)
        assert [item.paragraph_id for item in result.translations] == ["p1", "p2"]
        assert all(item.source_text == "A result follows." for item in result.translations)
    else:
        with pytest.raises(ValueError):
            validate_translation_output(expanded, segments)


def _queue(tmp_path, monkeypatch, item_kind):
    engine, _client, _paper_id, parse_id, session_id = _fixture(tmp_path)
    snapshot = {
        "provider": "synthetic",
        "model": "synthetic",
        "parameters": {
            "timeout_seconds": 30,
            "document_timeout_seconds": 600,
            "document_total_timeout_seconds": 1800,
        },
    }
    monkeypatch.setattr("researchgraph.model_settings.snapshot_for", lambda *args: snapshot)
    with Session(engine) as db, db.begin():
        job = queue_model_document_output(db, session_id, item_kind, allow_network=True)
        job_id, output_id = job.id, job.payload["output_id"]
        assert job.payload["postprocess_contract_version"] == (
            4 if item_kind == "paper_reading" else 3
        )
        assert job.payload["provider_snapshot"]["parameters"]["timeout_seconds"] == 600
        assert job.payload["provider_snapshot"]["parameters"]["text_total_timeout_seconds"] == 1800
        assert snapshot["parameters"]["timeout_seconds"] == 30
    return engine, parse_id, session_id, job_id, output_id


@pytest.mark.parametrize("item_kind", ["paper_reading", "translation"])
def test_worker_publishes_compact_response_only_after_binding_all_source_slots(
    tmp_path, monkeypatch, item_kind
):
    engine, _parse_id, _session_id, job_id, output_id = _queue(tmp_path, monkeypatch, item_kind)

    class CompactProvider(Provider):
        async def complete(self, prompt, data, schema):
            self.calls.append(data)
            slots = {}
            for paragraph in data["paragraphs"]:
                assert "paragraph_id" not in paragraph
                slots[paragraph["slot"]] = (
                    "作者阐述研究内容。"
                    if item_kind == "translation"
                    else {
                        "paragraph_function": "OTHER",
                        "logic_role_zh": "说明研究内容。",
                        "critical_note_zh": "",
                        "reading_question_zh": None,
                        "highlights": [],
                    }
                )
            result = {"slots": slots}
            if item_kind == "paper_reading":
                result["paper_argument"] = {
                    "logic_chain_zh": ["提出问题", "说明研究内容"],
                    "core_claim_zh": None,
                    "strong_point_zh": None,
                    "question_to_verify_zh": None,
                }
            self.response = json.dumps(result)
            return self.response

    provider = CompactProvider()
    asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as db:
        output = db.get(LlmDocumentOutput, output_id)
        assert output.status == db.get(Job, job_id).status == "succeeded"
        assert output.raw_response == provider.response
        assert output.usage["contract_version"] == (4 if item_kind == "paper_reading" else 3)
        assert output.usage["requests"][0]["status"] == "received"
        assert "slots" not in output.output_json
        if item_kind == "paper_reading":
            source = list(
                db.scalars(
                    select(LlmDocumentSegment).where(LlmDocumentSegment.parse_id == output.parse_id)
                )
            )
            validate_reading_output(output.output_json, source)
        else:
            source = list(
                db.scalars(
                    select(LlmDocumentSegment).where(LlmDocumentSegment.parse_id == output.parse_id)
                )
            )
            validate_translation_output(output.output_json, source)
    asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    assert len(provider.calls) == 1


def test_legacy_v2_format_repair_preserves_protocol_raw_and_full_source_checks(
    tmp_path, monkeypatch
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine, parse_id, session_id, job_id, output_id = _queue(tmp_path, monkeypatch, "paper_reading")
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        job.payload = {**job.payload, "postprocess_contract_version": 2}
        source = list(
            db.scalars(select(LlmDocumentSegment).where(LlmDocumentSegment.parse_id == parse_id))
        )
        # Contract fixtures operate on dictionaries, with a quote from each real source.
        paragraphs = [dict(id=s.id, kind=s.kind, text=s.text) for s in source]
        valid = reading_payload(paragraphs)
        for paragraph in valid["paragraphs"]:
            paragraph["highlights"] = []
    invalid = deepcopy(valid)
    invalid["paragraphs"][0]["paragraph_id"] = "outside-source"
    raw = json.dumps(invalid)
    provider = Provider(raw)
    with pytest.raises(ProviderError):
        asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    app = FastAPI()
    register_model_document_api(app, lambda: engine)
    api = TestClient(app)
    response = api.post(
        f"/api/v1/import-sessions/{session_id}/document-outputs/{output_id}/format-repair",
        json={"allow_network": True},
        headers={"Idempotency-Key": "v2-repair"},
    )
    assert response.status_code == 202, response.text
    repair_id = response.json()["id"]
    with Session(engine) as db:
        assert db.get(Job, repair_id).payload["postprocess_contract_version"] == 2
        assert db.get(LlmDocumentOutput, output_id).raw_response == raw
    provider = Provider(json.dumps(valid))
    asyncio.run(execute_document_postprocess(engine, repair_id, tmp_path, provider=provider))
    assert "paragraph_id" in provider.calls[0]["data"]["source_context"]["paragraphs"][0]
    assert provider.calls[0]["data"]["failed_response"] == raw
    with Session(engine) as db:
        original = db.get(LlmDocumentOutput, output_id)
        repaired = db.get(LlmDocumentOutput, db.get(Job, repair_id).payload["output_id"])
        assert original.status == "failed" and original.raw_response == raw
        assert repaired.status == "succeeded" and repaired.usage["contract_version"] == 2


def test_import_plan_defaults_to_new_wire_protocol_and_preserves_explicit_v2():
    assert ImportPlan().postprocess_contract_version == 4
    assert ImportPlan(postprocess_contract_version=2).postprocess_contract_version == 2


def test_explicit_local_recovery_persists_only_partial_reading_and_preserves_failure(
    tmp_path, monkeypatch
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine, parse_id, session_id, job_id, output_id = _queue(tmp_path, monkeypatch, "paper_reading")
    with Session(engine) as db:
        segments = list(
            db.scalars(select(LlmDocumentSegment).where(LlmDocumentSegment.parse_id == parse_id))
        )
        paragraphs = [
            {
                "id": segment.id,
                "kind": segment.kind,
                "chapter_ref": segment.chapter_ref,
                "text": segment.text,
            }
            for segment in segments
        ]
        paragraphs = [item for item in paragraphs if item["kind"] == "paragraph"]
    slots = {}
    for index, paragraph in enumerate(paragraphs, 1):
        highlights = []
        if index == 1:
            highlights = [
                {
                    "type": "CLAIM",
                    "quote_en": paragraph["text"][:16],
                    "occurrence_index": 0,
                },
                {
                    "type": "EVIDENCE",
                    "quote_en": "not present in source",
                    "occurrence_index": 0,
                },
            ]
        slots[str(index)] = {
            "paragraph_function": "OTHER",
            "logic_role_zh": "说明当前论证内容。",
            "critical_note_zh": "",
            "reading_question_zh": None,
            "highlights": highlights,
        }
    raw = json.dumps(
        {
            "slots": slots,
            "paper_argument": {
                "logic_chain_zh": ["提出问题", "说明材料"],
                "core_claim_zh": None,
                "strong_point_zh": None,
                "question_to_verify_zh": None,
            },
        }
    )
    provider = Provider(raw)
    with pytest.raises(ProviderError):
        asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))

    app = FastAPI()
    register_model_document_api(app, lambda: engine)
    api = TestClient(app)
    with Session(engine) as db:
        paper_id = db.get(ImportSession, session_id).source_snapshot["paper_id"]
    response = api.post(
        f"/api/v1/papers/{paper_id}/model-document-outputs/{output_id}/local-recovery",
        json={},
        headers={"Idempotency-Key": "local-reading-recovery"},
    )
    assert response.status_code == 200, response.text
    recovered = response.json()
    assert recovered["status"] == "partial"
    assert recovered["recovery_summary"] == {"normalized_types": 1, "unresolved_highlights": 1}
    assert [h["type"] for h in recovered["output_json"]["paragraphs"][0]["highlights"]] == [
        "THESIS"
    ]
    assert "raw_response" not in recovered

    listing = api.get(f"/api/v1/import-sessions/{session_id}/document-outputs").json()
    listed = next(item for item in listing if item["id"] == output_id)
    assert listed["status"] == "partial"
    assert listed["output_json"] == recovered["output_json"]
    assert listed["local_recovery_available"] is False
    with Session(engine) as db, db.begin():
        recovery = db.get(LlmDocumentOutputLocalRecovery, output_id)
        corrupted = deepcopy(recovery.output_json)
        corrupted["paragraphs"][0]["highlights"][0]["quote_en"] = "not source-bound"
        recovery.output_json = corrupted
    listing = api.get(f"/api/v1/import-sessions/{session_id}/document-outputs").json()
    retryable = next(item for item in listing if item["id"] == output_id)
    assert retryable["status"] == "failed" and retryable["local_recovery_available"] is True
    rebuilt = api.post(
        f"/api/v1/papers/{paper_id}/model-document-outputs/{output_id}/local-recovery",
        json={},
        headers={"Idempotency-Key": "local-reading-recovery-rebuild"},
    )
    assert rebuilt.status_code == 200 and rebuilt.json()["status"] == "partial"
    assert rebuilt.json()["output_json"] == recovered["output_json"]
    assert len(provider.calls) == 1
    with Session(engine) as db:
        original = db.get(LlmDocumentOutput, output_id)
        assert original.status == "failed"
        assert original.error_code == "MODEL_DOCUMENT_POSTPROCESS_CONTRACT_FAILED"
        assert original.output_json is None and original.raw_response == raw
        assert db.get(Job, job_id).status == "failed"
        audit = db.get(LlmDocumentOutputLocalRecovery, output_id).audit_json
        assert all("quote_en" not in item for item in audit)


@pytest.mark.parametrize(
    "category", ["timeout", "empty_response", "incomplete_stream", "output_limit"]
)
def test_transport_failure_is_not_format_error_and_keeps_safe_receipt(
    tmp_path, monkeypatch, category
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine, _parse_id, session_id, job_id, output_id = _queue(
        tmp_path, monkeypatch, "paper_reading"
    )

    class FailedProvider(Provider):
        partial_output = None if category == "empty_response" else '{"slots":{"1":'
        request_metadata = {
            "transport": "chat-sse-v1",
            "timeout_phase": "response_headers",
            "response_bytes": 200,
            "elapsed_seconds": 3.0,
            "reasoning_characters": 50,
            "content_characters": 0,
            "base_url": "https://PRIVATE.invalid",
            "credential": "PRIVATE_CREDENTIAL",
        }

        async def complete(self, prompt, data, schema):
            self.calls.append(data)
            raise ProviderError(category, "PRIVATE_PROVIDER_ERROR")

    provider = FailedProvider()
    with pytest.raises(ProviderError):
        asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    app = FastAPI()
    register_model_document_api(app, lambda: engine)
    api = TestClient(app)
    with Session(engine) as db:
        output = db.get(LlmDocumentOutput, output_id)
        assert output.status == db.get(Job, job_id).status == "failed"
        assert output.error_code == f"MODEL_DOCUMENT_POSTPROCESS_{category.upper()}_FAILED"
        assert "格式" not in output.error and "原始响应已在本机保留" not in output.error
        assert output.raw_response == provider.partial_output
        assert output.usage["requests"][0]["status"] == "failed"
        assert output.usage["requests"][0]["usage"]["total_tokens"] == 10
        assert output.usage["requests"][0]["diagnostics"]["reasoning_characters"] == 50
        assert "PRIVATE" not in json.dumps(output.usage) + output.error
    response = api.post(
        f"/api/v1/import-sessions/{session_id}/document-outputs/{output_id}/format-repair",
        json={"allow_network": True},
        headers={"Idempotency-Key": "transport-no-repair"},
    )
    assert response.status_code == 409
    asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    assert len(provider.calls) == 1


def test_contract_diagnostics_never_copy_unknown_fields_values_or_validator_messages(
    tmp_path, monkeypatch
):
    engine, _parse_id, _session_id, job_id, output_id = _queue(
        tmp_path, monkeypatch, "paper_reading"
    )
    notes = {
        "slots": {
            "1": {"PRIVATE_UNKNOWN_KEY": "PRIVATE_FIELD_VALUE"},
            "2": {"PRIVATE_UNKNOWN_KEY": "PRIVATE_FIELD_VALUE"},
        },
        "paper_argument": {},
    }
    with pytest.raises(ProviderError):
        asyncio.run(
            execute_document_postprocess(
                engine, job_id, tmp_path, provider=Provider(json.dumps(notes))
            )
        )
    with Session(engine) as db:
        output = db.get(LlmDocumentOutput, output_id)
        assert output.error_code == "MODEL_DOCUMENT_POSTPROCESS_CONTRACT_FAILED"
        assert "PRIVATE" in output.raw_response
        assert "PRIVATE" not in json.dumps(output.usage) + output.error
        assert output.usage["validation_errors"]
