"""Production K2→K3 workflows use anonymous papers and deterministic test providers."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
from researchgraph.core import KnowledgeError
from researchgraph.knowledge_connection_models import (
    KnowledgeAnalysisEvent,
    KnowledgeConnectionReport,
    KnowledgeConnectionRequest,
    KnowledgeConnectionRun,
    KnowledgePairCheckpoint,
)
from researchgraph.knowledge_connections import (
    cleanup_library_paper,
    dispatch_pending_analysis,
    queue_auto_connections,
    queue_knowledge_connect,
    recover_knowledge_connections,
    report_view,
    run_knowledge_connect,
    validate_connections,
)
from researchgraph.knowledge_library import ensure_library, publish_version
from researchgraph.knowledge_library_models import LibraryPaper, PaperKnowledgeVersion
from researchgraph.knowledge_tasks import run_knowledge_extract
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.model_document_models import LlmDocumentSegment
from researchgraph.models import Job, now
from researchgraph.providers import ConfiguredProvider
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_knowledge_extraction import SNAPSHOT, FixtureProvider, model_fixture, queued, run_record


def built_papers(tmp_path, count=2):
    versions = []
    originals = []
    for _ in range(count):
        values = model_fixture(tmp_path)
        job_id = queued(values, auto_connect=True)
        asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=FixtureProvider()))
        job, run = run_record(values[0], job_id)
        assert job.status == "succeeded", job.error
        versions.append(run.version_id)
        originals.append(values)
    engine = originals[0][0]
    with Session(engine) as db, db.begin():
        library = ensure_library(db)
        library.settings_json = {**library.settings_json, "scope": "all"}
    return engine, versions, originals


def connection_response(frozen):
    source = next(n for n in frozen["source"]["content"]["graph"]["nodes"] if n["type"] != "PAPER")
    target = frozen["candidates"][0]
    node = next(n for n in target["content"]["graph"]["nodes"] if n["type"] != "PAPER")
    return {
        "schema_version": "knowledge-connections-1",
        "relations": [
            {
                "ref": "r1",
                "target_ref": target["ref"],
                "source_node_id": source["id"],
                "target_node_id": node["id"],
                "type": "RELATED_METHOD",
                "explanation_zh": "双方作者均描述了合成方法，可比较其研究用途。",
                "limitations_zh": "测试样例未建立指标或实验设置等同，不能据此判断性能优劣。",
                "source_ref_ids": [source["source_refs"][0]["source_id"]],
                "target_ref_ids": [node["source_refs"][0]["source_id"]],
            }
        ],
        "summary": [{"text_zh": "两篇论文的方法存在可进一步阅读的联系。", "relation_refs": ["r1"]}],
        "no_relation_reason_zh": None,
    }


class ConnectionProvider(FixtureProvider):
    def __init__(self, response=None, action=None):
        super().__init__(response, action)

    async def complete(self, prompt, data, schema):
        self.calls += 1
        assert "untrusted source data" in prompt
        if self.action:
            self.action()
        if isinstance(self.response, Exception):
            raise self.response
        return self.response if self.response is not None else json.dumps(connection_response(data))


def queue_connection(engine, version, **kwargs):
    with Session(engine) as db, db.begin():
        return queue_knowledge_connect(
            db, version, allow_network=True, model_snapshot=SNAPSHOT, **kwargs
        ).id


def connection_record(engine, job_id):
    with Session(engine) as db:
        job = db.get(Job, job_id)
        run = db.scalar(
            select(KnowledgeConnectionRun).where(KnowledgeConnectionRun.job_id == job_id)
        )
        requests = list(
            db.scalars(
                select(KnowledgeConnectionRequest).where(
                    KnowledgeConnectionRequest.run_id == run.id
                )
            )
        )
        report = db.get(KnowledgeConnectionReport, run.report_id) if run.report_id else None
        return job, run, requests, report


def test_two_papers_extract_compare_and_persist_grounded_report(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    job, run, requests, report = connection_record(engine, job_id)
    assert job.status == run.status == "succeeded", job.error
    assert provider.calls == 1 and len(requests) == 1
    assert requests[0].sent_at and requests[0].raw_response
    assert requests[0].usage_json["total_tokens"] == 300
    assert report.report_json["status"] == "completed"
    assert report.report_json["coverage"]["compared"] == 1
    relation = report.report_json["relations"][0]
    assert relation["basis"] == "AI_ANALYSIS" and relation["limitations_zh"]
    assert relation["source_refs"][0]["quote"] in relation["source_refs"][0]["source"]["text"]
    assert relation["target_refs"][0]["quote"] in relation["target_refs"][0]["source"]["text"]
    with Session(engine) as db:
        assert db.query(KnowledgePairCheckpoint).count() == 1
        assert report_view(db, report)["stale"] is False
    assert queue_connection(engine, versions[1]) == job_id


def test_no_candidates_is_explained_without_network_or_model_configuration(tmp_path):
    engine, versions, _ = built_papers(tmp_path, 1)
    with Session(engine) as db, db.begin():
        job_id = queue_knowledge_connect(db, versions[0], allow_network=False).id
    provider = ConnectionProvider(RuntimeError("No request allowed"))
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    job, _, requests, report = connection_record(engine, job_id)
    assert job.status == "succeeded" and requests == [] and provider.calls == 0
    assert report.report_json["status"] == "no_candidates"
    assert report.report_json["coverage"]["eligible"] == 0


def test_legacy_overview_is_excluded_from_grounded_comparison(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    with Session(engine) as db, db.begin():
        old = db.get(PaperKnowledgeVersion, versions[0])
        publish_version(
            db,
            paper_id=old.source_paper_id,
            source_kind="legacy_overview",
            source_id="legacy",
            source_fingerprint="0" * 64,
            content_json={
                "schema_version": "paper_overview_graph.v1",
                "graph": {"nodes": [], "edges": []},
            },
            source_snapshot_json={},
            evidence_status="legacy",
            schema_version="paper_overview_graph.v1",
        )
    job_id = queue_connection(engine, versions[1])
    provider = ConnectionProvider(RuntimeError("No request allowed"))
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    _, _, requests, report = connection_record(engine, job_id)
    assert provider.calls == 0 and not requests
    assert report.report_json["coverage"]["excluded_legacy"] == 1
    assert report.report_json["status"] == "no_candidates"


@pytest.mark.parametrize(
    "mutation",
    [
        "root",
        "foreign_node",
        "foreign_paper",
        "foreign_ref",
        "empty_ref",
        "duplicate",
        "summary",
        "extra",
        "enum",
        "blank_limit",
    ],
)
def test_connection_validation_rejects_unbound_and_malformed_relations(tmp_path, mutation):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    _, _, requests, _ = connection_record(engine, job_id)
    frozen = requests[0].input_json
    response = connection_response(frozen)
    relation = response["relations"][0]
    if mutation == "root":
        relation["source_node_id"] = next(
            n["id"] for n in frozen["source"]["content"]["graph"]["nodes"] if n["type"] == "PAPER"
        )
    elif mutation == "foreign_node":
        relation["target_node_id"] = str(uuid4())
    elif mutation == "foreign_paper":
        relation["target_ref"] = "p999"
    elif mutation == "foreign_ref":
        relation["target_ref_ids"] = ["s999"]
    elif mutation == "empty_ref":
        relation["source_ref_ids"] = []
    elif mutation == "duplicate":
        response["relations"].append(copy.deepcopy(relation))
    elif mutation == "summary":
        response["summary"][0]["relation_refs"] = ["r999"]
    elif mutation == "extra":
        relation["apply_sql"] = "not allowed"
    elif mutation == "enum":
        relation["type"] = "CONTRADICTS"
    else:
        relation["limitations_zh"] = ""
    with pytest.raises(ValueError):
        validate_connections(json.dumps(response), frozen)
    for raw in ['{"schema_version":"x","schema_version":"y"}', '{"x":NaN}', '{"x":Infinity}']:
        with pytest.raises(ValueError):
            validate_connections(raw, frozen)


def test_source_change_after_queue_stops_before_any_model_request(tmp_path):
    engine, versions, originals = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    with Session(engine) as db, db.begin():
        db.execute(text("PRAGMA reverse_unordered_selects=ON"))
        segment = db.scalar(
            select(LlmDocumentSegment).where(
                LlmDocumentSegment.parse_id == originals[0][2],
                LlmDocumentSegment.chapter_ref == "c0",
            )
        )
        segment.text += " Changed original source."
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    job, run, requests, report = connection_record(engine, job_id)
    assert job.status == "failed" and run.error_code == "KNOWLEDGE_SOURCE_CHANGED"
    assert provider.calls == 0 and requests[0].sent_at is None and report is None


def test_metadata_capacity_failure_does_not_occupy_sent_slot(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])

    class SmallProvider(ConfiguredProvider):
        def __init__(self):
            super().__init__(base_url="https://invalid.test", model="synthetic", key="")
            self.calls = 0

        async def prepare(self):
            self.capabilities = ModelCapabilities(context_window=1024, max_output_tokens=512)

        async def complete(self, prompt, data, schema):
            self.calls += 1
            pytest.fail("Capacity refusal must precede actual request")

    provider = SmallProvider()
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    job, run, requests, _ = connection_record(engine, job_id)
    assert job.status == "failed" and run.error_code == "KNOWLEDGE_CAPACITY_INSUFFICIENT"
    assert provider.calls == 0 and requests[0].sent_at is None


def test_cancelled_queued_job_does_not_permanently_block_purge(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    with Session(engine) as db, db.begin():
        db.get(Job, job_id).status = "cancelled"
        paper_id = db.get(PaperKnowledgeVersion, versions[0]).library_paper_id
        cleanup_library_paper(db, paper_id)
    with Session(engine) as db:
        assert db.query(KnowledgeConnectionRun).count() == 0


def test_received_checkpoint_revalidates_and_publishes_without_resend(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    with Session(engine) as db, db.begin():
        run = db.scalar(
            select(KnowledgeConnectionRun).where(KnowledgeConnectionRun.job_id == job_id)
        )
        request = db.scalar(
            select(KnowledgeConnectionRequest).where(KnowledgeConnectionRequest.run_id == run.id)
        )
        request.status, request.sent_at = "received", now()
        request.raw_response = json.dumps(connection_response(request.input_json))
        db.get(Job, job_id).payload = {"allow_network": False}
    provider = ConnectionProvider(RuntimeError("No network"))
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    job, _, _, report = connection_record(engine, job_id)
    assert provider.calls == 0 and job.status == "succeeded" and report


def test_sent_interruption_does_not_resend_and_explicit_retry_creates_successor(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    first = queue_connection(engine, versions[1])
    with Session(engine) as db, db.begin():
        run = db.scalar(
            select(KnowledgeConnectionRun).where(KnowledgeConnectionRun.job_id == first)
        )
        request = db.scalar(
            select(KnowledgeConnectionRequest).where(KnowledgeConnectionRequest.run_id == run.id)
        )
        request.status, request.sent_at = "sent", now()
    recover_knowledge_connections(engine)
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=provider))
    assert provider.calls == 0 and connection_record(engine, first)[0].status == "failed"
    second = queue_connection(engine, versions[1], retry_failed=True)
    assert second != first
    asyncio.run(run_knowledge_connect(engine, second, tmp_path, provider=provider))
    job, run, _, _ = connection_record(engine, second)
    assert job.status == "succeeded" and provider.calls == 1 and run.previous_run_id


def test_pair_checkpoint_reuses_reverse_comparison_without_network(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    first = queue_connection(engine, versions[1])
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=provider))
    second = queue_connection(engine, versions[0])
    asyncio.run(run_knowledge_connect(engine, second, tmp_path, provider=provider))
    job, _, requests, report = connection_record(engine, second)
    assert job.status == "succeeded" and not requests and provider.calls == 1
    assert report.report_json["coverage"]["compared"] == 1
    assert report.report_json["relations"]


def test_reused_checkpoint_cannot_publish_tampered_report_content(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    first = queue_connection(engine, versions[1])
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=provider))
    old_id = connection_record(engine, first)[3].id
    with Session(engine) as db, db.begin():
        old = db.get(KnowledgeConnectionReport, old_id)
        damaged = copy.deepcopy(old.report_json)
        damaged["relations"][0]["source_refs"][0]["quote"] = "INVENTED QUOTE"
        old.report_json = damaged
    second = queue_connection(engine, versions[0])
    asyncio.run(run_knowledge_connect(engine, second, tmp_path, provider=provider))
    job, _, _, report = connection_record(engine, second)
    assert provider.calls == 1
    assert job.status == "failed" and report is None


def test_report_read_rejects_tampered_frozen_input_even_when_derived_output_matches(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    first = queue_connection(engine, versions[1])
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=ConnectionProvider()))
    with Session(engine) as db, db.begin():
        run = db.scalar(
            select(KnowledgeConnectionRun).where(KnowledgeConnectionRun.job_id == first)
        )
        request = db.scalar(
            select(KnowledgeConnectionRequest).where(KnowledgeConnectionRequest.run_id == run.id)
        )
        frozen = copy.deepcopy(request.input_json)
        node = next(
            node
            for node in frozen["source"]["content"]["graph"]["nodes"]
            if node["type"] != "PAPER"
        )
        node["source_refs"][0]["quote"] = "INVENTED FROZEN QUOTE"
        request.input_json = frozen
        changed = validate_connections(request.raw_response, frozen)
        request.output_json = changed
        report = db.get(KnowledgeConnectionReport, run.report_id)
        report_id = report.id
        report.report_json = {
            **report.report_json,
            "relations": changed["relations"],
            "summary": changed["summary"],
        }
    with Session(engine) as db, pytest.raises(KnowledgeError):
        report_view(db, db.get(KnowledgeConnectionReport, report_id))


def test_reused_negative_checkpoint_retains_no_relation_reason(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    first = queue_connection(engine, versions[1])
    reason = "两篇论文的合成术语相似，但缺少可支持科学联系的比较条件。"
    provider = ConnectionProvider(
        json.dumps(
            {
                "schema_version": "knowledge-connections-1",
                "relations": [],
                "summary": [],
                "no_relation_reason_zh": reason,
            }
        )
    )
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=provider))
    second = queue_connection(engine, versions[0])
    asyncio.run(run_knowledge_connect(engine, second, tmp_path, provider=provider))
    job, _, requests, report = connection_record(engine, second)
    assert job.status == "succeeded" and not requests and provider.calls == 1
    assert reason in report.report_json["no_relation_reasons"]


def test_auto_event_disabled_then_enabled_is_idempotent(tmp_path, monkeypatch):
    engine, versions, _ = built_papers(tmp_path)
    monkeypatch.setattr("researchgraph.knowledge_connections.snapshot_for", lambda *_: SNAPSHOT)
    with Session(engine) as db, db.begin():
        queue_auto_connections(db, versions[1])
        event = db.get(KnowledgeAnalysisEvent, versions[1])
        assert event.state == "pending" and event.reason == "POLICY_DISABLED"
        library = ensure_library(db)
        library.settings_json = {
            **library.settings_json,
            "auto_connect": True,
            "allow_network": True,
        }
        dispatch_pending_analysis(db)
        queue_auto_connections(db, versions[1])
    with Session(engine) as db:
        events = [db.get(KnowledgeAnalysisEvent, version) for version in versions]
        assert sorted(event.state for event in events) == ["pending", "queued"]
        assert (
            next(event for event in events if event.state == "pending").reason
            == "KNOWLEDGE_PAIR_PENDING"
        )
        assert db.query(KnowledgeConnectionRequest).count() == 1
        active = db.query(KnowledgeConnectionRun).one()
        job_id = active.job_id
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as db, db.begin():
        dispatch_pending_analysis(db)
        queued_runs = db.query(KnowledgeConnectionRun).filter_by(status="queued").all()
        assert len(queued_runs) == 1
        second_id = queued_runs[0].job_id
    asyncio.run(run_knowledge_connect(engine, second_id, tmp_path, provider=provider))
    with Session(engine) as db:
        assert all(
            db.get(KnowledgeAnalysisEvent, version).state == "queued" for version in versions
        )
        assert db.query(KnowledgeConnectionRequest).count() == 1
        assert db.query(KnowledgeConnectionReport).count() == 2
    assert provider.calls == 1


def test_budget_accounts_for_extracts_and_active_connection_reservations(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    with Session(engine) as db, db.begin():
        library = ensure_library(db)
        library.settings_json = {**library.settings_json, "total_request_limit": 2}
    with pytest.raises(KnowledgeError, match="预算"):
        queue_connection(engine, versions[1])
    with Session(engine) as db, db.begin():
        library = ensure_library(db)
        library.settings_json = {**library.settings_json, "total_request_limit": 3}
    first = queue_connection(engine, versions[1])
    with Session(engine) as db, db.begin():
        library = ensure_library(db)
        library.settings_json = {**library.settings_json, "total_request_limit": 2}
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=provider))
    assert (
        provider.calls == 0
        and connection_record(engine, first)[1].error_code == "KNOWLEDGE_BUDGET_EXHAUSTED"
    )


def test_partial_batches_keep_validated_checkpoint_and_retry_only_unfinished_pair(tmp_path):
    from researchgraph.knowledge_connections import PROMPT, _context
    from researchgraph.knowledge_connections_contracts import ConnectionsDraft

    engine, versions, _ = built_papers(tmp_path, 3)
    with Session(engine) as db, db.begin():
        source = _context(db, db.get(PaperKnowledgeVersion, versions[2]))
        candidate = {**_context(db, db.get(PaperKnowledgeVersion, versions[0])), "ref": "p1"}
        overhead = len(
            (PROMPT + json.dumps(ConnectionsDraft.model_json_schema(), ensure_ascii=False)).encode()
        )
        one = overhead + len(
            json.dumps({"source": source, "candidates": [candidate]}, ensure_ascii=False).encode()
        )
        library = ensure_library(db)
        library.settings_json = {**library.settings_json, "max_input_tokens": one + 100}
    first = queue_connection(engine, versions[2])

    class PartialProvider(ConnectionProvider):
        async def complete(self, prompt, data, schema):
            if self.calls == 1:
                self.calls += 1
                return "invalid JSON"
            return await super().complete(prompt, data, schema)

    provider = PartialProvider()
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=provider))
    job, _, requests, report = connection_record(engine, first)
    assert len(requests) == 2 and provider.calls == 2
    assert job.status == "failed" and report.report_json["status"] == "partial"
    assert report.report_json["coverage"]["compared"] == 1
    assert sorted(request.status for request in requests) == ["failed", "validated"]
    second = queue_connection(engine, versions[2], retry_failed=True)
    replacement = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, second, tmp_path, provider=replacement))
    job, _, requests, report = connection_record(engine, second)
    assert job.status == "succeeded" and replacement.calls == len(requests) == 1
    assert report.report_json["coverage"]["compared"] == 2
    assert len(report.report_json["relations"]) == 2


def test_archive_inflight_preserves_raw_and_stales_previous_report(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    first = queue_connection(engine, versions[1])
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=provider))
    old_report = connection_record(engine, first)[3]
    second = queue_connection(engine, versions[1], force_regenerate=True)

    def archive():
        with Session(engine) as db, db.begin():
            version = db.get(PaperKnowledgeVersion, versions[0])
            db.get(LibraryPaper, version.library_paper_id).archived = True

    provider.action = archive
    asyncio.run(run_knowledge_connect(engine, second, tmp_path, provider=provider))
    job, _, requests, report = connection_record(engine, second)
    assert job.status == "failed" and requests[0].raw_response and report is None
    with Session(engine) as db:
        assert report_view(db, old_report)["stale"]


def test_purge_refuses_active_dependencies_and_cleans_saved_report(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    with Session(engine) as db, db.begin():
        paper_id = db.get(PaperKnowledgeVersion, versions[0]).library_paper_id
        with pytest.raises(KnowledgeError, match="执行"):
            cleanup_library_paper(db, paper_id)
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=ConnectionProvider()))
    with Session(engine) as db, db.begin():
        cleanup_library_paper(db, paper_id)
    with Session(engine) as db:
        assert db.query(KnowledgeConnectionReport).count() == 0
        assert db.query(KnowledgePairCheckpoint).count() == 0


def test_purge_preserves_anonymous_usage_and_total_budget(tmp_path):
    from researchgraph.knowledge_connection_models import KnowledgeUsageTombstone
    from researchgraph.knowledge_connections import reserved_requests
    from researchgraph.knowledge_tasks import check_knowledge_request_budget

    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=ConnectionProvider()))
    with Session(engine) as db, db.begin():
        assert reserved_requests(db) == 3
        paper_id = db.get(PaperKnowledgeVersion, versions[0]).library_paper_id
        cleanup_library_paper(db, paper_id)
        assert reserved_requests(db) == 3
        tombstones = db.query(KnowledgeUsageTombstone).all()
        assert len(tombstones) == 2
        assert all(row.usage_json["total_tokens"] == 300 for row in tombstones)
        assert all(not hasattr(row, "source_paper_id") for row in tombstones)
        with pytest.raises(KnowledgeError, match="预算"):
            check_knowledge_request_budget(db, 3, additional=1)


def test_purge_removes_transitive_inherited_report_context_without_resetting_usage(tmp_path):
    from researchgraph.knowledge_connections import reserved_requests
    from researchgraph.knowledge_library_models import (
        KnowledgeCollection,
        KnowledgeCollectionMember,
    )
    from researchgraph.lite_usage import aggregate_knowledge_usage

    engine, versions, _ = built_papers(tmp_path, 3)
    a, b, c = versions
    first = queue_connection(engine, a)
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=provider))
    _, first_run, first_requests, first_report = connection_record(engine, first)
    assert len(first_requests) == 1
    assert {item["version_id"] for item in first_run.input_json["candidates"]} == {b, c}
    with Session(engine) as db, db.begin():
        library = ensure_library(db)
        a_paper = db.get(PaperKnowledgeVersion, a).library_paper_id
        c_paper = db.get(PaperKnowledgeVersion, c).library_paper_id
        collection = KnowledgeCollection(id=str(uuid4()), library_id=library.id, name="A only")
        db.add(collection)
        db.flush()
        db.add(KnowledgeCollectionMember(collection_id=collection.id, library_paper_id=a_paper))
        library.settings_json = {
            **library.settings_json,
            "scope": "collection",
            "collection_id": collection.id,
        }
    second = queue_connection(engine, b)
    asyncio.run(run_knowledge_connect(engine, second, tmp_path, provider=provider))
    _, second_run, second_requests, second_report = connection_record(engine, second)
    assert second_requests == [] and provider.calls == 1
    assert [item["version_id"] for item in second_run.input_json["candidates"]] == [a]
    assert second_run.input_json["reused_report_ids"] == [first_report.id]
    first_run_id, second_run_id = first_run.id, second_run.id
    first_report_id, second_report_id = first_report.id, second_report.id
    with Session(engine) as db, db.begin():
        before = aggregate_knowledge_usage(db)
        assert reserved_requests(db) == before.calls == 4
        cleanup_library_paper(db, c_paper)
    with Session(engine) as db:
        assert db.get(KnowledgeConnectionRun, first_run_id) is None
        assert db.get(KnowledgeConnectionRun, second_run_id) is None
        assert db.get(KnowledgeConnectionReport, first_report_id) is None
        assert db.get(KnowledgeConnectionReport, second_report_id) is None
        assert db.query(KnowledgeConnectionRequest).count() == 0
        assert db.query(KnowledgePairCheckpoint).count() == 0
        after = aggregate_knowledge_usage(db)
        assert reserved_requests(db) == after.calls == before.calls == 4
        assert after.total_tokens == before.total_tokens == 1200
