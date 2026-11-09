import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
)
from researchgraph.paper_overview_api import (
    build_overview_input,
    execute_overview,
    register_paper_overview_api,
)
from researchgraph.paper_overview_contracts import validate_response
from researchgraph.paper_overview_models import (
    PaperGraphLayout,
    PaperGraphViewport,
    PaperOverviewResult,
)
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

EXAMPLE = Path(
    "docs/ResearchGraph_Lite_LightGraph_Addendum/examples/paper_overview_graph.example.json"
)


def test_joint_overview_example_is_valid_and_ids_are_stable() -> None:
    raw = EXAMPLE.read_text(encoding="utf-8")
    card_a, graph_a = validate_response(raw, "paper-1")
    card_b, graph_b = validate_response(raw, "paper-1")
    assert card_a == card_b
    assert [node.id for node in graph_a.nodes] == [node.id for node in graph_b.nodes]
    assert len(graph_a.nodes) <= 12
    assert len(graph_a.edges) <= 16


def test_overview_input_uses_structured_roles_and_excludes_references() -> None:
    engine, project_id, paper_id, revision_id = _seed_overview_fixture()
    role_text = {
        "abstract": "ABSTRACT_MARKER",
        "introduction": "INTRO_MARKER",
        "method": "METHOD_MARKER",
        "result": "RESULT_MARKER",
        "conclusion": "CONCLUSION_MARKER",
        "references": "REFERENCE_MARKER",
    }
    with Session(engine) as session, session.begin():
        for ordinal, (role, text) in enumerate(role_text.items(), start=1):
            section_id = f"section-{role}"
            chunk_id = f"chunk-{role}"
            session.add(
                Section(
                    id=section_id,
                    document_version_id=revision_id,
                    title=role.title(),
                    ordinal=ordinal,
                    role=role,
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
                    page_index=ordinal,
                    page_label=str(ordinal),
                    block_index=0,
                    text=text,
                    bbox=[0, 0, 1, 1],
                )
            )
            session.add(
                EvidenceSpan(
                    id=f"evidence-{role}",
                    document_version_id=revision_id,
                    section_id=section_id,
                    paragraph_id=chunk_id,
                    page_index=ordinal,
                    start_offset=0,
                    end_offset=len(text),
                    quote=text,
                    text_sha256="f" * 64,
                    normalization="identity-v1",
                    bbox_list=[[0, 0, 1, 1]],
                )
            )
    paper = Paper(id=paper_id, project_id=project_id, title="Test", created_at="now")
    with Session(engine) as session:
        context = build_overview_input(
            session,
            paper,
            session.get(AttachmentRevision, revision_id),  # type: ignore[arg-type]
        )
    assert "ABSTRACT_MARKER" in context["abstract"]
    assert "INTRO_MARKER" in context["intro_objective_excerpt"]
    assert "METHOD_MARKER" in context["method_overview_excerpt"]
    assert "RESULT_MARKER" in context["result_overview_excerpt"]
    assert "CONCLUSION_MARKER" in context["conclusion_excerpt"]
    assert "REFERENCE_MARKER" not in json.dumps(context, ensure_ascii=False)


def test_schema_rejects_evidence_and_layout_fields() -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["graph"]["nodes"][0]["evidence_id"] = "forbidden"
    with pytest.raises(ValueError):
        validate_response(json.dumps(payload, ensure_ascii=False), "paper-1")

    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["graph"]["nodes"][0]["x"] = 10
    with pytest.raises(ValueError):
        validate_response(json.dumps(payload, ensure_ascii=False), "paper-1")


def test_schema_rejects_duplicate_edge_and_wrong_endpoint() -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["graph"]["edges"].append(dict(payload["graph"]["edges"][0], id="e6"))
    with pytest.raises(ValueError, match="Duplicate edge"):
        validate_response(json.dumps(payload, ensure_ascii=False), "paper-1")

    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["graph"]["edges"][0]["target"] = "n4"
    with pytest.raises(ValueError, match="relation direction"):
        validate_response(json.dumps(payload, ensure_ascii=False), "paper-1")


class CountingProvider:
    name = "test-provider"

    def __init__(
        self,
        response: str,
        *,
        model: str = "test-model",
        parameters: dict[str, object] | None = None,
    ) -> None:
        self.response = response
        self.model = model
        self.parameters = parameters or {}
        self.calls = 0
        self.usage = {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}
        self.prompts: list[str] = []

    async def complete(self, prompt: str, data: dict, schema: dict) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        return self.response


class FailingProvider(CountingProvider):
    async def complete(self, prompt: str, data: dict, schema: dict) -> str:
        self.calls += 1
        raise RuntimeError("provider failed")


def test_second_joint_generation_uses_cache_without_provider_call(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    raw = EXAMPLE.read_text(encoding="utf-8")
    project_id, paper_id, revision_id = str(uuid4()), str(uuid4()), str(uuid4())
    with Session(engine) as session, session.begin():
        session.add(
            Project(
                id=project_id,
                name="test",
                description="lite",
                experience_mode="lite",
                created_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            Paper(
                id=paper_id,
                project_id=project_id,
                title="Test paper",
                created_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="a" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            Chunk(
                id=str(uuid4()),
                revision_id=revision_id,
                page_index=0,
                page_label="1",
                block_index=0,
                text="Abstract and method",
                bbox=[0, 0, 1, 1],
            )
        )
    provider = CountingProvider(raw)
    for job_id in (str(uuid4()), str(uuid4())):
        with Session(engine) as session, session.begin():
            session.add(
                Job(
                    id=job_id,
                    project_id=project_id,
                    kind="paper_overview",
                    payload={
                        "paper_id": paper_id,
                        "document_version_id": revision_id,
                        "provider": "configured",
                        "allow_network": True,
                    },
                    status="queued",
                    stage="queued",
                    attempt=0,
                    created_at="2026-01-01T00:00:00Z",
                    updated_at="2026-01-01T00:00:00Z",
                )
            )
        asyncio.run(execute_overview(engine, job_id, tmp_path, provider=provider))
    assert provider.calls == 1
    with Session(engine) as session:
        assert session.query(PaperOverviewResult).count() == 2
        assert session.query(LiteTokenUsage).count() == 2
        assert session.query(LiteCacheEntry).count() == 1


def test_provider_failure_is_recorded_without_automatic_retry(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id, job_id = (str(uuid4()) for _ in range(4))
    with Session(engine) as session, session.begin():
        session.add(
            Project(
                id=project_id,
                name="test",
                description="lite",
                experience_mode="lite",
                created_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            Paper(
                id=paper_id, project_id=project_id, title="Test", created_at="2026-01-01T00:00:00Z"
            )
        )
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="b" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            Chunk(
                id=str(uuid4()),
                revision_id=revision_id,
                page_index=0,
                page_label="1",
                block_index=0,
                text="text",
                bbox=[0, 0, 1, 1],
            )
        )
        session.add(
            Job(
                id=job_id,
                project_id=project_id,
                kind="paper_overview",
                payload={
                    "paper_id": paper_id,
                    "document_version_id": revision_id,
                    "provider": "configured",
                    "allow_network": True,
                },
                status="queued",
                stage="queued",
                attempt=0,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
        )
    provider = FailingProvider("{}")
    asyncio.run(execute_overview(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as session:
        job = session.get(Job, job_id)
        assert provider.calls == 1
        assert job is not None and job.status == "failed"
        assert session.query(LiteTokenUsage).count() == 1
        failed = session.query(PaperOverviewResult).one()
        assert failed.status == "FAILED"


def _seed_overview_fixture() -> tuple[Engine, str, str, str]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id = (str(uuid4()) for _ in range(3))
    with Session(engine) as session, session.begin():
        session.add(
            Project(
                id=project_id,
                name="test",
                description="lite",
                experience_mode="lite",
                created_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            Paper(
                id=paper_id,
                project_id=project_id,
                title="Test paper",
                created_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="c" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            Chunk(
                id=str(uuid4()),
                revision_id=revision_id,
                page_index=0,
                page_label="1",
                block_index=0,
                text="Abstract and method",
                bbox=[0, 0, 1, 1],
            )
        )
    return engine, project_id, paper_id, revision_id


def _add_job(
    engine: Engine,
    project_id: str,
    paper_id: str,
    revision_id: str,
    *,
    force_regenerate: bool = False,
) -> str:
    job_id = str(uuid4())
    with Session(engine) as session, session.begin():
        session.add(
            Job(
                id=job_id,
                project_id=project_id,
                kind="paper_overview",
                payload={
                    "paper_id": paper_id,
                    "document_version_id": revision_id,
                    "provider": "configured",
                    "allow_network": True,
                    "force_regenerate": force_regenerate,
                },
                status="queued",
                stage="queued",
                attempt=0,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
        )
    return job_id


def test_cache_hit_completes_current_pending_result_row(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id = _seed_overview_fixture()
    raw = EXAMPLE.read_text(encoding="utf-8")
    provider = CountingProvider(raw)
    first_job = _add_job(engine, project_id, paper_id, revision_id)
    asyncio.run(execute_overview(engine, first_job, tmp_path, provider=provider))
    second_job = _add_job(engine, project_id, paper_id, revision_id)
    with Session(engine) as session, session.begin():
        session.add(
            PaperOverviewResult(
                id=str(uuid4()),
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                pdf_hash="c" * 64,
                input_hash="pending-input",
                cache_key="pending-cache-key",
                schema_version="paper_overview_graph.v1",
                prompt_version="paper_overview_with_light_graph_v1",
                provider_id="configured",
                model_id="pending",
                status="PENDING",
                graph_status="READY",
                job_id=second_job,
                usage_json={},
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
        )
    asyncio.run(execute_overview(engine, second_job, tmp_path, provider=provider))
    with Session(engine) as session:
        current = session.get(Job, second_job)
        assert current is not None and current.status == "succeeded"
        current_result = session.get(PaperOverviewResult, current.result["overview_result_id"])
        assert current_result is not None and current_result.job_id == second_job
        assert current_result.status == "COMPLETED" and current_result.cache_hit
        assert provider.calls == 1


def test_layout_follows_same_revision_but_not_a_new_revision(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id = _seed_overview_fixture()
    raw = EXAMPLE.read_text(encoding="utf-8")
    first = CountingProvider(raw, model="model-a")
    first_job = _add_job(engine, project_id, paper_id, revision_id)
    asyncio.run(execute_overview(engine, first_job, tmp_path, provider=first))
    with Session(engine) as session, session.begin():
        first_result = session.scalar(
            select(PaperOverviewResult).where(PaperOverviewResult.job_id == first_job)
        )
        assert first_result is not None and first_result.graph_json
        node_id = first_result.graph_json["nodes"][0]["id"]
        session.add(
            PaperGraphLayout(
                id=str(uuid4()),
                paper_id=paper_id,
                overview_result_id=first_result.id,
                node_id=node_id,
                x=123,
                y=456,
                pinned=True,
                updated_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            PaperGraphViewport(
                overview_result_id=first_result.id,
                x=7,
                y=8,
                zoom=1.7,
                updated_at="2026-01-01T00:00:00Z",
            )
        )
    second = CountingProvider(raw, model="model-b")
    second_job = _add_job(engine, project_id, paper_id, revision_id)
    asyncio.run(execute_overview(engine, second_job, tmp_path, provider=second))
    with Session(engine) as session, session.begin():
        second_result = session.scalar(
            select(PaperOverviewResult).where(PaperOverviewResult.job_id == second_job)
        )
        assert second_result is not None
        position = session.scalar(
            select(PaperGraphLayout).where(
                PaperGraphLayout.overview_result_id == second_result.id,
                PaperGraphLayout.node_id == node_id,
            )
        )
        viewport = session.get(PaperGraphViewport, second_result.id)
        assert position is not None
        assert (position.x, position.y, position.pinned) == (123, 456, True)
        assert viewport is not None and (viewport.x, viewport.y, viewport.zoom) == (7, 8, 1.7)

        new_revision_id = str(uuid4())
        session.add(
            AttachmentRevision(
                id=new_revision_id,
                paper_id=paper_id,
                sha256="d" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at="2026-01-02T00:00:00Z",
            )
        )
        session.add(
            Chunk(
                id=str(uuid4()),
                revision_id=new_revision_id,
                page_index=0,
                page_label="1",
                block_index=0,
                text="Abstract and method",
                bbox=[0, 0, 1, 1],
            )
        )
    third_job = _add_job(engine, project_id, paper_id, new_revision_id)
    asyncio.run(
        execute_overview(
            engine,
            third_job,
            tmp_path,
            provider=CountingProvider(raw, model="model-c"),
        )
    )
    with Session(engine) as session:
        third_result = session.scalar(
            select(PaperOverviewResult).where(PaperOverviewResult.job_id == third_job)
        )
        assert third_result is not None
        assert (
            session.scalars(
                select(PaperGraphLayout).where(
                    PaperGraphLayout.overview_result_id == third_result.id
                )
            ).all()
            == []
        )
        assert session.get(PaperGraphViewport, third_result.id) is None


def test_model_configuration_changes_cache_identity_and_prompt_has_no_duplicate_context(
    tmp_path: Path,
) -> None:
    engine, project_id, paper_id, revision_id = _seed_overview_fixture()
    raw = EXAMPLE.read_text(encoding="utf-8")
    first = CountingProvider(raw, parameters={"temperature": 0})
    first_job = _add_job(engine, project_id, paper_id, revision_id)
    asyncio.run(execute_overview(engine, first_job, tmp_path, provider=first))
    second = CountingProvider(raw, parameters={"temperature": 0.5})
    second_job = _add_job(engine, project_id, paper_id, revision_id)
    asyncio.run(execute_overview(engine, second_job, tmp_path, provider=second))
    assert first.calls == second.calls == 1
    assert "Abstract and method" not in first.prompts[0]
    with Session(engine) as session:
        assert session.query(PaperOverviewResult).count() == 2


def test_layout_reset_removes_positions_and_saved_viewport(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id = _seed_overview_fixture()
    raw = EXAMPLE.read_text(encoding="utf-8")
    card, graph = validate_response(raw, paper_id)
    result_id = str(uuid4())
    with Session(engine) as session, session.begin():
        session.add(
            PaperOverviewResult(
                id=result_id,
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                pdf_hash="c" * 64,
                input_hash="input",
                cache_key="k" * 64,
                schema_version="paper_overview_graph.v1",
                prompt_version="paper_overview_with_light_graph_v1",
                provider_id="test",
                model_id="test",
                paper_card_json=card.model_dump(),
                graph_json=graph.model_dump(),
                usage_json={},
                status="COMPLETED",
                graph_status="READY",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
        )
    app = FastAPI()
    register_paper_overview_api(app, lambda: engine, tmp_path)
    client = TestClient(app)
    path = f"/api/v1/papers/{paper_id}/overview/graph/layout"
    payload = {
        "overview_result_id": result_id,
        "positions": [{"node_id": graph.nodes[0].id, "x": 10, "y": 20, "pinned": True}],
        "viewport": {"x": 1, "y": 2, "zoom": 1.5},
    }
    assert client.put(path, json=payload).status_code == 200
    saved = client.get(path, params={"overview_result_id": result_id}).json()
    assert saved["positions"] and saved["viewport"] == {"x": 1, "y": 2, "zoom": 1.5}
    assert client.post(f"{path}/reset", json={"overview_result_id": result_id}).status_code == 200
    reset = client.get(path, params={"overview_result_id": result_id}).json()
    assert reset["positions"] == [] and reset["viewport"] is None


def test_explicit_force_regenerate_bypasses_cache_once(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id = _seed_overview_fixture()
    raw = EXAMPLE.read_text(encoding="utf-8")
    first = CountingProvider(raw)
    first_job = _add_job(engine, project_id, paper_id, revision_id)
    asyncio.run(execute_overview(engine, first_job, tmp_path, provider=first))
    second = CountingProvider(raw)
    second_job = _add_job(
        engine,
        project_id,
        paper_id,
        revision_id,
        force_regenerate=True,
    )
    asyncio.run(execute_overview(engine, second_job, tmp_path, provider=second))
    assert first.calls == second.calls == 1
    with Session(engine) as session:
        assert session.query(PaperOverviewResult).count() == 2


def test_generate_freezes_configuration_and_reuses_exact_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from researchgraph import model_settings

    engine, project_id, paper_id, revision_id = _seed_overview_fixture()
    snapshot = {"provider": "test-provider", "model": "test-model", "parameters": {}}
    monkeypatch.setattr(model_settings, "snapshot_for", lambda *args: dict(snapshot))
    app = FastAPI()
    register_paper_overview_api(app, lambda: engine, tmp_path)
    client = TestClient(app)
    path = f"/api/v1/papers/{paper_id}/overview/generate"
    body = {"document_version_id": revision_id, "allow_network": True}
    pending = client.post(path, json=body).json()
    assert pending["status"] == "PENDING"
    assert pending["id"] != pending["job_id"]
    repeated = client.post(path, json=body).json()
    assert repeated["id"] == pending["id"]
    provider = CountingProvider(EXAMPLE.read_text(encoding="utf-8"))
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    cached = client.post(path, json=body).json()
    assert cached["status"] == "COMPLETED" and cached["cache_hit"]
    assert cached["id"] == pending["id"]
    assert cached["usage"]["calls"] == 0 and provider.calls == 1
    with Session(engine) as session:
        assert session.query(Job).count() == 1
        frozen = session.get(Job, pending["job_id"])
        assert frozen.payload["model_snapshot"]["model"] == "test-model"
    snapshot["parameters"] = {"temperature": 0.5}
    changed = client.post(path, json=body).json()
    assert changed["status"] == "PENDING" and changed["id"] != pending["id"]
    new_provider = CountingProvider(
        EXAMPLE.read_text(encoding="utf-8"), parameters={"temperature": 0.5}
    )
    asyncio.run(execute_overview(engine, changed["job_id"], tmp_path, provider=new_provider))
    with Session(engine) as session:
        assert session.get(Job, changed["job_id"]).status == "succeeded"
        assert session.query(LiteCacheEntry).count() == 2
    assert new_provider.calls == 1


def test_failed_raw_and_usage_are_retained_without_reissuing(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id = _seed_overview_fixture()
    job_id = _add_job(engine, project_id, paper_id, revision_id)
    provider = CountingProvider('{"invalid":true}')
    asyncio.run(execute_overview(engine, job_id, tmp_path, provider=provider))
    asyncio.run(execute_overview(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as session:
        result = session.scalar(
            select(PaperOverviewResult).where(PaperOverviewResult.job_id == job_id)
        )
        usage = session.query(LiteTokenUsage).one()
        assert result.status == "FAILED" and result.raw_output == '{"invalid":true}'
        assert usage.status == "failed" and usage.total_tokens == 200
    assert provider.calls == 1
