"""The overview feature consumes both parser sources through one semantic DTO."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.model_document_models import (
    LlmDocumentOutput,
    LlmDocumentParse,
    LlmDocumentSegment,
)
from researchgraph.model_document_overview import (
    MODEL_OVERVIEW_PROMPT,
    build_model_overview_context,
    model_overview_schema,
    model_overview_view,
    register_model_overview_api,
    validate_model_overview,
)
from researchgraph.model_document_overview_models import (
    ModelOverviewGraphLayout,
    ModelOverviewGraphViewport,
)
from researchgraph.models import AttachmentRevision, Base, Chunk, Job, Paper, Project, now
from researchgraph.paper_overview_api import SYSTEM_PROMPT, overview_schema
from researchgraph.storage import make_engine
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

EXAMPLE = Path(
    "docs/ResearchGraph_Lite_LightGraph_Addendum/examples/paper_overview_graph.example.json"
)


def _fixture(tmp_path, *, output=None):
    engine = make_engine(tmp_path / "overview.sqlite3")
    Base.metadata.create_all(engine)
    project_id, paper_id, session_id, parse_id = (str(uuid4()) for _ in range(4))
    with Session(engine) as db, db.begin():
        db.add(Project(id=project_id, name="test", description="", created_at=now()))
        db.flush()
        db.add(Paper(id=paper_id, project_id=project_id, title="Test paper", created_at=now()))
        db.flush()
        db.add(
            ImportSession(
                id=session_id,
                project_id=project_id,
                source_kind="pdf",
                selection_id="synthetic",
                source_snapshot={"paper_id": paper_id},
                plan={"overview": False, "reading": False, "allow_network": True},
                status="succeeded",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.add(
            LlmDocumentParse(
                id=parse_id,
                import_session_id=session_id,
                parse_version="llm-document-1",
                modality="text",
                status="succeeded",
                warnings=[],
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        for index, (title, kind, text) in enumerate(
            [
                ("Introduction", "paragraph", "Research question from model parse."),
                ("Methods", "formula", "E=mc^2"),
                ("Results", "table", "A|B\n1|2"),
                ("4 References", "paragraph", "REFERENCE_MARKER"),
            ]
        ):
            db.add(
                LlmDocumentSegment(
                    id=str(uuid4()),
                    parse_id=parse_id,
                    chapter_ref=f"chapter-{index}",
                    chapter_title=title,
                    chapter_level=1,
                    chapter_order=index,
                    kind=kind,
                    ordinal=0,
                    text=text if kind != "table" else None,
                    latex=text if kind == "formula" else None,
                    raw_table_text=text if kind == "table" else None,
                    status="ok",
                    warnings=[],
                    created_at=now(),
                )
            )
        if output is not None:
            db.add(
                LlmDocumentOutput(
                    id=str(uuid4()),
                    import_session_id=session_id,
                    parse_id=parse_id,
                    item_kind="paper_overview",
                    status="succeeded",
                    output_json=(
                        validate_model_overview(EXAMPLE.read_text(encoding="utf-8"), paper_id)
                        if output is True
                        else output
                    ),
                    usage={"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
                    created_at=now(),
                    updated_at=now(),
                )
            )
    app = FastAPI()
    register_model_overview_api(app, lambda: engine)
    return engine, TestClient(app), paper_id, parse_id, session_id


def test_model_overview_uses_the_shared_card_graph_contract_and_strict_decoding():
    assert model_overview_schema() == overview_schema()
    assert MODEL_OVERVIEW_PROMPT == SYSTEM_PROMPT
    raw = EXAMPLE.read_text(encoding="utf-8")
    payload = validate_model_overview(raw, "paper-1")
    assert payload["paper_card"]["research_question"]
    assert payload["graph"]["nodes"]
    assert payload == validate_model_overview(raw, "paper-1")
    assert payload == validate_model_overview(payload, "paper-1")
    assert payload == validate_model_overview(json.loads(raw), "paper-1")
    with pytest.raises(ValueError, match="身份与当前论文不匹配"):
        validate_model_overview(payload, "other-paper")
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        validate_model_overview('{"schema_version":"x","schema_version":"y"}', "paper-1")
    extra = json.loads(raw)
    extra["unapproved_field"] = "not allowed"
    with pytest.raises(ValueError):
        validate_model_overview(json.dumps(extra), "paper-1")
    extra = json.loads(raw)
    extra["paper_card"]["motivation"] = float("nan")
    with pytest.raises(ValueError, match="Non-finite"):
        validate_model_overview(json.dumps(extra), "paper-1")


def test_context_reads_model_sections_formulas_and_tables_without_legacy_chunks(tmp_path):
    engine, _client, paper_id, parse_id, _session_id = _fixture(tmp_path)
    with Session(engine) as db:
        context = build_model_overview_context(db, db.get(LlmDocumentParse, parse_id))
        assert context["paper_id"] == paper_id
        assert context["document_version_id"] == parse_id
        assert len(context["chapters"]) == 3
        assert context["chapters"][1]["segments"][0]["latex"] == "E=mc^2"
        assert context["chapters"][2]["segments"][0]["raw_table_text"] == "A|B\n1|2"
        assert "REFERENCE_MARKER" not in json.dumps(context)
        assert db.query(AttachmentRevision).count() == 0
        assert db.query(Chunk).count() == 0


def test_unselected_or_legacy_summary_overview_is_not_generated_on_get(tmp_path):
    engine, client, paper_id, parse_id, session_id = _fixture(tmp_path)
    endpoint = f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}"
    assert client.get(endpoint).json() is None
    with Session(engine) as db:
        assert db.query(Job).count() == db.query(LlmDocumentOutput).count() == 0
        assert db.get(ImportSession, session_id).plan["overview"] is False
    with Session(engine) as db, db.begin():
        db.add(
            LlmDocumentOutput(
                id=str(uuid4()),
                import_session_id=session_id,
                parse_id=parse_id,
                item_kind="paper_overview",
                status="succeeded",
                output_json={"item_kind": "paper_overview", "summary": "Legacy summary"},
                created_at=now(),
                updated_at=now(),
            )
        )
    assert client.get(endpoint).json() is None
    with Session(engine) as db:
        assert db.query(Job).count() == 0
        assert db.query(LlmDocumentOutput).one().output_json["summary"] == "Legacy summary"


def test_projected_overview_and_layout_enforce_source_scope_and_keep_semantics_unchanged(tmp_path):
    engine, client, paper_id, parse_id, _session_id = _fixture(tmp_path, output=True)
    with Session(engine) as db:
        normalized = db.query(LlmDocumentOutput).one().output_json
    base = f"/api/v1/papers/{paper_id}/model-overview"
    response = client.get(base, params={"parse_id": parse_id})
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["status"] == "COMPLETED"
    assert view["document_version_id"] == parse_id
    assert view["paper_card"] == normalized["paper_card"]
    assert view["graph"] == normalized["graph"]
    assert view["usage"]["total_tokens"] == 45
    output_id = view["id"]
    node_id = normalized["graph"]["nodes"][0]["id"]
    layout = {
        "overview_result_id": output_id,
        "positions": [{"node_id": node_id, "x": 15.5, "y": -18.0, "pinned": True}],
        "viewport": {"x": 20, "y": -10, "zoom": 1.25},
    }
    saved = client.post(base + "/graph/layout", json=layout)
    assert saved.status_code == 200, saved.text
    assert saved.json() == layout
    assert (
        client.get(base + "/graph/layout", params={"overview_result_id": output_id}).json()
        == layout
    )
    invalid = {**layout, "positions": [{**layout["positions"][0], "node_id": "not-in-graph"}]}
    assert client.post(base + "/graph/layout", json=invalid).status_code == 422
    assert (
        client.get(f"/api/v1/papers/other-paper/model-overview?parse_id={parse_id}").status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/papers/other-paper/model-overview/graph/layout", json=layout
        ).status_code
        == 404
    )
    with Session(engine) as db:
        assert db.get(LlmDocumentOutput, output_id).output_json == normalized
        assert db.query(ModelOverviewGraphLayout).count() == 1
        assert db.query(ModelOverviewGraphViewport).count() == 1
    reset = client.post(base + "/graph/layout/reset", json={"overview_result_id": output_id})
    assert reset.status_code == 200
    assert reset.json()["positions"] == [] and reset.json()["viewport"] is None
    assert client.post(base + "/graph/layout", json=layout).status_code == 200
    with Session(engine) as db, db.begin():
        db.execute(delete(LlmDocumentOutput).where(LlmDocumentOutput.id == output_id))
    with Session(engine) as db:
        assert db.query(ModelOverviewGraphLayout).count() == 0
        assert db.query(ModelOverviewGraphViewport).count() == 0


def test_projection_rejects_wrong_parse_and_invalid_stored_semantics(tmp_path):
    engine, _client, _paper_id, parse_id, session_id = _fixture(tmp_path)
    with Session(engine) as db, db.begin():
        parse = db.get(LlmDocumentParse, parse_id)
        output = LlmDocumentOutput(
            id=str(uuid4()),
            import_session_id=session_id,
            parse_id=parse_id,
            item_kind="paper_reading",
            status="succeeded",
            created_at=now(),
            updated_at=now(),
        )
        with pytest.raises(ValueError, match="归属不匹配"):
            model_overview_view(db, parse, output)
        output.item_kind = "paper_overview"
        output.output_json = {"schema_version": "paper_overview_graph.v1", "paper_card": {}}
        with pytest.raises(ValueError):
            model_overview_view(db, parse, output)


def test_explicit_generate_creates_one_pending_output_and_shared_contract_result(
    tmp_path, monkeypatch
):
    from researchgraph import model_settings
    from researchgraph.model_document_api import execute_document_postprocess

    engine, client, paper_id, parse_id, session_id = _fixture(tmp_path)
    monkeypatch.setattr(
        model_settings,
        "snapshot_for",
        lambda *args: {"provider": "synthetic", "model": "synthetic", "parameters": {}},
    )
    endpoint = f"/api/v1/papers/{paper_id}/model-overview/generate"
    body = {"document_version_id": parse_id, "allow_network": False}
    assert client.post(endpoint, json=body).status_code == 409
    body["allow_network"] = True
    first = client.post(endpoint, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    assert first.json()["usage"]["calls"] == 0
    assert client.post(endpoint, json=body).json() == first.json()
    with Session(engine) as db:
        assert db.query(Job).count() == 1
        assert db.query(LlmDocumentOutput).count() == 1
        job = db.query(Job).one()
        job_id = job.id
        assert job.payload["postprocess_contract_version"] == 2
        assert db.get(ImportSession, session_id).plan["overview"] is False

    class Provider:
        name = "synthetic"
        model = "synthetic"
        usage = {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45}
        calls = 0

        async def complete(self, prompt, data, schema):
            self.calls += 1
            assert prompt == SYSTEM_PROMPT
            assert schema == overview_schema()
            assert data["document_version_id"] == parse_id
            return EXAMPLE.read_text(encoding="utf-8")

    provider = Provider()
    asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    response = client.get(
        f"/api/v1/papers/{paper_id}/model-overview", params={"parse_id": parse_id}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["paper_card"] and response.json()["graph"]["nodes"]
    assert client.post(endpoint, json=body).json() == response.json()
    assert provider.calls == 1
    with Session(engine) as db:
        assert db.get(Job, job_id).status == "succeeded"
        assert db.scalar(select(ImportPlanItem)).status == "succeeded"
        assert db.query(AttachmentRevision).count() == db.query(Chunk).count() == 0
        original_json = db.get(LlmDocumentOutput, first.json()["id"]).output_json
    regenerated = client.post(endpoint, json={**body, "force_regenerate": True})
    assert regenerated.status_code == 200, regenerated.text
    assert regenerated.json()["status"] == "PENDING"
    assert regenerated.json()["id"] != first.json()["id"]
    assert regenerated.json()["display_result_id"] == first.json()["id"]
    assert regenerated.json()["paper_card"] == response.json()["paper_card"]
    with Session(engine) as db:
        assert db.query(Job).count() == 2
        assert db.query(LlmDocumentOutput).count() == 2
        old = db.get(LlmDocumentOutput, first.json()["id"])
        assert old.status == "succeeded" and old.output_json == original_json
    assert provider.calls == 1


def test_failed_or_running_regeneration_keeps_prior_valid_graph_until_source_changes(tmp_path):
    engine, client, paper_id, parse_id, session_id = _fixture(tmp_path, output=True)
    with Session(engine) as db, db.begin():
        prior = db.query(LlmDocumentOutput).one()
        prior_id = prior.id
        parse = db.get(LlmDocumentParse, parse_id)
        prior.usage = {"source_updated_at": parse.updated_at}
        current_id = str(uuid4())
        db.add(
            LlmDocumentOutput(
                id=current_id,
                import_session_id=session_id,
                parse_id=parse_id,
                item_kind="paper_overview",
                status="failed",
                error_code="MODEL_DOCUMENT_POSTPROCESS_CONTRACT_FAILED",
                error="Failed current draft",
                usage={"source_updated_at": parse.updated_at},
                created_at="2099-01-01T00:00:00Z",
                updated_at="2099-01-01T00:00:00Z",
            )
        )
    endpoint = f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}"
    failed = client.get(endpoint).json()
    assert failed["id"] == current_id and failed["status"] == "FAILED"
    assert failed["error"] == "Failed current draft"
    assert failed["display_result_id"] == prior_id
    assert failed["paper_card"] and failed["graph"]["nodes"]
    assert (
        client.get(
            f"/api/v1/papers/{paper_id}/model-overview/graph/layout",
            params={"overview_result_id": failed["display_result_id"]},
        ).status_code
        == 200
    )
    with Session(engine) as db, db.begin():
        db.get(LlmDocumentOutput, current_id).status = "running"
    running = client.get(endpoint).json()
    assert running["status"] == "PENDING" and running["display_result_id"] == prior_id
    with Session(engine) as db, db.begin():
        db.get(LlmDocumentParse, parse_id).updated_at = "2099-01-02T00:00:00Z"
        db.get(LlmDocumentOutput, prior_id).status = "stale"
    changed = client.get(endpoint).json()
    assert changed["paper_card"] is None and changed["graph"] is None
    assert changed["display_result_id"] is None
