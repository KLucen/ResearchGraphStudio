"""Anonymous card sets cannot replace or revive independent library graphs."""

from uuid import uuid4

from researchgraph.close_reading_api import _current_graph
from researchgraph.knowledge_library_api import register_knowledge_library_api
from researchgraph.knowledge_library_models import PaperKnowledgeVersion
from researchgraph.knowledge_workflow_api import register_knowledge_workflow_api
from researchgraph.model_document_models import LlmDocumentOutput
from researchgraph.model_document_overview import validate_model_overview
from researchgraph.models import AttachmentRevision, Job
from researchgraph.paper_overview_api import register_paper_overview_api
from researchgraph.paper_overview_models import PaperOverviewResult
from researchgraph.reading_state_api import (
    current_overview,
    list_concept_understanding,
    node_fingerprint,
)
from researchgraph.reading_state_models import ConceptUnderstanding
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_knowledge_library import EXAMPLE, _collect, _fixture, _headers
from test_model_card_set import fixture as model_fixture
from test_reading_state import _overview
from test_reading_state import fixture as fixture


def _new_row(db, legacy):
    row = PaperOverviewResult(
        id=str(uuid4()),
        project_id=legacy.project_id,
        paper_id=legacy.paper_id,
        document_version_id=legacy.document_version_id,
        pdf_hash=legacy.pdf_hash,
        input_hash="e" * 64,
        cache_key="f" * 64,
        schema_version="paper-card-set-2",
        prompt_version="paper-card-set-extract-1",
        provider_id="synthetic",
        model_id="synthetic",
        status="COMPLETED",
        paper_card_json={"schema_version": "paper-card-set-2"},
        graph_json=None,
        created_at="2099-01-01T00:00:00Z",
        updated_at="2099-01-01T00:00:00Z",
    )
    db.add(row)
    return row.id


def test_retired_local_overview_stays_out_of_reading_but_library_snapshot_survives(tmp_path):
    engine, client, paper_id, revision_id, legacy_id = _fixture(tmp_path)
    register_paper_overview_api(client.app, lambda: engine, tmp_path)
    with Session(engine) as db, db.begin():
        row = db.get(PaperOverviewResult, legacy_id)
        node = row.graph_json["nodes"][0]
        saved = ConceptUnderstanding(
            id=str(uuid4()),
            paper_id=paper_id,
            document_version_id=revision_id,
            overview_result_id=legacy_id,
            graph_node_id=node["id"],
            node_fingerprint=node_fingerprint(node),
            node_snapshot=node,
            self_level="CONFIDENT",
            note_zh="Personal history must remain available.",
        )
        db.add(saved)
    assert client.get(f"/api/v1/papers/{paper_id}/overview").json() is None
    with Session(engine) as db:
        assert current_overview(db, paper_id, revision_id) is None
        views = list_concept_understanding(db, paper_id, revision_id)
        assert len(views) == 1
        assert views[0].association_status == "NEEDS_RELINK"
        assert views[0].note_zh == "Personal history must remain available."
        assert db.scalar(select(Job)) is None
    collected = _collect(client, paper_id, revision_id)
    assert collected.status_code == 200, collected.text
    version = collected.json()["current_version"]
    assert version["source_id"] == legacy_id
    assert version["content"]["graph"]["nodes"][0]["type"] == "PAPER"


def test_new_local_card_row_never_masks_or_enters_legacy_library_collection(tmp_path):
    engine, client, paper_id, revision_id, legacy_id = _fixture(tmp_path)
    register_knowledge_workflow_api(client.app, lambda: engine, tmp_path)
    with Session(engine) as db, db.begin():
        new_id = _new_row(db, db.get(PaperOverviewResult, legacy_id))
    options = client.get("/api/v1/knowledge/source-options").json()["items"][0]["sources"]
    assert options[0]["has_overview"] is True
    assert options[0]["overview_result_id"] == legacy_id
    collected = _collect(client, paper_id, revision_id)
    assert collected.status_code == 200, collected.text
    assert collected.json()["current_version"]["source_id"] == legacy_id
    rejected = client.post(
        "/api/v1/knowledge/papers/collect",
        headers=_headers("new-card-is-not-a-graph"),
        json={
            "paper_id": paper_id,
            "source_kind": "local_revision",
            "source_id": revision_id,
            "overview_result_id": new_id,
        },
    )
    assert rejected.status_code == 409
    with Session(engine) as db:
        assert db.query(PaperKnowledgeVersion).count() == 1
        assert db.scalar(select(Job)) is None


def test_new_model_card_row_never_masks_or_enters_legacy_library_collection(tmp_path, monkeypatch):
    engine, client, paper_id, parse_id, session_id = model_fixture(tmp_path, monkeypatch)
    register_knowledge_library_api(client.app, lambda: engine, tmp_path)
    register_knowledge_workflow_api(client.app, lambda: engine, tmp_path)
    legacy_id, new_id = str(uuid4()), str(uuid4())
    with Session(engine) as db, db.begin():
        for identity, payload, created in (
            (
                legacy_id,
                validate_model_overview(EXAMPLE.read_text(encoding="utf-8"), paper_id),
                "2026-01-01T00:00:00Z",
            ),
            (new_id, {"schema_version": "paper-card-set-2"}, "2099-01-01T00:00:00Z"),
        ):
            db.add(
                LlmDocumentOutput(
                    id=identity,
                    import_session_id=session_id,
                    parse_id=parse_id,
                    item_kind="paper_overview",
                    status="succeeded",
                    output_json=payload,
                    created_at=created,
                    updated_at=created,
                )
            )
    sources = client.get("/api/v1/knowledge/source-options").json()["items"][0]["sources"]
    assert sources[0]["overview_result_id"] == legacy_id
    body = {"paper_id": paper_id, "source_kind": "model_parse", "source_id": parse_id}
    collected = client.post("/api/v1/knowledge/papers/collect", headers=_headers(), json=body)
    assert collected.status_code == 200, collected.text
    assert collected.json()["current_version"]["source_id"] == legacy_id
    rejected = client.post(
        "/api/v1/knowledge/papers/collect",
        headers=_headers("explicit-new-model-card"),
        json={**body, "overview_result_id": new_id},
    )
    assert rejected.status_code == 409
    with Session(engine) as db:
        assert db.query(PaperKnowledgeVersion).count() == 1
        assert db.scalar(select(Job)) is None


def test_close_reading_uses_visible_new_card_version_and_only_key_concepts(fixture):
    f = fixture
    with Session(f.engine) as db, db.begin():
        original = db.get(PaperOverviewResult, f.overview_id)
        base = original.paper_card_json["wire_draft"]["cards"][0]
        extra = dict(base, id="c2", kind="core_contribution", title_zh="Contribution")
        old = _overview(
            db,
            f.paper_id,
            f.project_id,
            f.revision_id,
            updated="2026-11-14T01:00:00Z",
            cards=[base, extra],
        )
        old.updated_at = "2099-01-01T00:00:00Z"
        latest = _overview(
            db,
            f.paper_id,
            f.project_id,
            f.revision_id,
            updated="2026-11-14T02:00:00Z",
            cards=[base, extra],
        )
        db.add_all([old, latest])
        original.schema_version = "paper_overview_graph.v1"
        original.created_at = original.updated_at = "2099-01-01T00:00:00Z"
        original.graph_json = {"nodes": [{"id": "retired-node", "type": "CONCEPT"}]}
        db.flush()
        assert current_overview(db, f.paper_id, f.revision_id).id == latest.id
        overview_id, concepts = _current_graph(
            db, f.paper_id, db.get(AttachmentRevision, f.revision_id)
        )
        assert overview_id == latest.id
        assert [node["id"] for node in concepts] == [latest.paper_card_json["cards"][0]["id"]]
        assert all(node["type"] == "CONCEPT" for node in concepts)
        assert latest.graph_json is None
