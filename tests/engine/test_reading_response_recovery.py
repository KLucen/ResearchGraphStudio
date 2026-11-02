"""Strict reading DTO recovery without losing source data or repeating model calls."""

import asyncio
import copy
import json

import pytest
import test_knowledge
from pydantic import ValidationError
from researchgraph import reading_validation, unified_extraction
from researchgraph.extraction_repair import validation_message
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun
from researchgraph.knowledge_store import text_hash
from researchgraph.models import Chunk, Job
from researchgraph.providers import MockProvider
from researchgraph.reading_contracts import KnowledgeExtractionBatch
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_reading_extraction import candidate_batch, save

seeded = test_knowledge.seeded


def test_exact_duplicate_keeps_links_and_original_response_and_is_idempotent(seeded):
    _, engine, eid = seeded
    data = candidate_batch(eid)
    data["items"].extend(copy.deepcopy(data["items"][1:]))
    raw = json.dumps(data)
    removed = []
    batch, quarantined = reading_validation.validate_batch(raw, {eid}, removed_duplicates=removed)
    assert len(batch.items) == 4 and len(batch.links) == 3 and not quarantined
    assert removed == [
        {"kept_index": 1, "removed_index": 4},
        {"kept_index": 2, "removed_index": 5},
        {"kept_index": 3, "removed_index": 6},
    ]
    with Session(engine) as session, session.begin():
        session.get(ModelRun, "run").raw_output = raw
    normalized = batch.model_dump(mode="json")
    response = save(engine, eid, normalized)
    assert save(engine, eid, normalized, key="repeat")["node_ids"] == response["node_ids"]
    with Session(engine) as session:
        assert session.get(ModelRun, "run").raw_output == raw
        assert len(list(session.scalars(select(KnowledgeNode)))) == 4


@pytest.mark.parametrize("field", ["summary", "evidence_ids", "default"])
def test_duplicate_number_with_different_content_is_rejected_without_private_text(field):
    data = candidate_batch("ev")
    duplicate = copy.deepcopy(data["items"][0])
    if field == "summary":
        duplicate["summary"]["original"] = "PRIVATE_CHANGED_VALUE"
    elif field == "evidence_ids":
        duplicate["evidence_ids"] = ["other"]
    else:
        # Explicit defaults are not identical to a field omitted from the original response.
        duplicate["uncertainties"] = []
    data["items"].append(duplicate)
    with pytest.raises(ValueError) as caught:
        reading_validation.validate_batch(json.dumps(data), {"ev", "other"})
    assert "第 1 与第 5" in str(caught.value) and "内容不同" in str(caught.value)
    assert "PRIVATE_CHANGED_VALUE" not in str(caught.value)


@pytest.mark.parametrize(
    "fault",
    ["item_extra", "envelope_extra", "link_extra", "evidence", "items_limit", "links_limit"],
)
def test_dedup_and_quarantine_cannot_hide_invalid_fields_or_source(fault):
    data = candidate_batch("ev")
    if fault == "item_extra":
        data["items"][0]["unknown_science"] = None
    elif fault == "envelope_extra":
        data["invented"] = True
    elif fault == "link_extra":
        data["links"][0]["unknown_science"] = None
    elif fault == "evidence":
        data["items"][0]["evidence_ids"] = ["outside"]
    elif fault == "items_limit":
        data["items"] *= 26
    else:
        data["links"] *= 101
    data["items"].append(copy.deepcopy(data["items"][0]))
    with pytest.raises(ValueError):
        reading_validation.validate_batch(json.dumps(data), {"ev"})


def test_failed_cache_requires_source_identity_and_whitelist():
    data = candidate_batch("ev")
    data["items"].append(copy.deepcopy(data["items"][0]))
    raw = json.dumps(data)
    request = {"document_version_id": "version", "chunk_id": "chunk"}
    assert reading_validation.reusable_reading_output(raw, request, {"ev"})
    for key in request:
        assert not reading_validation.reusable_reading_output(
            raw, {**request, key: "other"}, {"ev"}
        )
    assert not reading_validation.reusable_reading_output(raw, request, {"other"})
    assert not reading_validation.reusable_reading_output("invalid JSON", request, {"ev"})


def test_generic_duplicate_schema_error_has_safe_reason():
    data = candidate_batch("ev")
    data["items"].append(copy.deepcopy(data["items"][0]))
    with pytest.raises(ValidationError) as caught:
        KnowledgeExtractionBatch.model_validate(data)
    assert validation_message(caught.value) == "Schema 校验失败：模型重复使用了引用编号"


def test_failed_reading_response_reuses_original_call_and_completed_batch(seeded, monkeypatch):
    _, engine, eid = seeded
    with Session(engine) as session, session.begin():
        first = session.get(EvidenceSpan, eid)
        text = "Our second synthetic method reports accuracy of 82%."
        session.add(
            Chunk(
                id="second",
                revision_id="version",
                page_index=0,
                page_label="1",
                block_index=1,
                text=text,
                bbox=[0.0, 0.0, 100.0, 100.0],
            )
        )
        session.flush()
        session.add(
            EvidenceSpan(
                id="second-evidence",
                document_version_id="version",
                paragraph_id="second",
                section_id=first.section_id,
                page_index=0,
                start_offset=0,
                end_offset=len(text),
                quote=text,
                text_sha256=text_hash(text),
                normalization="identity-v1",
                bbox_list=[[0.0, 0.0, 100.0, 100.0]],
            )
        )
        session.get(Job, "job").payload = {
            "document_version_id": "version",
            "pipeline": "paper-reading-v1",
            "provider": "mock",
            "allow_network": False,
        }
        # An already-started 1.0 task must retain the old output Schema/Prompt.
        session.get(Job, "job").result = {"batches": [{"status": "pending"}, {"status": "pending"}]}

    class DuplicateProvider(MockProvider):
        calls = []

        async def complete(self, prompt, data, schema):
            raw = await super().complete(prompt, data, schema)
            if data.get("contract_version") == "reading-extraction-1.0":
                self.calls.append(data["chunk_id"])
                if len(self.calls) == 2:
                    output = json.loads(raw)
                    output["items"].append(copy.deepcopy(output["items"][-1]))
                    return json.dumps(output)
            return raw

    provider = DuplicateProvider()
    monkeypatch.setattr(unified_extraction, "provider_for", lambda *_: provider)
    monkeypatch.setattr(
        unified_extraction,
        "plan_sections",
        lambda spans, **_: [
            [{"id": s.id, "text": s.quote, "section": s.section_id}] for s in spans
        ],
    )
    fixed_validate = reading_validation.validate_batch

    def old_validate(raw, allowed, **kwargs):
        return KnowledgeExtractionBatch.model_validate_json(raw), []

    monkeypatch.setattr(reading_validation, "validate_batch", old_validate)
    with pytest.raises(ValueError, match="重复使用"):
        asyncio.run(unified_extraction.run_unified_extraction(engine, "job", reading=True))
    with Session(engine) as session:
        assert session.get(Job, "job").result["completed_batches"] == "1"
        first_nodes = {n.id: n.payload for n in session.scalars(select(KnowledgeNode))}
        failed = session.scalar(select(ModelRun).where(ModelRun.status == "validation_failed"))
        failed_id, failed_raw = failed.id, failed.raw_output
    monkeypatch.setattr(reading_validation, "validate_batch", fixed_validate)
    asyncio.run(unified_extraction.run_unified_extraction(engine, "job", reading=True))
    assert len(provider.calls) == 2  # No repeated P02 request for either batch.
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert job.status == "succeeded" and job.result["completed_batches"] == "2"
        run = session.get(ModelRun, failed_id)
        assert run.raw_output == failed_raw and run.status == "succeeded" and run.error is None
        assert run.parameters["reading_normalization"]["removed_items"]
        assert all(
            session.get(KnowledgeNode, key).payload == value for key, value in first_nodes.items()
        )
