"""Terminal response/cache checks use synthetic sources and never call a provider."""

import copy
import json

import pytest
import test_knowledge
from researchgraph.extraction import PROMPT_DIR, reusable_model_run
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeStore, digest, text_hash
from researchgraph.models import now
from researchgraph.providers import MockProvider
from researchgraph.reading_stage_validation import (
    StageValidationError,
    record_validation_failure,
    validate_stage,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_reading_extraction import candidate_batch, save

seeded = test_knowledge.seeded


def extraction_input(engine, eid):
    with Session(engine) as session:
        return {
            "document_version_id": "version",
            "chunk_id": "chunk",
            "allowed_evidence": [{"id": "ev0001", "text": session.get(EvidenceSpan, eid).quote}],
        }, {"evidence_aliases": {"ev0001": eid}}


def stage_inputs(engine, eid):
    save(engine, eid)
    with Session(engine) as session:
        reading = KnowledgeStore(session).reading()
        nodes = reading.nodes("version")
        snapshot = reading.snapshot("version")
        root = next(node for node in nodes if node.kind == "claim")
        integration = {
            "document_version_id": "version",
            "input_revision": int(snapshot[:12], 16),
            "root_claim_ids": [root.id],
            "candidates": [
                {"id": node.id, "content": node.payload, "evidence_ids": [eid]} for node in nodes
            ],
            "allowed_evidence": [{"id": eid, "text": session.get(EvidenceSpan, eid).quote}],
        }
        selection = {
            "document_version_id": "version",
            "input_revision": int(snapshot[:12], 16),
            "units": [
                {
                    "root_claim_id": root.id,
                    "root": root.payload,
                    "members": [
                        {"id": node.id, "content": node.payload}
                        for node in nodes
                        if node.id != root.id
                    ],
                }
            ],
        }
        return snapshot, integration, selection


def integration_response(data):
    return {
        "contract_version": "reading-integration-1.0",
        "document_version_id": data["document_version_id"],
        "input_revision": data["input_revision"],
        "units": [
            {
                "local_ref": "unit-one",
                "root_claim_id": root,
                "member_ids": [],
                "rationale": "Synthetic complete context",
            }
            for root in data["root_claim_ids"]
        ],
        "associations": [],
        "duplicates": [],
        "warnings": [],
    }


def selection_response(data):
    return {
        "document_version_id": data["document_version_id"],
        "input_revision": data["input_revision"],
        "recommendations": [
            {
                "root_claim_id": unit["root_claim_id"],
                "recommendation": "suggest_core",
                "reasons": ["main_contribution"],
                "rationale": "Synthetic evidence only",
            }
            for unit in data["units"]
        ],
        "coverage_gaps": ["A complete observed limitation."],
    }


@pytest.mark.parametrize(
    "fault,category",
    [
        ("json", "protocol"),
        ("schema", "schema"),
        ("version", "context"),
        ("chunk", "context"),
        ("evidence", "evidence"),
    ],
)
def test_p02_full_terminal_validation_classifies_response_failures(seeded, fault, category):
    _, engine, eid = seeded
    data, manifest = extraction_input(engine, eid)
    batch = candidate_batch("ev0001")
    if fault == "schema":
        batch["items"][0]["unknown_science"] = "Do not discard"
    elif fault == "version":
        batch["document_version_id"] = "invented"
    elif fault == "chunk":
        batch["chunk_id"] = "invented"
    elif fault == "evidence":
        batch["items"][0]["evidence_ids"] = ["outside"]
    raw = "{" if fault == "json" else json.dumps(batch)
    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(session, "P02", raw, data, input_manifest=manifest)
    assert caught.value.category == category and caught.value.response_invalid
    assert "Do not discard" not in str(caught.value)


def test_p02_keeps_lossless_null_note_and_duplicate_recovery_without_writes(seeded):
    _, engine, eid = seeded
    data, manifest = extraction_input(engine, eid)
    batch = candidate_batch("ev0001")
    batch["items"][0]["kind_note_unused"] = None
    batch["items"].append(copy.deepcopy(batch["items"][0]))
    raw = json.dumps(batch)
    with Session(engine) as session:
        before = list(session.scalars(select(KnowledgeNode)))
        result = validate_stage(session, "P02", raw, data, input_manifest=manifest)
        assert len(result.value["items"]) == 4
        assert len(result.removed_duplicates) == 1 and len(result.normalization) == 2
        assert list(session.scalars(select(KnowledgeNode))) == before
        assert session.get(ModelRun, "run").raw_output == '{"original":true}'
        assert not session.new and not session.dirty and not session.deleted
    assert json.loads(raw) == batch


@pytest.mark.parametrize("fault", ["quote", "offset", "hash", "manifest"])
def test_stale_source_inputs_stop_instead_of_becoming_paid_retries(seeded, fault):
    _, engine, eid = seeded
    data, manifest = extraction_input(engine, eid)
    if fault == "quote":
        data["allowed_evidence"][0]["text"] = "Changed source"
    elif fault == "manifest":
        manifest["evidence_aliases"]["ev0002"] = eid
    else:
        with Session(engine) as session, session.begin():
            span = session.get(EvidenceSpan, eid)
            if fault == "offset":
                span.end_offset -= 1
            else:
                span.text_sha256 = "0" * 64
    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(
            session, "P02", json.dumps(candidate_batch("ev0001")), data, input_manifest=manifest
        )
    assert caught.value.category in {"context", "evidence"}
    assert not caught.value.response_invalid


@pytest.mark.parametrize("stage", ["P12", "P13"])
@pytest.mark.parametrize("fault", ["version", "revision", "snapshot"])
def test_stage_version_revision_and_live_snapshot_are_all_required(seeded, stage, fault):
    _, engine, eid = seeded
    snapshot, integration, selection = stage_inputs(engine, eid)
    data = integration if stage == "P12" else selection
    value = integration_response(data) if stage == "P12" else selection_response(data)
    if fault == "version":
        value["document_version_id"] = "invented"
    elif fault == "revision":
        value["input_revision"] += 1
    else:
        snapshot = "0" * 64
    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(session, stage, json.dumps(value), data, snapshot=snapshot)
    assert caught.value.category == "context"
    assert caught.value.response_invalid is (fault != "snapshot")


def test_p12_quarantines_outside_candidates_but_never_outside_evidence(seeded):
    _, engine, eid = seeded
    snapshot, data, _ = stage_inputs(engine, eid)
    value = integration_response(data)
    value["units"][0]["member_ids"] = ["invented"]
    root = data["root_claim_ids"][0]
    value["associations"] = [
        {
            "source_id": root,
            "target_id": "invented",
            "relation": "SUPPORTED_BY",
            "evidence_ids": [eid],
            "rationale": "Do not guess an ID",
        }
    ]
    with Session(engine) as session:
        result = validate_stage(session, "P12", json.dumps(value), data, snapshot=snapshot)
        assert len(result.quarantined) == 2
        assert not result.value["units"][0]["member_ids"]
        assert not result.value["associations"]
        assert not session.new and not session.dirty
    value["associations"][0]["evidence_ids"] = ["invented"]
    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(session, "P12", json.dumps(value), data, snapshot=snapshot)
    assert caught.value.category == "evidence" and caught.value.response_invalid


@pytest.mark.parametrize("fault", ["missing_root", "invented_root", "wrong_content", "source"])
def test_p13_exact_roots_and_candidate_source_are_terminal_not_only_dto(seeded, fault):
    _, engine, eid = seeded
    snapshot, _, data = stage_inputs(engine, eid)
    value = selection_response(data)
    if fault == "missing_root":
        value["recommendations"] = []
    elif fault == "invented_root":
        value["recommendations"][0]["root_claim_id"] = "invented"
    elif fault == "wrong_content":
        data["units"][0]["root"] = {**data["units"][0]["root"], "statement": "invented"}
    else:
        with Session(engine) as session, session.begin():
            session.get(EvidenceSpan, eid).end_offset -= 1
        # Verify anchor validation independently of the outer snapshot check.
        snapshot = None
    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(session, "P13", json.dumps(value), data, snapshot=snapshot)
    assert caught.value.response_invalid is (fault in {"missing_root", "invented_root"})


def add_cached_run(engine, run_id, prompt, data, manifest, raw, status, created_at):
    provider = MockProvider()
    with Session(engine) as session, session.begin():
        session.add(
            ModelRun(
                id=run_id,
                job_id="job",
                document_version_id="version",
                provider=provider.name,
                model=provider.model,
                prompt_name=prompt,
                prompt_hash=text_hash((PROMPT_DIR / (prompt + ".md")).read_text(encoding="utf-8")),
                schema_version="reading-1.0",
                input_hash=digest(data),
                parameters={
                    **getattr(provider, "parameters", {"temperature": 0, "timeout_seconds": 35}),
                    "input_manifest": manifest,
                },
                status=status,
                raw_output=raw,
                created_at=created_at,
            )
        )


@pytest.mark.parametrize("status", ["received", "succeeded", "validation_failed"])
def test_all_cache_statuses_require_final_context_and_keep_raw_when_rejected(seeded, status):
    _, engine, eid = seeded
    _, _, data = stage_inputs(engine, eid)
    prompt, manifest = "P13_reading_selection_v3", {"pipeline": "paper-reading-v1"}
    good = json.dumps(selection_response(data))
    bad = json.loads(good)
    bad["recommendations"] = []
    raw = json.dumps(bad)
    add_cached_run(engine, "good", prompt, data, manifest, good, "received", "2026-01-01")
    add_cached_run(engine, "bad", prompt, data, manifest, raw, status, "2026-02-01")
    result = reusable_model_run(
        engine, "job", MockProvider(), prompt, data, manifest, include_invalid=True
    )
    assert result == ("good", good)
    with Session(engine) as session:
        run = session.get(ModelRun, "bad")
        assert run.status == "validation_failed" and run.raw_output == raw
        assert run.parameters["stage_validation"]["category"] == "context"
        assert run.parameters["stage_validation"]["raw_sha256"] == text_hash(raw)
    assert reusable_model_run(
        engine, "job", MockProvider(), prompt, data, manifest, include_invalid=True
    ) == ("good", good)


def test_exact_p13_syntax_recovery_is_reusable_with_unmodified_model_output(seeded):
    _, engine, eid = seeded
    _, _, data = stage_inputs(engine, eid)
    prompt, manifest = "P13_reading_selection_v3", {"pipeline": "paper-reading-v1"}
    raw = json.dumps(selection_response(data), separators=(",", ":"))
    raw = raw[:-2] + raw[-1]
    add_cached_run(engine, "recover", prompt, data, manifest, raw, "validation_failed", now())
    assert reusable_model_run(
        engine, "job", MockProvider(), prompt, data, manifest, include_invalid=True
    ) == ("recover", raw)
    with Session(engine) as session:
        result = validate_stage(session, "P13", raw, data)
        assert result.normalization[0]["rule"] == "close-final-selection-gaps-array-v1"
        assert session.get(ModelRun, "recover").raw_output == raw


@pytest.mark.parametrize("status", ["received", "succeeded", "validation_failed"])
def test_cache_context_change_is_propagated_without_rewriting_historical_outcome(seeded, status):
    _, engine, eid = seeded
    snapshot, _, data = stage_inputs(engine, eid)
    prompt, manifest = "P13_reading_selection_v3", {"pipeline": "paper-reading-v1"}
    raw = json.dumps(selection_response(data))
    add_cached_run(engine, "stale", prompt, data, manifest, raw, status, now())
    with Session(engine) as session:
        run = session.get(ModelRun, "stale")
        historical_outcome = (run.status, run.error, run.finished_at)
    with Session(engine) as session, session.begin():
        session.get(EvidenceSpan, eid).end_offset -= 1

    def validate(raw):
        with Session(engine) as session:
            return validate_stage(session, "P13", raw, data, snapshot=snapshot)

    with pytest.raises(StageValidationError) as caught:
        reusable_model_run(
            engine,
            "job",
            MockProvider(),
            prompt,
            data,
            manifest,
            include_invalid=True,
            validator=validate,
        )
    assert not caught.value.response_invalid
    with Session(engine) as session:
        run = session.get(ModelRun, "stale")
        assert run.parameters["stage_validation"]["code"] == "SNAPSHOT_CHANGED"
        assert run.raw_output == raw
        assert (run.status, run.error, run.finished_at) == historical_outcome


def test_wire_callback_is_validated_after_trusted_binding_and_does_not_mutate_raw(seeded):
    _, engine, eid = seeded
    data, manifest = extraction_input(engine, eid)
    supplied = json.dumps(
        {"items": candidate_batch("ev0001")["items"], "links": candidate_batch("ev0001")["links"]}
    )

    def bind(raw):
        return json.dumps(
            {
                "contract_version": "reading-extraction-1.0",
                "document_version_id": data["document_version_id"],
                "chunk_id": data["chunk_id"],
                **json.loads(raw),
            }
        )

    with Session(engine) as session:
        result = validate_stage(
            session, "P02", supplied, data, input_manifest=manifest, wire_validator=bind
        )
    assert len(result.value["items"]) == 4
    assert "document_version_id" not in json.loads(supplied)


@pytest.mark.parametrize("fault", ["duplicate", "constant", "missing_key"])
def test_selection_protocol_failure_is_classified_without_private_echo(seeded, fault):
    _, engine, eid = seeded
    _, _, data = stage_inputs(engine, eid)
    raw = json.dumps(selection_response(data), separators=(",", ":"))
    if fault == "duplicate":
        raw = raw.replace(
            '"document_version_id":"version",',
            '"document_version_id":"private","document_version_id":"version",',
        )
    elif fault == "constant":
        raw = raw.replace(str(data["input_revision"]), "NaN")
    else:
        del_value = selection_response(data)
        del del_value["recommendations"]
        raw = json.dumps(del_value)
    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(session, "P13", raw, data)
    assert caught.value.category == ("schema" if fault == "missing_key" else "protocol")
    assert "private" not in str(caught.value)


def test_failure_recorder_changes_only_run_diagnostics_and_rejects_wrong_raw(seeded):
    _, engine, _ = seeded
    error = StageValidationError("protocol", "INVALID_JSON", "模型响应不是有效JSON")
    raw = '{"original":true}'
    with Session(engine) as session:
        before = session.get(ModelRun, "run")
        identity = (before.prompt_hash, before.input_hash, before.provider, before.model)
    record_validation_failure(engine, "run", error, {"trusted": "input"}, raw)
    with Session(engine) as session:
        after = session.get(ModelRun, "run")
        assert identity == (after.prompt_hash, after.input_hash, after.provider, after.model)
        assert after.status == "validation_failed" and after.raw_output == raw
        assert after.parameters["stage_validation"]["category"] == "protocol"
        assert after.parameters["stage_validation"]["input_hash"] == digest({"trusted": "input"})
        diagnostics = copy.deepcopy(after.parameters)
    with pytest.raises(StageValidationError, match="模型记录已变化"):
        record_validation_failure(engine, "run", error, {}, "wrong response")
    with Session(engine) as session:
        after = session.get(ModelRun, "run")
        assert after.parameters == diagnostics and after.raw_output == raw


def test_failure_recorder_preserves_historical_success_for_stale_trusted_input(seeded):
    _, engine, _ = seeded
    with Session(engine) as session:
        run = session.get(ModelRun, "run")
        historical_outcome = (run.status, run.error, run.finished_at, run.raw_output)
    error = StageValidationError(
        "context", "SNAPSHOT_CHANGED", "候选快照已变化", response_invalid=False
    )
    record_validation_failure(engine, "run", error, {}, historical_outcome[-1])
    with Session(engine) as session:
        run = session.get(ModelRun, "run")
        assert (run.status, run.error, run.finished_at, run.raw_output) == historical_outcome
        assert run.parameters["stage_validation"]["response_invalid"] is False


def test_missing_full_candidate_evidence_is_stale_input_not_model_schema_failure(seeded):
    _, engine, eid = seeded
    _, data, _ = stage_inputs(engine, eid)
    data["candidates"][0]["evidence_ids"] = []
    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(session, "P12", json.dumps(integration_response(data)), data)
    assert caught.value.category == "evidence" and not caught.value.response_invalid


@pytest.mark.parametrize(
    "fault,diagnostic",
    [
        ("known_missing", "known 条件必须提供一个有证据的 value，且 alternatives 必须为空"),
        ("known_alternatives", "known 条件必须提供一个有证据的 value，且 alternatives 必须为空"),
        (
            "known_missing_alternatives",
            "known 条件必须提供一个有证据的 value，且 alternatives 必须为空",
        ),
        ("unknown_value", "unknown/not_applicable 条件不能声明 value、unit 或 alternatives"),
        ("not_applicable_unit", "unknown/not_applicable 条件不能声明 value、unit 或 alternatives"),
        (
            "conflicting_single",
            "conflicting 条件必须提供至少两个有证据的 alternatives，且不能声明单一 value",
        ),
        (
            "conflicting_value",
            "conflicting 条件必须提供至少两个有证据的 alternatives，且不能声明单一 value",
        ),
    ],
)
def test_condition_validation_reports_safe_path_type_and_fixed_state_rule(
    seeded, fault, diagnostic
):
    _, engine, eid = seeded
    data, manifest = extraction_input(engine, eid)
    batch = candidate_batch("ev0001")
    condition = batch["items"][3]
    alternative = {
        "value": {"original": "Synthetic alternative", "language": "en"},
        "evidence_ids": ["ev0001"],
    }
    if fault == "known_missing":
        condition.pop("value")
    elif fault == "known_alternatives":
        condition["alternatives"] = [alternative, copy.deepcopy(alternative)]
    elif fault == "known_missing_alternatives":
        condition.pop("value")
        condition["alternatives"] = [copy.deepcopy(alternative) for _ in range(3)]
    elif fault == "unknown_value":
        condition["state"] = "unknown"
    elif fault == "not_applicable_unit":
        condition.update(state="not_applicable", value=None, unit="agents")
    elif fault == "conflicting_single":
        condition.update(state="conflicting", value=None, alternatives=[alternative])
    else:
        condition.update(
            state="conflicting", alternatives=[alternative, copy.deepcopy(alternative)]
        )
    raw = json.dumps(batch)
    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(session, "P02", raw, data, input_manifest=manifest)
    error = caught.value
    assert (error.category, error.code, error.response_invalid) == ("schema", "INVALID_DTO", True)
    assert "items.3.Condition (value_error)" in str(error)
    assert diagnostic in str(error)
    assert json.loads(raw) == batch  # No condition repair, mutation or semantic conversion.
    assert "Synthetic alternative" not in str(error)
    with Session(engine) as session:
        assert session.get(ModelRun, "run").raw_output == '{"original":true}'
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 0


def test_schema_diagnostics_bound_count_and_redact_unknown_keys_and_values(seeded):
    _, engine, eid = seeded
    data, manifest = extraction_input(engine, eid)
    batch = candidate_batch("ev0001")
    private_key, private_value = "secret-api-key-" + "x" * 400, "private-note-and-token-value"
    for item in batch["items"]:
        for i in range(6):
            item[f"{private_key}-{i}"] = private_value
    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(session, "P02", json.dumps(batch), data, input_manifest=manifest)
    message = str(caught.value)
    assert message.count("extra_forbidden") == 4 and "另有 20 项错误" in message
    assert "items.0.Claim.<未允许字段>" in message
    assert "secret-api-key" not in message and private_value not in message
    assert len(message) < 1000


def test_schema_diagnostics_never_reflect_arbitrary_validator_message_or_context(seeded):
    from pydantic import ValidationError

    _, engine, eid = seeded
    data, manifest = extraction_input(engine, eid)
    private = "private-validator-message-and-token"

    def binder(_raw):
        raise ValidationError.from_exception_data(
            "Synthetic",
            [
                {
                    "type": "value_error",
                    "loc": ("items", 2, "Condition"),
                    "input": private,
                    "ctx": {"error": ValueError(private)},
                }
            ],
        )

    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(session, "P02", "{}", data, input_manifest=manifest, wire_validator=binder)
    assert str(caught.value) == "模型响应未通过阶段 Schema 校验：items.2.Condition (value_error)"
    assert private not in str(caught.value) and caught.value.code == "INVALID_DTO"


def test_p12_wire_schema_diagnostics_show_missing_fields_and_redact_unknown_code(seeded):
    from researchgraph.reading_finish_wire import bind_integration

    _, engine, eid = seeded
    snapshot, data, _ = stage_inputs(engine, eid)
    valid = {
        "candidate_refs": ["n1", "n2"],
        "representative_ref": "n1",
        "rationale": "Synthetic duplicate",
    }
    private = "private-provider-response-content"
    value = {
        "associations": [],
        "duplicates": [copy.deepcopy(valid) for _ in range(4)]
        + [{"representative_ref": "n1", "code": private}],
        "warnings": [],
    }
    raw = json.dumps(value)

    def bind(text):
        return json.dumps(
            bind_integration(json.loads(text), {"candidate_aliases": {}, "evidence_aliases": {}})
        )

    with Session(engine) as session, pytest.raises(StageValidationError) as caught:
        validate_stage(session, "P12", raw, data, snapshot=snapshot, wire_validator=bind)
    message = str(caught.value)
    assert "duplicates.4.candidate_refs (missing)" in message
    assert "duplicates.4.rationale (missing)" in message
    assert "duplicates.4.<未允许字段> (extra_forbidden)" in message
    assert private not in message and "code" not in message
    assert (caught.value.category, caught.value.code, caught.value.response_invalid) == (
        "schema",
        "INVALID_DTO",
        True,
    )
    assert json.loads(raw) == value
