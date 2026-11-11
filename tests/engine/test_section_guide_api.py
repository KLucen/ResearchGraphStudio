import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.core import KnowledgeError
from researchgraph.lite_models import LiteCacheEntry, LiteTokenUsage
from researchgraph.models import (
    AttachmentRevision,
    Base,
    Chunk,
    EvidenceSpan,
    Job,
    Paper,
    Project,
    Section,
    now,
)
from researchgraph.section_guide_api import (
    _configuration,
    _hash,
    _identity,
    _section_scope,
    build_guide_input,
    execute_section_guide,
    recover_section_guides,
    register_section_guide_api,
)
from researchgraph.section_guide_contracts import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    TASK_KIND,
)
from researchgraph.section_guide_models import SectionGuideResult
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

EXAMPLE = Path("docs/researchgraph_lite_ABD/examples/reading_guide_fictional.json")


class CountingProvider:
    name = "test-provider"
    model = "test-model"
    base_url = "https://provider.test/v1"
    parameters: dict[str, object] = {"temperature": 0}

    def __init__(self, response: str, before_return=None) -> None:
        self.response = response
        self.before_return = before_return
        self.calls = 0
        self.usage = {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}
        self.request_metadata: dict[str, object] = {}

    async def complete(self, prompt: str, data: dict, schema: dict) -> str:
        self.calls += 1
        if self.before_return is not None:
            self.before_return()
        return self.response


def _fixture() -> tuple[Engine, str, str, str, str, str]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Importing these modules registers their tables on the shared metadata.
    import researchgraph.lite_models  # noqa: F401

    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id, section_id, chunk_id, span_id = (
        str(uuid4()) for _ in range(6)
    )
    timestamp = now()
    with Session(engine) as session, session.begin():
        session.add(
            Project(
                id=project_id,
                name="guide-test",
                description="lite",
                experience_mode="lite",
                created_at=timestamp,
            )
        )
        session.add(
            Paper(id=paper_id, project_id=project_id, title="Guide paper", created_at=timestamp)
        )
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="a" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at=timestamp,
            )
        )
        session.add(
            Section(
                id=section_id,
                document_version_id=revision_id,
                title="Methods",
                ordinal=1,
                role="method",
                parser="test",
                parent_id=None,
                level=1,
                start_page=0,
                end_page=0,
                excluded=False,
            )
        )
        session.add(
            Chunk(
                id=chunk_id,
                revision_id=revision_id,
                page_index=0,
                page_label="1",
                block_index=0,
                text="The method uses a shared memory module.",
                bbox=[0, 0, 1, 1],
            )
        )
        session.add(
            EvidenceSpan(
                id=span_id,
                document_version_id=revision_id,
                section_id=section_id,
                paragraph_id=chunk_id,
                page_index=0,
                start_offset=0,
                end_offset=39,
                quote="The method uses a shared memory module.",
                text_sha256="b" * 64,
                normalization="identity-v1",
                bbox_list=[[0, 0, 1, 1]],
            )
        )
    return engine, project_id, paper_id, revision_id, section_id, span_id


def _job_for(
    engine: Engine,
    provider: CountingProvider,
    project_id: str,
    paper_id: str,
    revision_id: str,
    section_id: str,
    *,
    depth: str = "standard",
    allow_network: bool = True,
) -> str:
    with Session(engine) as session:
        paper = session.get(Paper, paper_id)
        revision = session.get(AttachmentRevision, revision_id)
        section = session.get(Section, section_id)
        assert paper is not None and revision is not None and section is not None
        spans = session.scalars(
            select(EvidenceSpan).where(EvidenceSpan.section_id == section_id)
        ).all()
        context = build_guide_input(session, paper, revision, section, None, spans, depth)
    input_hash = _hash(context)
    config = _configuration({"base_url": provider.base_url, "parameters": provider.parameters})
    key, _ = _identity(
        project_id,
        paper_id,
        revision,
        section_id,
        depth,
        input_hash,
        provider.name,
        provider.model,
        config,
    )
    job_id = str(uuid4())
    with Session(engine) as session, session.begin():
        session.add(
            Job(
                id=job_id,
                project_id=project_id,
                kind=TASK_KIND,
                payload={
                    "paper_id": paper_id,
                    "document_version_id": revision_id,
                    "section_id": section_id,
                    "depth": depth,
                    "allow_network": allow_network,
                    "input_hash": input_hash,
                    "cache_key": key,
                },
                status="queued",
                stage="queued",
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
        )
    return job_id


def _response(section_id: str, span_id: str) -> str:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["section_id"] = section_id
    payload["evidence_span_ids"] = [span_id]
    return json.dumps(payload, ensure_ascii=False)


def test_section_guide_cache_is_scoped_by_depth_and_avoids_second_provider_call(
    tmp_path: Path,
) -> None:
    engine, project_id, paper_id, revision_id, section_id, span_id = _fixture()
    provider = CountingProvider(_response(section_id, span_id))
    first = _job_for(
        engine, provider, project_id, paper_id, revision_id, section_id, depth="standard"
    )
    second = _job_for(
        engine, provider, project_id, paper_id, revision_id, section_id, depth="standard"
    )
    deep = _job_for(engine, provider, project_id, paper_id, revision_id, section_id, depth="deep")

    asyncio.run(execute_section_guide(engine, first, tmp_path, provider=provider))
    asyncio.run(execute_section_guide(engine, second, tmp_path, provider=provider))
    asyncio.run(execute_section_guide(engine, deep, tmp_path, provider=provider))

    with Session(engine) as session:
        rows = session.scalars(
            select(SectionGuideResult).order_by(SectionGuideResult.created_at)
        ).all()
        assert [row.status for row in rows] == ["COMPLETED", "COMPLETED", "COMPLETED"]
        assert rows[1].cache_hit is True
        assert rows[2].depth == "deep"
        assert session.query(LiteCacheEntry).count() == 2
        usage = session.scalars(
            select(LiteTokenUsage).where(LiteTokenUsage.task_kind == TASK_KIND)
        ).all()
        assert sum(1 for item in usage if item.cache_hit) == 1
    assert provider.calls == 2


def test_completion_rechecks_section_readability_before_publishing(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id, section_id, span_id = _fixture()

    def exclude_section() -> None:
        with Session(engine) as session, session.begin():
            section = session.get(Section, section_id)
            assert section is not None
            section.excluded = True

    provider = CountingProvider(_response(section_id, span_id), before_return=exclude_section)
    job_id = _job_for(engine, provider, project_id, paper_id, revision_id, section_id)
    asyncio.run(execute_section_guide(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as session:
        row = session.scalar(select(SectionGuideResult).where(SectionGuideResult.job_id == job_id))
        job = session.get(Job, job_id)
        assert row is not None and row.status == "FAILED"
        assert row.error_code == "GUIDE_INPUT_CHANGED"
        assert job is not None and job.status == "failed"


def test_invalid_cache_payload_is_not_reused(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id, section_id, span_id = _fixture()
    provider = CountingProvider(_response(section_id, span_id))
    first = _job_for(engine, provider, project_id, paper_id, revision_id, section_id)
    asyncio.run(execute_section_guide(engine, first, tmp_path, provider=provider))
    with Session(engine) as session, session.begin():
        cache = session.scalar(select(LiteCacheEntry))
        assert cache is not None
        cache.response = {
            "section_id": "wrong-section",
            "overview_zh": "bad",
            "key_points": ["bad"],
            "reading_questions": ["q1", "q2"],
            "evidence_span_ids": ["wrong-span"],
        }
    second = _job_for(engine, provider, project_id, paper_id, revision_id, section_id)
    asyncio.run(execute_section_guide(engine, second, tmp_path, provider=provider))
    with Session(engine) as session:
        row = session.scalar(select(SectionGuideResult).where(SectionGuideResult.job_id == second))
        assert row is not None and row.status == "COMPLETED" and row.cache_hit is False
    assert provider.calls == 2


def test_cancelled_invalid_response_preserves_raw_and_cancelled_usage(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id, section_id, span_id = _fixture()
    job_holder = {"id": ""}

    def cancel_job() -> None:
        with Session(engine) as session, session.begin():
            job = session.get(Job, job_holder["id"])
            row = session.scalar(
                select(SectionGuideResult).where(SectionGuideResult.job_id == job_holder["id"])
            )
            assert job is not None and row is not None
            job.status = "cancelled"
            row.status = "FAILED"
            row.error_code = "CANCELLED"

    provider = CountingProvider("not-json", before_return=cancel_job)
    job_id = _job_for(engine, provider, project_id, paper_id, revision_id, section_id)
    job_holder["id"] = job_id
    asyncio.run(execute_section_guide(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as session:
        row = session.scalar(select(SectionGuideResult).where(SectionGuideResult.job_id == job_id))
        usage = session.scalar(select(LiteTokenUsage).where(LiteTokenUsage.task_run_id == job_id))
        assert row is not None and row.raw_output == "not-json"
        assert (
            usage is not None and usage.status == "cancelled" and usage.reason_code == "CANCELLED"
        )


def test_guide_input_contains_version_scoped_allowed_span_fields() -> None:
    engine, _project_id, paper_id, revision_id, section_id, _span_id = _fixture()
    with Session(engine) as session:
        paper = session.get(Paper, paper_id)
        revision = session.get(AttachmentRevision, revision_id)
        section = session.get(Section, section_id)
        spans = list(
            session.scalars(select(EvidenceSpan).where(EvidenceSpan.section_id == section_id))
        )
        assert paper is not None and revision is not None and section is not None
        context = build_guide_input(session, paper, revision, section, None, spans, "standard")
    allowed = context["allowed_spans"]
    assert allowed and set(allowed[0]) == {
        "span_id",
        "document_version_id",
        "section_id",
        "page_start",
        "page_end",
        "text_en",
    }
    assert allowed[0]["document_version_id"] == revision_id


@pytest.mark.parametrize("field", ["excluded", "references"])
def test_reference_or_excluded_section_cannot_generate_guide(field: str) -> None:
    engine, _project_id, paper_id, revision_id, section_id, _span_id = _fixture()
    with Session(engine) as session, session.begin():
        section = session.get(Section, section_id)
        assert section is not None
        if field == "excluded":
            section.excluded = True
        else:
            section.role = "references"
    with Session(engine) as session:
        with pytest.raises(KnowledgeError, match="参考文献"):
            _section_scope(session, paper_id, revision_id, section_id)


def test_network_consent_is_required_and_get_is_read_only(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id, section_id, span_id = _fixture()
    provider = CountingProvider(_response(section_id, span_id))
    job_id = _job_for(
        engine,
        provider,
        project_id,
        paper_id,
        revision_id,
        section_id,
        allow_network=False,
    )
    asyncio.run(execute_section_guide(engine, job_id, tmp_path, provider=provider))
    assert provider.calls == 0
    with Session(engine) as session:
        job = session.get(Job, job_id)
        result = session.scalar(
            select(SectionGuideResult).where(SectionGuideResult.job_id == job_id)
        )
        assert job is not None and job.status == "failed"
        # Consent is checked before a model request and the transaction that
        # created the provisional row is rolled back; no guide is published.
        assert result is None

    app = FastAPI()
    register_section_guide_api(app, lambda: engine, tmp_path)
    with TestClient(app) as client:
        before = provider.calls
        response = client.get(f"/api/v1/papers/{paper_id}/sections/{section_id}/guide")
        assert response.status_code == 200
        assert response.json() is None
        assert provider.calls == before


def test_invalid_provider_response_is_failed_with_raw_output_and_usage(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id, section_id, span_id = _fixture()
    bad = json.loads(_response(section_id, span_id))
    bad["section_id"] = "wrong-section"
    provider = CountingProvider(json.dumps(bad, ensure_ascii=False))
    job_id = _job_for(engine, provider, project_id, paper_id, revision_id, section_id)
    asyncio.run(execute_section_guide(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as session:
        result = session.scalar(
            select(SectionGuideResult).where(SectionGuideResult.job_id == job_id)
        )
        usage = session.scalar(select(LiteTokenUsage).where(LiteTokenUsage.task_run_id == job_id))
        assert result is not None and result.status == "FAILED"
        assert result.error_code == "GUIDE_GENERATION_FAILED"
        assert result.raw_output == json.dumps(bad, ensure_ascii=False)
        assert usage is not None and usage.status == "failed"
        assert usage.input_tokens == 120 and usage.output_tokens == 80
    assert provider.calls == 1


def test_restart_recovery_interrupts_pending_without_resubmitting(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id, section_id, _span_id = _fixture()
    job_id = str(uuid4())
    result_id = str(uuid4())
    timestamp = now()
    with Session(engine) as session, session.begin():
        session.add(
            Job(
                id=job_id,
                project_id=project_id,
                kind=TASK_KIND,
                payload={"paper_id": paper_id, "section_id": section_id},
                status="running",
                stage="generating",
                attempt=0,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        session.add(
            SectionGuideResult(
                id=result_id,
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                section_id=section_id,
                depth="standard",
                source_hash="a" * 64,
                input_hash="b" * 64,
                cache_key="c" * 64,
                schema_version=SCHEMA_VERSION,
                prompt_version=PROMPT_VERSION,
                provider_id="test-provider",
                model_id="test-model",
                status="PENDING",
                usage_json={},
                created_at=timestamp,
                updated_at=timestamp,
                job_id=job_id,
            )
        )
        session.add(
            LiteTokenUsage(
                id=str(uuid4()),
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                section_id=section_id,
                task_run_id=job_id,
                task_kind=TASK_KIND,
                status="started",
                created_at=timestamp,
            )
        )
    assert recover_section_guides(engine) == 1
    with Session(engine) as session:
        job = session.get(Job, job_id)
        result = session.get(SectionGuideResult, result_id)
        usage = session.scalar(select(LiteTokenUsage).where(LiteTokenUsage.task_run_id == job_id))
        assert job is not None and job.status == "interrupted"
        assert result is not None and result.error_code == "INTERRUPTED"
        assert usage is not None and usage.status == "interrupted"


def test_list_marks_completed_guide_stale_when_a_newer_document_version_exists(
    tmp_path: Path,
) -> None:
    engine, project_id, paper_id, revision_id, section_id, span_id = _fixture()
    newer_revision_id = str(uuid4())
    timestamp = now()
    with Session(engine) as session, session.begin():
        session.add(
            AttachmentRevision(
                id=newer_revision_id,
                paper_id=paper_id,
                sha256="d" * 64,
                parser_version="test-newer",
                page_count=1,
                warnings=[],
                created_at="9999-01-01T00:00:00+00:00",
            )
        )
        session.add(
            SectionGuideResult(
                id=str(uuid4()),
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                section_id=section_id,
                depth="standard",
                source_hash="a" * 64,
                input_hash="b" * 64,
                cache_key="c" * 64,
                schema_version=SCHEMA_VERSION,
                prompt_version=PROMPT_VERSION,
                provider_id="test-provider",
                model_id="test-model",
                status="COMPLETED",
                guide_json={
                    "section_id": section_id,
                    "overview_zh": "旧版本导读",
                    "key_points": ["旧重点"],
                    "reading_questions": ["旧问题一", "旧问题二"],
                    "evidence_span_ids": [span_id],
                },
                usage_json={},
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    app = FastAPI()
    register_section_guide_api(app, lambda: engine, tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/papers/{paper_id}/section-guides")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["status"] == "STALE"
    assert payload[0]["stale_reason"] == "document_version_changed"


def test_list_rejects_unknown_depth_without_querying_provider(tmp_path: Path) -> None:
    _engine, _project_id, paper_id, _revision_id, _section_id, _span_id = _fixture()
    app = FastAPI()
    register_section_guide_api(app, lambda: _engine, tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/papers/{paper_id}/section-guides?depth=full")
    assert response.status_code == 422


@pytest.mark.parametrize("allow_network", [False, True])
def test_generate_route_requires_explicit_network_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, allow_network: bool
) -> None:
    engine, _project_id, paper_id, revision_id, section_id, _span_id = _fixture()
    snapshot = {
        "provider": "compatible",
        "model": "test-model",
        "base_url": "https://provider.test/v1",
        "parameters": {"temperature": 0},
    }
    monkeypatch.setattr("researchgraph.model_settings.snapshot_for", lambda *args: snapshot)
    app = FastAPI()
    register_section_guide_api(app, lambda: engine, tmp_path)
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/papers/{paper_id}/sections/{section_id}/guide/generate",
            json={
                "document_version_id": revision_id,
                "section_id": section_id,
                "depth": "standard",
                "allow_network": allow_network,
            },
        )
    if not allow_network:
        assert response.status_code == 409
        with Session(engine) as session:
            assert session.query(Job).filter(Job.kind == TASK_KIND).count() == 0
    else:
        assert response.status_code == 200
        assert response.json()["status"] == "PENDING"
