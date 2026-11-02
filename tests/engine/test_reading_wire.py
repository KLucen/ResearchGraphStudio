import asyncio
import copy
import json

import httpx
import pytest
import test_knowledge
from researchgraph import reading_wire, unified_extraction
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.model_adapters import new_task_parameters
from researchgraph.models import Job
from researchgraph.providers import ConfiguredProvider, MockProvider, ProviderError
from researchgraph.reading_contracts import KnowledgeExtractionBatch
from researchgraph.reading_validation import validate_batch
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_reading_extraction import candidate_batch

seeded = test_knowledge.seeded


def compact_sample():
    canonical = candidate_batch("ev")
    # Duplicate summaries are optional; distinct details must survive unchanged.
    canonical["items"][0]["summary"] = copy.deepcopy(canonical["items"][0]["statement"])
    canonical["items"][0]["statement"]["zh"] = "仅在三个智能体条件下达到81%，不是普遍保证。"
    canonical["items"][0]["summary"] = copy.deepcopy(canonical["items"][0]["statement"])
    canonical["items"][2]["summary"] = {
        "original": "Do not extrapolate this observation.",
        "language": "en",
    }
    canonical["items"][2]["baseline"] = {"original": "对照结果", "language": "zh", "zh": None}
    return canonical, reading_wire.compact_fixture(canonical)


def test_compact_output_preserves_scientific_fields_and_explicit_language_overrides():
    canonical, wire = compact_sample()
    assert "summary" not in wire["items"][0]
    assert wire["items"][2]["summary"]["original"] == "Do not extrapolate this observation."
    assert wire["items"][2]["baseline"]["language"] == "zh"
    before = copy.deepcopy(wire)
    batch, isolated = validate_batch(json.dumps(wire), {"ev"}, compact=True)
    assert not isolated
    assert batch == KnowledgeExtractionBatch.model_validate(canonical)
    assert wire == before and reading_wire.expand(wire) == canonical
    # New transport does not weaken the frozen old domain Schema.
    with pytest.raises(ValueError):
        validate_batch(json.dumps(wire), {"ev"})


@pytest.mark.parametrize(
    "fault",
    [
        "extra",
        "unknown_evidence",
        "null_language",
        "missing_statement",
        "null_summary",
        "condition_value",
        "missing_header",
        "wrong_kind",
    ],
)
def test_compact_transport_still_rejects_invalid_science_and_fields(fault):
    _, wire = compact_sample()
    if fault == "extra":
        wire["items"][0]["findings_placeholder"] = None
    elif fault == "unknown_evidence":
        wire["items"][0]["evidence_ids"] = ["outside"]
    elif fault == "null_language":
        wire["items"][0]["statement"]["language"] = None
    elif fault == "missing_statement":
        del wire["items"][0]["statement"]
    elif fault == "null_summary":
        wire["items"][0]["summary"] = None
    elif fault == "condition_value":
        wire["items"][-1]["state"] = "unknown"
    elif fault == "missing_header":
        del wire["source_language"]
    else:
        wire["items"][0]["kind"] = ["Claim"]
    with pytest.raises(ValueError):
        validate_batch(json.dumps(wire), {"ev"}, compact=True)


def test_compact_dedup_compares_original_wire_objects_not_expanded_defaults():
    _, wire = compact_sample()
    duplicate = copy.deepcopy(wire["items"][0])
    duplicate["summary"] = copy.deepcopy(duplicate["statement"])
    wire["items"].append(duplicate)
    with pytest.raises(ValueError, match="内容不同"):
        validate_batch(json.dumps(wire), {"ev"}, compact=True)


def test_source_text_strings_expand_only_in_schema_defined_fields_with_audit():
    _, wire = compact_sample()
    wire["items"][2]["baseline"] = "81.00% (95% CI 80–82%); three agents only"
    wire["items"][-1].update(
        state="conflicting",
        alternatives=[
            {"value": "3 agents", "evidence_ids": ["ev"]},
            {"value": "4 agents", "evidence_ids": ["ev"]},
        ],
    )
    wire["items"][-1].pop("value")
    changes = []
    batch, _ = validate_batch(json.dumps(wire), {"ev"}, compact=True, wire_changes=changes)
    assert batch.items[2].baseline.original == wire["items"][2]["baseline"]
    assert batch.items[2].baseline.language == "en" and batch.items[2].baseline.zh is None
    assert batch.items[-1].alternatives[1].value.original == "4 agents"
    assert {"path": "items.2.baseline", "rule": "source-text-string"} in changes
    wire["items"][2]["baseline"] = 81
    with pytest.raises(ValueError):
        validate_batch(json.dumps(wire), {"ev"}, compact=True)


def test_compact_pipeline_preserves_raw_response_and_store_fields_in_new_session(
    seeded, monkeypatch
):
    _, engine, _ = seeded
    with Session(engine) as session, session.begin():
        session.get(Job, "job").payload = {
            "document_version_id": "version",
            "pipeline": "paper-reading-v1",
            "provider": "mock",
            "allow_network": False,
        }
    calls = []

    class Captured(MockProvider):
        async def complete(self, prompt, data, schema):
            calls.append(schema)
            return await super().complete(prompt, data, schema)

    monkeypatch.setattr(unified_extraction, "provider_for", lambda *args: Captured())
    asyncio.run(unified_extraction.run_unified_extraction(engine, "job", reading=True))
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert job.status == "succeeded"
        assert job.payload["unified_plan"]["prompt_name"] == reading_wire.PROMPT
        run = session.scalar(select(ModelRun).where(ModelRun.prompt_name == reading_wire.PROMPT))
        raw = json.loads(run.raw_output)
        assert raw["wire_format"] == reading_wire.FORMAT
        assert "summary" not in raw["items"][0]
        assert run.parameters["reading_wire"]["canonical_contract"] == "reading-extraction-1.0"
        claim = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "claim"))
        assert claim.payload["summary"] == claim.payload["statement"]
        assert claim.payload["statement"]["language"] == "en"
    assert len(calls) == 3  # One P02 plus P12 and P13; no extra translation request.


@pytest.mark.parametrize("finish", ["stop", "length"])
def test_endpoint_maximum_is_used_and_truncation_never_becomes_a_schema_failure(
    monkeypatch, finish
):
    requests = []

    def response(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": finish, "message": {"content": '{"items":[]}'}}],
                "usage": {"prompt_tokens": 6000, "completion_tokens": 70000, "total_tokens": 76000},
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(response))
    )
    endpoint, model = "https://tokenhub.tencentmaas.com/plan/v3", "deepseek-v4.1-flash"
    provider = ConfiguredProvider(
        base_url=endpoint,
        model=model,
        parameters=new_task_parameters(endpoint, model, {"max_output_tokens": 8192}, "extraction"),
    )
    provider.capabilities_checked = True
    if finish == "length":
        with pytest.raises(ProviderError) as error:
            asyncio.run(provider.complete("JSON", {}, reading_wire.output_schema()))
        assert error.value.category == "output_limit"
    else:
        assert (
            asyncio.run(provider.complete("JSON", {}, reading_wire.output_schema()))
            == '{"items":[]}'
        )
    assert requests[0]["max_tokens"] == 393216
    assert requests[0]["thinking"]["type"] == "disabled"
    assert provider.usage["completion_tokens"] == 70000


def test_known_smaller_context_reserves_input_before_requesting_output():
    endpoint, model = "https://tokenhub.tencentmaas.com/plan/v3", "deepseek-v4.1-flash"
    params = new_task_parameters(
        endpoint,
        model,
        {
            "capabilities": {
                "max_output_tokens": 393216,
                "context_window": 16384,
                "source": "endpoint_metadata",
            }
        },
        "extraction",
    )
    provider = ConfiguredProvider(base_url=endpoint, model=model, parameters=params)
    body = provider._build_body("JSON", {"text": "source" * 100}, {})
    assert 128 < body["max_tokens"] < 16384
