"""One observed P13 punctuation defect, never generic JSON or content rewriting."""

import asyncio
import copy
import json

import pytest
import test_knowledge
from researchgraph import reading_pipeline
from researchgraph.extraction import PROMPT_DIR
from researchgraph.extraction_repair import validation_message
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.knowledge_store import digest, text_hash
from researchgraph.models import Job, now
from researchgraph.providers import MockProvider
from researchgraph.reading_contracts import CoreSelectionProposal
from researchgraph.reading_validation import validate_integration, validate_selection
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_reading_extraction import save

seeded = test_knowledge.seeded


def proposal():
    return {
        "document_version_id": "version",
        "input_revision": 7,
        "recommendations": [
            {
                "root_claim_id": "root-one",
                "recommendation": "suggest_core",
                "reasons": ["main_contribution"],
                "rationale": "Original scientific text: 81.3% under stated conditions.",
            }
        ],
        "coverage_gaps": [
            "中文提示保留",
            'A quote " and a backslash \\ remain literal text.',
            "Brackets ] } and commas, inside a string are source text.",
        ],
    }


def missing_final_array_close(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    assert raw.endswith("]}")
    return raw[:-2] + raw[-1]


@pytest.mark.parametrize("whitespace", ["", " \n\t"])
def test_only_final_string_array_closer_is_restored_and_audited(whitespace):
    value = proposal()
    raw = missing_final_array_close(value)
    raw = raw[:-1] + whitespace + "}" + whitespace
    original = str(raw)
    validated, audit = validate_selection(raw)
    assert validated == value and raw == original
    assert len(audit) == 1
    change = audit[0]
    assert change["path"] == "coverage_gaps"
    assert change["rule"] == "close-final-selection-gaps-array-v1"
    assert change["inserted"] == "]"
    offset = int(change["offset"])
    normalized = raw[:offset] + "]" + raw[offset:]
    assert json.loads(normalized) == value
    assert change["raw_sha256"] == text_hash(raw)
    assert change["normalized_sha256"] == text_hash(normalized)
    assert all("scientific" not in str(v) for v in change.values())


def test_correct_json_is_unchanged_without_punctuation_audit():
    value = proposal()
    raw = json.dumps(value, ensure_ascii=False)
    assert validate_selection(raw) == (value, [])


@pytest.mark.parametrize(
    "fault", ["root_duplicate", "nested_duplicate", "escaped_duplicate", "NaN", "Infinity"]
)
def test_syntactically_complete_selection_still_requires_unambiguous_json(fault):
    raw = json.dumps(proposal(), ensure_ascii=False, separators=(",", ":"))
    if fault == "root_duplicate":
        raw = raw.replace(
            '"document_version_id":"version",',
            '"document_version_id":"other","document_version_id":"version",',
        )
    elif fault == "nested_duplicate":
        raw = raw.replace(
            '"root_claim_id":"root-one",',
            '"root_claim_id":"other","root_claim_id":"root-one",',
        )
    elif fault == "escaped_duplicate":
        raw = raw.replace('"input_revision":7,', '"input_revision":6,"input\\u005frevision":7,')
    else:
        raw = raw.replace('"input_revision":7', '"input_revision":' + fault)
    with pytest.raises(ValueError):
        validate_selection(raw)


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "missing_comma",
        "unquoted",
        "two_missing_closers",
        "trailing_comma",
        "eof",
        "other_field",
        "nested_array",
        "duplicate_key",
        "escaped_duplicate_key",
        "nan",
        "infinity",
        "after_final_field",
        "wrong_value_type",
        "missing_root_close",
    ],
)
def test_ambiguous_incomplete_or_nonmatching_json_is_not_repaired(fault):
    value = proposal()
    if fault == "empty":
        value["coverage_gaps"] = []
    elif fault == "nested_array":
        value["coverage_gaps"] = [["Nested structure is not a string gap."]]
    elif fault == "wrong_value_type":
        value["coverage_gaps"] = [17]
    elif fault == "other_field":
        value["warnings"] = value.pop("coverage_gaps")
    raw = missing_final_array_close(value)
    if fault == "missing_comma":
        raw = raw.replace('"中文提示保留",', '"中文提示保留" ', 1)
    elif fault == "unquoted":
        raw = raw.replace('"中文提示保留"', "中文提示保留", 1)
    elif fault == "two_missing_closers":
        raw = raw.replace('}],"coverage_gaps"', '},"coverage_gaps"', 1)
    elif fault == "trailing_comma":
        raw = raw[:-1] + ",}"
    elif fault == "eof":
        raw = raw[:-1]
    elif fault == "duplicate_key":
        raw = raw.replace('"input_revision":7,', '"input_revision":6,"input_revision":7,')
    elif fault == "escaped_duplicate_key":
        raw = raw.replace('"input_revision":7,', '"input_revision":6,"input\\u005frevision":7,')
    elif fault in {"nan", "infinity"}:
        raw = raw.replace(
            '"input_revision":7', '"input_revision":' + ("NaN" if fault == "nan" else "Infinity")
        )
    elif fault == "after_final_field":
        raw = raw[:-1] + ',"extra":"Do not drop this field"}'
    elif fault == "missing_root_close":
        raw = raw[:-1] + "]"
    with pytest.raises(ValueError):
        validate_selection(raw)


@pytest.mark.parametrize("field", ["extra", "recommendation", "duplicate_root"])
def test_restored_syntax_does_not_relax_selection_schema(field):
    value = proposal()
    if field == "extra":
        value = {"unknown_science": "Cannot silently discard", **value}
    elif field == "recommendation":
        value["recommendations"][0]["recommendation"] = "invented_fact"
    else:
        value["recommendations"].append(copy.deepcopy(value["recommendations"][0]))
    with pytest.raises(ValueError):
        validate_selection(missing_final_array_close(value))


def test_rule_is_not_applied_to_integration_or_to_general_missing_punctuation():
    integration = {
        "contract_version": "reading-integration-1.0",
        "document_version_id": "version",
        "input_revision": 7,
        "units": [],
        "warnings": ["Do not close this other-stage array"],
    }
    with pytest.raises(ValueError):
        validate_integration(missing_final_array_close(integration))
    raw = json.dumps(proposal(), ensure_ascii=False).replace(
        ', "coverage_gaps"', ' "coverage_gaps"'
    )
    with pytest.raises(ValueError):
        validate_selection(raw)


def test_old_failed_selection_response_is_revalidated_without_model_call_and_raw_is_immutable(
    seeded,
):
    _, engine, eid = seeded
    save(engine, eid)
    with Session(engine) as session:
        root = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "claim"))
        root_id, root_content = root.id, root.payload
    value = proposal()
    value["recommendations"][0]["root_claim_id"] = root_id
    raw = missing_final_array_close(value)
    prompt = "P13_reading_selection_v3"
    request = {
        "document_version_id": "version",
        "input_revision": 7,
        "units": [{"root_claim_id": root_id, "root": root_content, "members": []}],
        "density": "standard",
        "coverage_gaps": [],
    }
    schema = CoreSelectionProposal.model_json_schema()
    manifest = {"pipeline": "paper-reading-v1", "schema_hash": digest(schema)}

    class NeverCall(MockProvider):
        async def complete(self, prompt, data, schema):
            raise AssertionError("A recoverable saved response must not call the model again")

    provider = NeverCall()
    with Session(engine) as session, session.begin():
        session.add(
            ModelRun(
                id="failed-selection",
                job_id="job",
                document_version_id="version",
                provider=provider.name,
                model=provider.model,
                prompt_name=prompt,
                prompt_hash=text_hash((PROMPT_DIR / (prompt + ".md")).read_text(encoding="utf-8")),
                schema_version="reading-1.0",
                input_hash=digest(request),
                raw_output=raw,
                status="validation_failed",
                error="Expecting ',' delimiter",
                parameters={"temperature": 0, "timeout_seconds": 35, "input_manifest": manifest},
                created_at=now(),
            )
        )
    for _ in range(2):
        run_id, result = asyncio.run(
            reading_pipeline.model_stage(
                engine,
                "job",
                provider,
                prompt,
                CoreSelectionProposal,
                request,
            )
        )
        assert run_id == "failed-selection" and result == value
    with Session(engine) as session:
        run = session.get(ModelRun, "failed-selection")
        assert run.raw_output == raw
        audit = run.parameters["integration_normalization"]
        assert len(audit) == 1 and audit[0]["rule"] == "close-final-selection-gaps-array-v1"
        assert session.scalar(select(func.count()).select_from(ModelRun)) == 2
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 4


def test_json_error_message_is_chinese_and_does_not_echo_private_document_content():
    raw = '{"PRIVATE_SCIENTIFIC_TEXT":["x"}'
    try:
        json.loads(raw)
    except json.JSONDecodeError as error:
        message = validation_message(error)
    assert "PRIVATE_SCIENTIFIC_TEXT" not in message and raw not in message
    assert "JSON" in message and any("\u4e00" <= char <= "\u9fff" for char in message)


def test_finish_reuses_saved_failed_selection_and_clears_error_on_checkpoint(seeded, monkeypatch):
    from researchgraph import reading_stage_validation

    _, engine, eid = seeded
    save(engine, eid)
    with Session(engine) as session, session.begin():
        session.get(Job, "job").payload = {"document_version_id": "version"}
        original_nodes = session.scalar(select(func.count()).select_from(KnowledgeNode))

    class MissingArrayProvider(MockProvider):
        def __init__(self):
            self.calls = []

        async def complete(self, prompt, data, schema):
            self.calls.append(schema["title"])
            raw = await super().complete(prompt, data, schema)
            if schema["title"] == "CoreSelectionProposal":
                value = json.loads(raw)
                value["coverage_gaps"] = ["Synthetic gap retained verbatim"]
                return missing_final_array_close(value)
            return raw

    def old_validation(raw):
        json.loads(raw)
        raise AssertionError("Expected the historical syntax failure")

    provider = MissingArrayProvider()
    monkeypatch.setattr(reading_stage_validation, "validate_selection", old_validation)
    with pytest.raises(ValueError, match="JSON"):
        asyncio.run(reading_pipeline.finish_reading(engine, "job", provider))
    with Session(engine) as session:
        run = session.scalar(select(ModelRun).where(ModelRun.prompt_name.like("P13%")))
        assert run.status == "validation_failed" and run.error
        run_id, original_raw = run.id, run.raw_output
        original_run_count = session.scalar(select(func.count()).select_from(ModelRun))

    monkeypatch.setattr(reading_stage_validation, "validate_selection", validate_selection)
    asyncio.run(reading_pipeline.finish_reading(engine, "job", provider))
    assert provider.calls == ["PaperIntegrationProposal", "CoreSelectionProposal"]
    with Session(engine) as session:
        run = session.get(ModelRun, run_id)
        assert run.status == "succeeded" and run.error is None and run.finished_at
        assert run.raw_output == original_raw
        assert run.parameters["integration_normalization"][0]["inserted"] == "]"
        assert session.scalar(select(func.count()).select_from(ModelRun)) == original_run_count
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == original_nodes
        assert session.get(Job, "job").status == "succeeded"
