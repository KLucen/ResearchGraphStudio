"""New model-source overview card sets retain source and request boundaries."""

import asyncio
import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.import_plan_api import create_import_session_record
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.knowledge_library_models import KnowledgeLibrary
from researchgraph.model_document_api import (
    _queue_selected_postprocessing,
    _validate_output,
    execute_document_postprocess,
    queue_model_document_output,
    register_model_document_api,
)
from researchgraph.model_document_models import (
    LlmDocumentOutput,
    LlmDocumentOutputLocalRecovery,
    LlmDocumentParse,
    LlmDocumentSegment,
)
from researchgraph.model_document_overview import register_model_overview_api
from researchgraph.models import AttachmentRevision, Base, Chunk, Job, Paper, Project, now
from researchgraph.paper_card_set_contracts import (
    ANCHORED_PROMPT_VERSION,
    MODEL_CARD_CONTRACT_VERSION,
    SCHEMA_VERSION,
    model_card_prompt,
    model_card_schema,
    validate_paper_card_set,
)
from researchgraph.paper_card_set_service import build_card_manifest, card_context
from researchgraph.schemas import ImportPlan, SourceSnapshot
from researchgraph.storage import make_engine
from sqlalchemy import select
from sqlalchemy.orm import Session


def fixture(tmp_path, monkeypatch):
    from researchgraph import model_settings

    monkeypatch.setattr(
        model_settings,
        "snapshot_for",
        lambda *args: {"provider": "synthetic", "model": "synthetic", "parameters": {}},
    )
    engine = make_engine(tmp_path)
    assert KnowledgeLibrary.__tablename__ in Base.metadata.tables
    Base.metadata.create_all(engine)
    project_id, paper_id, session_id, parse_id = (str(uuid4()) for _ in range(4))
    with Session(engine) as db, db.begin():
        db.add(Project(id=project_id, name="Synthetic", description="", created_at=now()))
        db.flush()
        db.add(Paper(id=paper_id, project_id=project_id, title="Synthetic paper", created_at=now()))
        db.flush()
        db.add(
            ImportSession(
                id=session_id,
                project_id=project_id,
                source_kind="pdf",
                selection_id="synthetic",
                source_snapshot={"paper_id": paper_id},
                plan={},
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
                parse_version="synthetic-1",
                modality="text",
                status="succeeded",
                warnings=[],
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.add(
            LlmDocumentSegment(
                id=str(uuid4()),
                parse_id=parse_id,
                chapter_ref="c0",
                chapter_title="Methods",
                chapter_order=0,
                chapter_level=1,
                ordinal=0,
                kind="paragraph",
                text="The authors propose a synthetic method.",
                status="ok",
                warnings=[],
                locator=None,
                created_at=now(),
            )
        )
    app = FastAPI()
    register_model_overview_api(app, lambda: engine)
    register_model_document_api(app, lambda: engine)
    return engine, TestClient(app), paper_id, parse_id, session_id


def response(context):
    source = context["sources"][0]
    evidence = {"translation_zh": "作者提出一种合成方法。"}
    if "excerpts" in source:
        evidence["excerpt_id"] = source["excerpts"][0]["excerpt_id"]
    else:
        evidence.update(source_id=source["source_id"], quote_en=source["text"], occurrence_index=0)
    return {
        "schema_version": SCHEMA_VERSION,
        "article_overview_zh": "作者提出一种合成方法。",
        "overview_card_ids": ["c1"],
        "card_set_intro_zh": "方法卡片可返回解析材料核对。",
        "coverage_notes": ["这是软件回归夹具。"],
        "cards": [
            {
                "id": "c1",
                "kind": "architecture_algorithm",
                "attribution": "AUTHOR",
                "title_zh": "合成方法",
                "title_en": None,
                "body_zh": "作者提出一种合成方法。",
                "reading_guide_zh": "核对其具体条件。",
                "evidence": [evidence],
            }
        ],
    }


class Provider:
    name = model = "synthetic"
    usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}

    def __init__(self, mutate=None):
        self.calls = 0
        self.mutate = mutate
        self.raw = None

    async def complete(self, prompt, context, schema):
        self.calls += 1
        if "source_context" in context:
            context = context["source_context"]
        version = MODEL_CARD_CONTRACT_VERSION if "excerpts" in context["sources"][0] else 5
        assert prompt.startswith(model_card_prompt(version)) and schema == model_card_schema(
            version
        )
        value = response(context)
        if self.mutate:
            self.mutate(value)
        self.raw = json.dumps(value, ensure_ascii=False)
        return self.raw


def queue(values):
    engine, client, paper_id, parse_id, _session_id = values
    result = client.post(
        f"/api/v1/papers/{paper_id}/model-overview/generate",
        json={
            "document_version_id": parse_id,
            "allow_network": True,
        },
    )
    assert result.status_code == 200, result.text
    with Session(engine) as db:
        job = db.get(Job, result.json()["job_id"])
        assert job.payload["postprocess_contract_version"] == MODEL_CARD_CONTRACT_VERSION
    return result.json()


def test_model_cards_generate_from_segments_and_get_is_read_only(tmp_path, monkeypatch):
    values = fixture(tmp_path, monkeypatch)
    engine, client, paper_id, parse_id, session_id = values
    path = f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}"
    assert client.get(path).json() is None
    with Session(engine) as db:
        assert db.query(Job).count() == 0
    pending = queue(values)
    assert pending["card_set"] is None and pending["graph"] is None
    provider = Provider()
    asyncio.run(
        execute_document_postprocess(engine, pending["job_id"], tmp_path, provider=provider)
    )
    saved = client.get(path).json()
    assert saved["status"] == "COMPLETED"
    assert saved["schema_version"] == SCHEMA_VERSION
    assert saved["prompt_version"] == saved["card_set"]["prompt_version"] == ANCHORED_PROMPT_VERSION
    assert saved["paper_card"] is None and saved["graph"] is None
    evidence = saved["card_set"]["cards"][0]["evidence"][0]
    assert evidence["quote_en"] == "The authors propose a synthetic method."
    assert evidence["position"]["page_start"] is None
    assert evidence["position"]["segment_id"]
    assert client.get(path).json() == saved
    assert provider.calls == 1
    with Session(engine) as db:
        assert db.query(AttachmentRevision).count() == db.query(Chunk).count() == 0
        output = db.get(LlmDocumentOutput, pending["id"])
        assert output.raw_response == provider.raw
        assert output.usage["card_set_contract"]["source_fingerprint"]
    assert queue(values) == saved
    edit = client.patch(
        f"/api/v1/import-sessions/{session_id}/document-outputs/{saved['id']}",
        json={"output_json": saved["card_set"]},
    )
    assert edit.status_code == 200, edit.text
    assert client.get(path).json()["card_set"] == saved["card_set"]
    assert (
        client.get(
            f"/api/v1/papers/{paper_id}/model-overview/graph/layout",
            params={"overview_result_id": saved["id"]},
        ).status_code
        == 409
    )
    asyncio.run(
        execute_document_postprocess(engine, pending["job_id"], tmp_path, provider=provider)
    )
    assert provider.calls == 1


def test_legacy_overview_is_not_displayed_or_reused_as_new_cards(tmp_path, monkeypatch):
    values = fixture(tmp_path, monkeypatch)
    engine, client, paper_id, parse_id, session_id = values
    old = {"schema_version": "paper_overview_graph.v1", "paper_card": {}, "graph": {}}
    with Session(engine) as db, db.begin():
        db.add(
            LlmDocumentOutput(
                id=str(uuid4()),
                import_session_id=session_id,
                parse_id=parse_id,
                item_kind="paper_overview",
                status="succeeded",
                output_json=copy.deepcopy(old),
                created_at=now(),
                updated_at=now(),
            )
        )
    assert (
        client.get(f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}").json() is None
    )
    pending = queue(values)
    assert pending["status"] == "PENDING" and pending["display_result_id"] is None
    with Session(engine) as db:
        assert db.query(LlmDocumentOutput).count() == 2
        assert (
            db.scalar(
                select(LlmDocumentOutput).where(LlmDocumentOutput.status == "succeeded")
            ).output_json
            == old
        )


@pytest.mark.parametrize(
    "change", ["bad_excerpt", "source_before", "source_during", "locator_during", "cancel"]
)
def test_invalid_or_changed_or_cancelled_cards_never_publish(tmp_path, monkeypatch, change):
    values = fixture(tmp_path, monkeypatch)
    engine, client, paper_id, parse_id, _ = values
    pending = queue(values)

    def mutation(value):
        if change == "bad_excerpt":
            value["cards"][0]["evidence"][0]["excerpt_id"] = "q9999"
        elif change in {"source_during", "locator_during", "cancel"}:
            with Session(engine) as db, db.begin():
                if change == "cancel":
                    db.get(Job, pending["job_id"]).status = "cancelled"
                elif change == "locator_during":
                    db.scalar(select(LlmDocumentSegment)).locator = {"page": 10}
                else:
                    db.scalar(select(LlmDocumentSegment)).text = "Changed material."

    provider = Provider(mutation)
    if change == "source_before":
        with Session(engine) as db, db.begin():
            db.scalar(select(LlmDocumentSegment)).text = "Changed before send."
    try:
        asyncio.run(
            execute_document_postprocess(engine, pending["job_id"], tmp_path, provider=provider)
        )
    except ValueError:
        pass
    with Session(engine) as db:
        output = db.get(LlmDocumentOutput, pending["id"])
        assert output.status != "succeeded" and output.output_json is None
        assert db.get(Job, pending["job_id"]).status in {"failed", "cancelled"}
        if change in {"source_before", "source_during", "locator_during"}:
            assert output.error_code == "DOCUMENT_OUTPUT_SOURCE_CHANGED"
        if change != "source_before":
            assert output.raw_response == provider.raw and output.usage["requests"]
    assert provider.calls == (0 if change == "source_before" else 1)
    if change != "source_before":
        assert (
            client.get(f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}").json()[
                "card_set"
            ]
            is None
        )


def test_selected_import_overview_publishes_one_pending_new_card_output(tmp_path, monkeypatch):
    values = fixture(tmp_path, monkeypatch)
    engine, client, paper_id, parse_id, session_id = values
    with Session(engine) as db, db.begin():
        session = db.get(ImportSession, session_id)
        session.plan = {"allow_network": True, "overview_contract_version": 5}
        db.add(
            ImportPlanItem(
                id=str(uuid4()),
                session_id=session_id,
                item_kind="paper_overview",
                status="planned",
                config={},
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        parse = db.get(LlmDocumentParse, parse_id)
        _queue_selected_postprocessing(db, session, parse)
        _queue_selected_postprocessing(db, session, parse)
    pending = client.get(f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}").json()
    assert pending["status"] == "PENDING" and pending["job_id"]
    with Session(engine) as db:
        assert db.query(LlmDocumentOutput).count() == db.query(Job).count() == 1
        job = db.get(Job, pending["job_id"])
        assert job.payload["output_id"] == pending["id"]
    provider = Provider()
    asyncio.run(
        execute_document_postprocess(engine, pending["job_id"], tmp_path, provider=provider)
    )
    assert provider.calls == 1
    assert client.get(f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}").json()[
        "card_set"
    ]["cards"]


def test_optional_cards_without_text_fail_without_rolling_back_successful_parse(
    tmp_path, monkeypatch
):
    values = fixture(tmp_path, monkeypatch)
    engine, client, paper_id, parse_id, session_id = values
    with Session(engine) as db, db.begin():
        session = db.get(ImportSession, session_id)
        session.plan = {
            "allow_network": True,
            "overview_contract_version": 5,
            "postprocess_contract_version": 4,
        }
        db.scalar(select(LlmDocumentSegment)).text = None
        for kind in ("paper_overview", "paper_reading"):
            db.add(
                ImportPlanItem(
                    id=str(uuid4()),
                    session_id=session_id,
                    item_kind=kind,
                    status="planned",
                    config={},
                    created_at=now(),
                    updated_at=now(),
                )
            )
        db.flush()
        _queue_selected_postprocessing(db, session, db.get(LlmDocumentParse, parse_id))
    failed = client.get(f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}").json()
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "DOCUMENT_OUTPUT_SOURCE_UNAVAILABLE"
    assert failed["card_set"] is None and failed["usage"]["calls"] == 0
    provider = Provider()
    asyncio.run(execute_document_postprocess(engine, failed["job_id"], tmp_path, provider=provider))
    assert provider.calls == 0
    with Session(engine) as db:
        assert db.get(LlmDocumentParse, parse_id).status == "succeeded"
        assert db.query(LlmDocumentSegment).count() == 1
        reading = db.scalar(
            select(ImportPlanItem).where(ImportPlanItem.item_kind == "paper_reading")
        )
        assert reading.status == "queued" and db.get(Job, reading.job_id).status == "queued"


def test_new_contract_stays_separate_from_legacy_and_rejects_expanded_wire(tmp_path, monkeypatch):
    values = fixture(tmp_path, monkeypatch)
    engine, _client, paper_id, parse_id, _ = values
    with Session(engine) as db:
        parse = db.get(LlmDocumentParse, parse_id)
        manifest = build_card_manifest(db, paper_id, "model_parse", parse_id)
        wire = response(card_context(manifest))
        saved = validate_paper_card_set(wire, manifest)
        with pytest.raises(ValueError):
            _validate_output(db, parse, json.dumps(wire), "paper_overview", paper_id, True, 2)
        with pytest.raises(ValueError):
            _validate_output(db, parse, json.dumps(saved), "paper_overview", paper_id, True, 5)
        assert _validate_output(db, parse, saved, "paper_overview", paper_id, True, 5) == saved


def test_saved_tampering_rejects_read_and_does_not_block_explicit_regeneration(
    tmp_path, monkeypatch
):
    values = fixture(tmp_path, monkeypatch)
    engine, client, paper_id, parse_id, _ = values
    pending = queue(values)
    provider = Provider()
    asyncio.run(
        execute_document_postprocess(engine, pending["job_id"], tmp_path, provider=provider)
    )
    with Session(engine) as db, db.begin():
        output = db.get(LlmDocumentOutput, pending["id"])
        tampered = copy.deepcopy(output.output_json)
        tampered["cards"][0]["evidence"][0]["position"]["page_start"] = 44
        output.output_json = tampered
    assert (
        client.get(f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}").status_code
        == 409
    )
    regenerated = queue(values)
    assert regenerated["id"] != pending["id"] and regenerated["card_set"] is None
    assert provider.calls == 1


def test_failed_card_repair_revalidates_full_source_identity(tmp_path, monkeypatch):
    values = fixture(tmp_path, monkeypatch)
    engine, client, _paper_id, _parse_id, session_id = values
    pending = queue(values)
    provider = Provider(lambda value: value["cards"][0].update({"unexpected": "reject"}))
    with pytest.raises(ValueError):
        asyncio.run(
            execute_document_postprocess(engine, pending["job_id"], tmp_path, provider=provider)
        )
    path = f"/api/v1/import-sessions/{session_id}/document-outputs"
    assert client.get(path).json()[0]["format_repair_available"] is True
    with Session(engine) as db, db.begin():
        db.scalar(select(LlmDocumentSegment)).locator = {"page": 11}
    assert client.get(path).json()[0]["format_repair_available"] is False
    rejected = client.post(
        f"{path}/{pending['id']}/format-repair",
        json={"allow_network": True},
        headers={"Idempotency-Key": "changed-card-source"},
    )
    assert rejected.status_code == 409 and provider.calls == 1


@pytest.mark.parametrize("version", [5, MODEL_CARD_CONTRACT_VERSION])
def test_card_local_recovery_quarantines_the_entire_card_and_preserves_job(
    tmp_path, monkeypatch, version
):
    values = fixture(tmp_path, monkeypatch)
    engine, client, paper_id, parse_id, session_id = values
    path = f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}"
    with Session(engine) as db, db.begin():
        queue_model_document_output(
            db, session_id, "paper_overview", allow_network=True, card_contract_version=version
        )
    pending = client.get(path).json()

    def mixed_cards(value):
        bad = copy.deepcopy(value["cards"][0])
        bad.update(id="c2", title_zh="不可发布的卡片")
        second_evidence = copy.deepcopy(bad["evidence"][0])
        if version == 5:
            second_evidence["quote_en"] = "Invented quotation."
        else:
            second_evidence["excerpt_id"] = "q9999"
        bad["evidence"].append(second_evidence)
        value["cards"].append(bad)
        value["overview_card_ids"] = ["c1", "c2"]
        value["article_overview_zh"] = "不应保留的总览"

    failed = Provider(mixed_cards)
    with pytest.raises(ValueError):
        asyncio.run(
            execute_document_postprocess(engine, pending["job_id"], tmp_path, provider=failed)
        )
    summary = dict(original_cards=2, retained_cards=1, excluded_cards=1, invalid_evidence=1)
    preview = client.get(path).json()
    assert preview["status"] == "FAILED" and preview["card_set"] is None
    assert preview["local_recovery_available"] is True and preview["recovery_summary"] == summary
    recovery_path = (
        f"/api/v1/papers/{paper_id}/model-document-outputs/{pending['id']}/local-recovery"
    )
    headers = {"Idempotency-Key": "recover-card-set"}
    with Session(engine) as db:
        output = db.get(LlmDocumentOutput, pending["id"])
        original_usage = copy.deepcopy(output.usage)
        assert original_usage["validation_errors"] == [
            {
                "path": "cards[1].evidence[1].quote_en"
                if version == 5
                else "cards[1].evidence[1].excerpt_id",
                "code": "card_quote_not_found"
                if version == 5
                else "card_excerpt_reference_invalid",
            }
        ]
        assert db.query(LlmDocumentOutputLocalRecovery).count() == 0

    result = client.post(recovery_path, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "partial" and result.json()["recovery_summary"] == summary
    assert client.post(recovery_path, headers=headers).json() == result.json()
    recovered = client.get(path).json()
    assert (
        recovered["status"] == "PARTIAL" and recovered["card_set"] == result.json()["output_json"]
    )
    assert recovered["local_recovery_available"] is False
    assert len(recovered["card_set"]["cards"]) == 1
    assert recovered["card_set"]["article_overview_zh"] != "不应保留的总览"
    assert [card["id"] for card in recovered["card_set"]["cards"]] == recovered["card_set"][
        "overview_card_ids"
    ]
    with Session(engine) as db:
        output = db.get(LlmDocumentOutput, pending["id"])
        assert output.status == "failed" and output.raw_response == failed.raw
        assert output.usage == original_usage and output.output_json is None
        assert db.get(Job, pending["job_id"]).status == "failed"
        assert db.query(Job).count() == db.query(LlmDocumentOutputLocalRecovery).count() == 1
    assert failed.calls == 1
    generate_path = f"/api/v1/papers/{paper_id}/model-overview/generate"
    generate_body = {"allow_network": True, "document_version_id": parse_id}
    assert client.post(generate_path, json=generate_body).json() == recovered

    retry = client.post(generate_path, json={**generate_body, "force_regenerate": True}).json()
    bad_retry = Provider(lambda value: value["cards"][0].update(unexpected="reject"))
    with pytest.raises(ValueError):
        asyncio.run(
            execute_document_postprocess(engine, retry["job_id"], tmp_path, provider=bad_retry)
        )
    fallback = client.get(path).json()
    assert fallback["status"] == "FAILED" and fallback["id"] == retry["id"]
    assert fallback["display_result_id"] == pending["id"]
    assert fallback["display_recovery_summary"] == summary
    assert fallback["card_set"] == recovered["card_set"]
    with Session(engine) as db, db.begin():
        db.scalar(select(LlmDocumentSegment)).locator = {"page": 11}
    assert client.get(path).json()["card_set"] is None
    assert client.post(recovery_path, headers=headers).status_code == 409


def test_frozen_v5_card_format_repair_preserves_its_existing_wire(tmp_path, monkeypatch):
    engine, client, paper_id, parse_id, session_id = fixture(tmp_path, monkeypatch)
    with Session(engine) as db, db.begin():
        job_id = queue_model_document_output(
            db, session_id, "paper_overview", allow_network=True, card_contract_version=5
        ).id
    failed = Provider(lambda value: value["cards"][0].update(unexpected="reject"))
    with pytest.raises(ValueError):
        asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=failed))
    path = f"/api/v1/import-sessions/{session_id}/document-outputs"
    failed_output = client.get(path).json()[0]
    repair = client.post(
        f"{path}/{failed_output['id']}/format-repair",
        json={"allow_network": True},
        headers={"Idempotency-Key": "frozen-v5-format-repair"},
    )
    assert repair.status_code == 202, repair.text
    repair_job = repair.json()["id"]
    with Session(engine) as db:
        original, successor = db.get(Job, job_id), db.get(Job, repair_job)
        assert successor.payload["postprocess_contract_version"] == 5
        assert successor.payload["card_set_contract"] == original.payload["card_set_contract"]
    provider = Provider()
    asyncio.run(execute_document_postprocess(engine, repair_job, tmp_path, provider=provider))
    assert provider.calls == 1
    current = client.get(f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}").json()
    assert current["status"] == "COMPLETED"
    assert current["card_set"]["cards"][0]["evidence"][0]["quote_en"]
    assert client.get(path).json()[0]["status"] == "failed"


@pytest.mark.parametrize("version", [2, 3, 4])
def test_frozen_legacy_graph_jobs_keep_their_original_contract_and_are_hidden(
    tmp_path, monkeypatch, version
):
    from researchgraph.model_document_overview import (
        MODEL_OVERVIEW_PROMPT,
        model_overview_schema,
        validate_model_overview,
    )

    values = fixture(tmp_path, monkeypatch)
    engine, client, paper_id, parse_id, _ = values
    pending = queue(values)
    with Session(engine) as db, db.begin():
        job = db.get(Job, pending["job_id"])
        job.payload = {**job.payload, "postprocess_contract_version": version}
        db.get(LlmDocumentOutput, pending["id"]).usage = {"contract_version": version}

    class LegacyProvider:
        name = model = "synthetic"
        usage = {}
        calls = 0

        async def complete(self, prompt, context, schema):
            self.calls += 1
            assert prompt == MODEL_OVERVIEW_PROMPT and schema == model_overview_schema()
            assert "chapters" in context and "sources" not in context
            return Path(
                "docs/ResearchGraph_Lite_LightGraph_Addendum/examples/paper_overview_graph.example.json"
            ).read_text(encoding="utf-8")

    provider = LegacyProvider()
    asyncio.run(
        execute_document_postprocess(engine, pending["job_id"], tmp_path, provider=provider)
    )
    assert provider.calls == 1
    with Session(engine) as db:
        output = db.get(LlmDocumentOutput, pending["id"])
        assert output.status == "succeeded"
        assert output.usage["contract_version"] == version
        assert validate_model_overview(output.output_json, paper_id) == output.output_json
    assert (
        client.get(f"/api/v1/papers/{paper_id}/model-overview?parse_id={parse_id}").json() is None
    )


def test_import_plan_freezes_new_overview_version_without_changing_reading_version(
    tmp_path, monkeypatch
):
    values = fixture(tmp_path, monkeypatch)
    engine, _client, _paper_id, _parse_id, _session_id = values
    with Session(engine) as db, db.begin():
        project = db.scalar(select(Project))
        source, items = create_import_session_record(
            db,
            project_id=project.id,
            source_kind="pdf",
            selection_id="plan-test",
            source_snapshot=SourceSnapshot(file_name="synthetic.pdf"),
            plan=ImportPlan(overview=True, reading=True, allow_network=True),
        )
        assert source.plan["overview_contract_version"] == MODEL_CARD_CONTRACT_VERSION
        assert source.plan["postprocess_contract_version"] == 4
        assert {item.item_kind for item in items} == {
            "document_parse",
            "paper_overview",
            "paper_reading",
        }
