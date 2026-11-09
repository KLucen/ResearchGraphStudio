"""Vertical Lite P0 checks: local indexing, zero model calls and cache primitives."""

import re
import shutil

import pytest
from researchgraph.knowledge_models import ModelRun
from researchgraph.lite_usage import (
    cache_key,
    mark_cache_stale,
    read_cache,
    write_cache,
)
from researchgraph.models import AttachmentRevision, Job, Paper, now
from researchgraph.providers import ConfiguredProvider, MockProvider
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_document_structure import synthetic
from test_engine import client, post
from test_ingest import FIXTURES, queue, wait_job


def indexed_source_snapshot(engine, project_id, revision_id, chunks):
    """Check materialized FTS rows directly, without triggering an index rebuild."""

    with Session(engine) as session:
        entries = (
            session.execute(
                text(
                    "SELECT e.id, e.object_id, e.text, f.text AS fts_text "
                    "FROM query_index_entries e JOIN query_fts f ON f.entry_id=e.id "
                    "WHERE e.project_id=:project AND e.source_kind='chunk' "
                    "AND json_extract(e.data, '$.document_version_id')=:version "
                    "ORDER BY e.id"
                ),
                {"project": project_id, "version": revision_id},
            )
            .mappings()
            .all()
        )
        assert entries, "Lite local import must materialize its text index"
        source_text = {chunk["id"]: chunk["text"] for chunk in chunks}
        for entry in entries:
            assert entry["text"] == entry["fts_text"] == source_text[entry["object_id"]]
            token = next(iter(re.findall(r"[A-Za-z]{3,}", entry["text"])), None)
            if token is not None:
                assert (
                    session.scalar(
                        text(
                            "SELECT count(*) FROM query_fts WHERE query_fts MATCH :query "
                            "AND project_id=:project AND entry_id=:entry"
                        ),
                        {"query": '"' + token + '"', "project": project_id, "entry": entry["id"]},
                    )
                    == 1
                )
        return [dict(entry) for entry in entries]


def test_lite_pdf_is_local_only_and_reports_zero_usage(tmp_path, monkeypatch):
    calls = []

    async def unexpected_model_call(self, *args, **kwargs):
        calls.append(type(self).__name__)
        raise AssertionError("Local Lite parsing must not call any model")

    monkeypatch.setattr(MockProvider, "complete", unexpected_model_call)
    monkeypatch.setattr(ConfiguredProvider, "complete", unexpected_model_call)
    source = tmp_path / "lite.pdf"
    shutil.copyfile(FIXTURES / "two-pages.pdf", source)
    second = tmp_path / "structured.pdf"
    synthetic(second)
    snapshots = {}
    with client(tmp_path / "data", worker=True) as api:
        project_response = post(
            api,
            "/projects",
            {"name": "Lite P0", "experience_mode": "lite"},
            "lite-project",
        )
        assert project_response.status_code == 201
        project = project_response.json()
        assert project["experience_mode"] == "lite"

        for index, path in enumerate((source, second)):
            imported = wait_job(api, queue(api, project["id"], path, f"lite-pdf-{index}"))
            assert imported["status"] == "succeeded", imported
            revision_id = imported["result"]["revision_id"]
            chunks = api.get(f"/api/v1/revisions/{revision_id}/chunks").json()["items"]
            assert chunks and {chunk["page_index"] for chunk in chunks} == {0, 1}
            structure = api.get(f"/api/v1/revisions/{revision_id}/structure").json()
            assert structure["sections"] and structure["evidence"]
            indexed = indexed_source_snapshot(
                api.app.state.engine, project["id"], revision_id, chunks
            )
            snapshots[revision_id] = (chunks, structure, indexed)

        usage = api.get(f"/api/v1/projects/{project['id']}/lite/usage")
        assert usage.status_code == 200, usage.text
        assert usage.json()["calls"] == 0
        assert usage.json()["input_tokens"] == 0
        assert usage.json()["output_tokens"] == 0
        assert usage.json()["total_tokens"] == 0

        # A stale client may still submit the old explicit extraction route. The
        # worker records a local, deterministic refusal and never creates a run.
        extract = post(
            api,
            "/knowledge/extract",
            {"document_version_id": revision_id, "allow_network": True},
            "lite-extract",
        )
        blocked = wait_job(api, extract.json())
        assert blocked["status"] == "failed"
        assert blocked["result"]["model_calls"] == 0
        assert "Lite 模式" in blocked["error"]
        with Session(api.app.state.engine) as session:
            assert session.scalar(select(ModelRun.id)) is None
        assert calls == []

    with client(tmp_path / "data", worker=True) as reopened:
        for revision_id, (chunks, structure, indexed) in snapshots.items():
            assert reopened.get(f"/api/v1/revisions/{revision_id}/chunks").json()["items"] == chunks
            assert reopened.get(f"/api/v1/revisions/{revision_id}/structure").json() == structure
            assert (
                indexed_source_snapshot(
                    reopened.app.state.engine, project["id"], revision_id, chunks
                )
                == indexed
            )
        assert reopened.get(f"/api/v1/projects/{project['id']}/lite/usage").json()["calls"] == 0
        assert calls == []


@pytest.mark.parametrize(
    "kind",
    ["knowledge_extract", "knowledge_reason", "query_answer", "p5_workflow", "translation_repair"],
)
def test_queued_legacy_model_jobs_are_blocked_in_lite_on_restart(tmp_path, monkeypatch, kind):
    calls = []

    async def unexpected_model_call(self, *args, **kwargs):
        calls.append(type(self).__name__)
        raise AssertionError("Legacy queued model job must be blocked")

    monkeypatch.setattr(MockProvider, "complete", unexpected_model_call)
    monkeypatch.setattr(ConfiguredProvider, "complete", unexpected_model_call)
    data = tmp_path / "data"
    with client(data) as api:
        project = api.post(
            "/api/v1/projects",
            json={"name": "Queued Lite"},
            headers={"Idempotency-Key": "queued-lite"},
        ).json()
        with Session(api.app.state.engine) as session, session.begin():
            session.add(
                Job(
                    id="queued-model",
                    project_id=project["id"],
                    kind=kind,
                    payload={"provider": "mock"},
                    status="queued",
                    attempt=0,
                    created_at=now(),
                    updated_at=now(),
                )
            )
    with client(data, worker=True) as reopened:
        blocked = wait_job(reopened, {"id": "queued-model"})
        assert blocked["status"] == "failed"
        assert blocked["result"]["error_code"] == "LITE_MODE_DISABLED"
        assert blocked["result"]["model_calls"] == 0
        assert calls == []


def test_lite_cache_key_and_stale_transition_are_versioned(tmp_path):
    with client(tmp_path / "data") as api:
        project = post(
            api,
            "/projects",
            {"name": "Lite cache", "experience_mode": "lite"},
            "lite-cache-project",
        ).json()
        engine = api.app.state.engine
        with Session(engine) as session, session.begin():
            session.add(
                Paper(
                    id="paper-1",
                    project_id=project["id"],
                    title="Synthetic paper",
                    created_at=now(),
                )
            )
            session.flush()
            session.add(
                AttachmentRevision(
                    id="version-1",
                    paper_id="paper-1",
                    sha256="c" * 64,
                    parser_version="test",
                    page_count=1,
                    warnings=[],
                    created_at=now(),
                )
            )
        key = cache_key(
            {
                "task_kind": "A",
                "project_id": project["id"],
                "paper_id": "paper-1",
                "document_version_id": "version-1",
                "input_fingerprint": "f" * 64,
                "prompt_version": "A01-v1",
                "schema_version": "ReadingGuideDraft-v1",
                "source_hash": "c" * 64,
                "provider": "synthetic",
                "model": "synthetic",
                "config_fingerprint": "d" * 64,
            }
        )
        assert key == cache_key(
            {
                "schema_version": "ReadingGuideDraft-v1",
                "prompt_version": "A01-v1",
                "document_version_id": "version-1",
                "input_fingerprint": "f" * 64,
                "paper_id": "paper-1",
                "project_id": project["id"],
                "task_kind": "A",
                "source_hash": "c" * 64,
                "provider": "synthetic",
                "model": "synthetic",
                "config_fingerprint": "d" * 64,
            }
        )
        with Session(engine) as session, session.begin():
            write_cache(
                session,
                cache_key_value=key,
                project_id=project["id"],
                paper_id="paper-1",
                document_version_id="version-1",
                task_kind="A",
                input_fingerprint="f" * 64,
                prompt_version="A01-v1",
                schema_version="ReadingGuideDraft-v1",
                source_hash="c" * 64,
                provider="synthetic",
                model="synthetic",
                config_fingerprint="d" * 64,
                response={"status": "cached"},
            )
        with Session(engine) as session, session.begin():
            assert (
                read_cache(
                    session,
                    key,
                    project_id=project["id"],
                    paper_id="paper-1",
                    document_version_id="version-1",
                    task_kind="A",
                )
                is not None
            )
            assert mark_cache_stale(
                session,
                key,
                "source_changed",
                project_id=project["id"],
                paper_id="paper-1",
                document_version_id="version-1",
                task_kind="A",
            )
        with Session(engine) as session:
            assert (
                read_cache(
                    session,
                    key,
                    project_id=project["id"],
                    paper_id="paper-1",
                    document_version_id="version-1",
                    task_kind="A",
                )
                is None
            )
            assert (
                read_cache(
                    session,
                    key,
                    project_id=project["id"],
                    paper_id="paper-1",
                    document_version_id="version-1",
                    task_kind="A",
                    allow_stale=True,
                ).stale_reason
                == "source_changed"
            )
