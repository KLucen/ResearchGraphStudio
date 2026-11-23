import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph import storage
from researchgraph.close_reading_models import SectionCloseReadingResult, UnderstandingCheckResult
from researchgraph.core import KnowledgeError, text_hash
from researchgraph.lite_models import LiteTokenUsage
from researchgraph.models import (
    AttachmentRevision,
    Chunk,
    EvidenceSpan,
    Paper,
    Project,
    Section,
    now,
)
from researchgraph.paper_card_set_contracts import validate_paper_card_set
from researchgraph.paper_card_set_service import build_card_manifest
from researchgraph.paper_overview_models import PaperOverviewResult
from researchgraph.reading_state_api import (
    apply_check_result,
    build_reader_context,
    get_state_snapshot,
    list_concept_understanding,
    register_reading_state_api,
)
from researchgraph.reading_state_models import ConceptUnderstanding, ReadingState
from researchgraph.section_guide_api import execute_section_guide, register_section_guide_api
from researchgraph.section_guide_models import SectionGuideResult
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session


def _overview(
    session,
    paper_id,
    project_id,
    revision_id,
    *,
    node_id="c1",
    label="共享记忆",
    label_en="shared memory",
    updated="2026-11-14T00:00:00Z",
    cards=None,
):
    manifest = build_card_manifest(session, paper_id, "local_revision", revision_id)
    source = manifest["sources"][0]
    concept = {
        "id": node_id,
        "kind": "key_concept",
        "attribution": "AUTHOR",
        "title_zh": label,
        "title_en": label_en,
        "body_zh": "本节方法使用的共享记忆。",
        "reading_guide_zh": "核对共享记忆的定义与适用条件。",
        "evidence": [
            {
                "source_id": source["ref"],
                "quote_en": source["text"],
                "occurrence_index": 0,
                "translation_zh": None,
            }
        ],
    }
    selected = cards or [concept]
    content = validate_paper_card_set(
        {
            "schema_version": "paper-card-set-2",
            "article_overview_zh": "本文介绍合成测试中的共享记忆。",
            "overview_card_ids": [selected[0]["id"]],
            "card_set_intro_zh": "合成概念卡可定位原文。",
            "coverage_notes": ["软件回归材料。"],
            "cards": selected,
        },
        manifest,
    )
    return PaperOverviewResult(
        id=str(uuid4()),
        project_id=project_id,
        paper_id=paper_id,
        document_version_id=revision_id,
        pdf_hash="a" * 64,
        input_hash="b" * 64,
        cache_key="c" * 64,
        schema_version="paper-card-set-2",
        prompt_version="paper-card-set-extract-1",
        provider_id="test",
        model_id="test",
        status="COMPLETED",
        created_at=updated,
        updated_at=updated,
        paper_card_json=content,
        graph_json=None,
    )


@pytest.fixture
def fixture(tmp_path):
    engine = storage.make_engine(tmp_path)
    storage.migrate(engine, tmp_path)
    project_id, paper_id, revision_id, section_id, chunk_id, span_id = (
        str(uuid4()) for _ in range(6)
    )
    with Session(engine) as session, session.begin():
        session.add(
            Project(id=project_id, name="Synthetic reading state", description="", created_at=now())
        )
        session.flush()
        session.add(
            Paper(id=paper_id, project_id=project_id, title="Synthetic paper", created_at=now())
        )
        session.flush()
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="a" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        session.flush()
        session.add(
            Section(
                id=section_id,
                document_version_id=revision_id,
                title="Methods",
                ordinal=0,
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
                text="The method uses shared memory to coordinate decisions.",
                bbox=[0, 0, 1, 1],
            )
        )
        session.flush()
        session.add(
            EvidenceSpan(
                id=span_id,
                document_version_id=revision_id,
                section_id=section_id,
                paragraph_id=chunk_id,
                page_index=0,
                start_offset=0,
                end_offset=54,
                quote="The method uses shared memory to coordinate decisions.",
                text_sha256=text_hash("The method uses shared memory to coordinate decisions."),
                normalization="identity-v1",
                bbox_list=[[0, 0, 1, 1]],
            )
        )
        session.flush()
        overview = _overview(session, paper_id, project_id, revision_id)
        session.add(overview)
        overview_id = overview.id
        node_id = overview.paper_card_json["cards"][0]["id"]
    app = FastAPI()
    register_reading_state_api(app, lambda: engine)
    register_section_guide_api(app, lambda: engine, tmp_path)
    with TestClient(app) as client:
        yield SimpleNamespace(
            engine=engine,
            client=client,
            project_id=project_id,
            paper_id=paper_id,
            revision_id=revision_id,
            section_id=section_id,
            chunk_id=chunk_id,
            span_id=span_id,
            overview_id=overview_id,
            node_id=node_id,
            path=tmp_path,
        )
    engine.dispose()


def _state_url(f):
    return f"/api/v1/papers/{f.paper_id}/sections/{f.section_id}/reading-state"


def _concept_url(f, node_id=None):
    node_id = node_id or f.node_id
    return f"/api/v1/papers/{f.paper_id}/concept-understanding/{node_id}"


def _put_concept(f, level="UNSURE", note="我需要回看定义。"):
    response = f.client.put(
        _concept_url(f),
        json={
            "document_version_id": f.revision_id,
            "overview_result_id": f.overview_id,
            "self_level": level,
            "note_zh": note,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_progress_patch_preserves_subjective_fields_unlinked_ids_and_source_baseline(fixture):
    f = fixture
    with Session(f.engine) as session, session.begin():
        row = ReadingState(
            id=str(uuid4()),
            paper_id=f.paper_id,
            document_version_id=f.revision_id,
            section_id=f.section_id,
            source_hash="old-source-baseline",
            progress="READING",
            self_assessment="PARTIAL",
            unresolved_concept_ids=["old-unlinked-concept"],
            graph_reference_json={"old-unlinked-concept": {"fingerprint": "old"}},
            questions=[{"paragraph_id": f.chunk_id, "text": "Keep my question", "resolved": False}],
            updated_at=now(),
        )
        session.add(row)
    response = f.client.patch(
        _state_url(f),
        json={"document_version_id": f.revision_id, "progress": "COMPLETED"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["progress"] == "COMPLETED"
    assert response.json()["source_changed"] is True
    assert response.json()["unresolved_unlinked_ids"] == ["old-unlinked-concept"]
    with Session(f.engine) as session:
        row = session.scalar(select(ReadingState))
        assert row.source_hash == "old-source-baseline"
        assert row.self_assessment == "PARTIAL"
        assert row.questions[0]["text"] == "Keep my question"
        assert row.unresolved_concept_ids == ["old-unlinked-concept"]
        assert row.graph_reference_json == {"old-unlinked-concept": {"fingerprint": "old"}}
        assert session.scalar(select(LiteTokenUsage)) is None
    assert (
        f.client.patch(
            _state_url(f), json={"document_version_id": "foreign", "progress": "READING"}
        ).status_code
        == 409
    )
    assert (
        f.client.patch(
            _state_url(f), json={"document_version_id": f.revision_id, "progress": "INVENTED"}
        ).status_code
        == 422
    )


def test_progress_patch_creates_missing_state_without_model_use(fixture):
    f = fixture
    response = f.client.patch(
        _state_url(f),
        json={"document_version_id": f.revision_id, "progress": "READING"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["self_assessment"] == "UNSET"
    assert response.json()["questions"] == []
    with Session(f.engine) as session:
        assert session.scalar(select(LiteTokenUsage)) is None


def test_empty_get_and_state_save_are_local_and_persist(fixture):
    f = fixture
    empty = f.client.get(_state_url(f)).json()
    assert empty["progress"] == "NOT_STARTED" and empty["updated_at"] is None
    with Session(f.engine) as session:
        assert session.scalar(select(ReadingState)) is None
        before = session.get(PaperOverviewResult, f.overview_id).paper_card_json
    response = f.client.put(
        _state_url(f),
        json={
            "document_version_id": f.revision_id,
            "overview_result_id": f.overview_id,
            "progress": "READING",
            "self_assessment": "PARTIAL",
            "unresolved_concept_ids": [f.node_id],
            "questions": [
                {"paragraph_id": f.chunk_id, "text": "如何更新共享记忆？", "resolved": False}
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["unresolved_concept_ids"] == [f.node_id]
    fresh_engine = storage.make_engine(f.path)
    with Session(fresh_engine) as session:
        snapshot = get_state_snapshot(session, f.paper_id, f.revision_id, f.section_id)
        assert snapshot["self_assessment"] == "PARTIAL"
        assert snapshot["questions"][0]["text"] == "如何更新共享记忆？"
        assert session.scalar(select(LiteTokenUsage)) is None
        assert session.get(PaperOverviewResult, f.overview_id).paper_card_json == before
        concept = list_concept_understanding(session, f.paper_id, f.revision_id)[0]
        assert concept.has_unresolved_question is True
        assert concept.related_sections[0].section_id == f.section_id
        assert concept.self_level == "UNSET"
    fresh_engine.dispose()


@pytest.mark.parametrize(
    "field,value",
    [
        ("questions", [{"paragraph_id": "foreign", "text": "what?", "resolved": False}]),
        ("unresolved_concept_ids", ["foreign"]),
    ],
)
def test_state_rejects_foreign_paragraph_and_graph_ids(fixture, field, value):
    f = fixture
    response = f.client.put(_state_url(f), json={"overview_result_id": f.overview_id, field: value})
    assert response.status_code == 409
    with Session(f.engine) as session:
        assert session.scalar(select(ReadingState)) is None


def test_concept_check_never_overwrites_user_assessment_or_note(fixture):
    f = fixture
    saved = _put_concept(f, "CONFIDENT", "这是我的主观记录。")
    with Session(f.engine) as session, session.begin():
        apply_check_result(
            session,
            f.paper_id,
            f.revision_id,
            [f.node_id],
            "MISCONCEPTION",
            "请核对信息与决策的区别。",
            overview_result_id=f.overview_id,
        )
    current = f.client.get(f"/api/v1/papers/{f.paper_id}/concept-understanding").json()[0]
    assert current["id"] == saved["id"]
    assert current["self_level"] == "CONFIDENT" and current["note_zh"] == "这是我的主观记录。"
    assert current["last_check_result"] == "MISCONCEPTION"
    assert current["last_check_note_zh"] == "请核对信息与决策的区别。"
    assert current["association_status"] == "CURRENT"


@pytest.mark.parametrize(
    "node_id,label,expected",
    [
        ("c1", "共享记忆", "CURRENT"),
        ("c2", "共享记忆", "NEEDS_RELINK"),
        ("c1", "不同概念", "NEEDS_RELINK"),
    ],
)
def test_graph_refresh_requires_same_stable_id_and_same_semantics(
    fixture, node_id, label, expected
):
    f = fixture
    saved = _put_concept(f)
    with Session(f.engine) as session, session.begin():
        session.add(
            _overview(
                session,
                f.paper_id,
                f.project_id,
                f.revision_id,
                node_id=node_id,
                label=label,
                updated="2026-11-14T01:00:00Z",
            )
        )
    views = f.client.get(f"/api/v1/papers/{f.paper_id}/concept-understanding").json()
    old = next(view for view in views if view["id"] == saved["id"])
    assert old["association_status"] == expected
    if expected == "NEEDS_RELINK":
        current = next(view for view in views if view["association_status"] == "CURRENT")
        assert current["self_level"] == "UNSET"
    stale_write = f.client.put(
        _concept_url(f), json={"overview_result_id": f.overview_id, "self_level": "CONFIDENT"}
    )
    assert stale_write.status_code == 409
    with Session(f.engine) as session:
        assert session.get(ConceptUnderstanding, saved["id"]).self_level == "UNSURE"


def test_missing_or_pending_graph_keeps_old_state_for_relink(fixture):
    f = fixture
    saved = _put_concept(f)
    with Session(f.engine) as session, session.begin():
        session.get(PaperOverviewResult, f.overview_id).status = "FAILED"
    result = f.client.get(f"/api/v1/papers/{f.paper_id}/concept-understanding").json()
    assert len(result) == 1 and result[0]["id"] == saved["id"]
    assert result[0]["association_status"] == "NEEDS_RELINK"
    with Session(f.engine) as session, session.begin():
        with pytest.raises(KnowledgeError, match="图谱已变化"):
            apply_check_result(
                session,
                f.paper_id,
                f.revision_id,
                [f.node_id],
                "ADEQUATE",
                "feedback",
                overview_result_id=f.overview_id,
            )


def test_source_change_flags_subjective_state_without_deleting_it(fixture):
    f = fixture
    f.client.put(_state_url(f), json={"progress": "COMPLETED", "self_assessment": "CONFIDENT"})
    with Session(f.engine) as session, session.begin():
        session.get(Chunk, f.chunk_id).text += " Updated source."
    view = f.client.get(_state_url(f)).json()
    assert view["source_changed"] is True
    assert view["progress"] == "COMPLETED" and view["self_assessment"] == "CONFIDENT"


def test_adaptive_context_requires_local_related_term_and_is_bounded(fixture):
    f = fixture
    _put_concept(f)
    with Session(f.engine) as session:
        assert (
            build_reader_context(
                session, f.paper_id, f.revision_id, f.section_id, "Unrelated discussion."
            )
            is None
        )
        context = build_reader_context(
            session, f.paper_id, f.revision_id, f.section_id, "We use shared memory."
        )
        assert context["strategy"] == "BRIDGE_GAPS"
        assert context["unresolved_concepts"] == ["共享记忆"]
        assert "我需要回看定义" not in json.dumps(context, ensure_ascii=False)
    # Unresolved concept selection also informs A01 without changing self_level.
    _put_concept(f, "UNSET")
    f.client.put(
        _state_url(f),
        json={"overview_result_id": f.overview_id, "unresolved_concept_ids": [f.node_id]},
    )
    with Session(f.engine) as session:
        assert (
            build_reader_context(
                session, f.paper_id, f.revision_id, f.section_id, "We use shared memory."
            )["strategy"]
            == "BRIDGE_GAPS"
        )


def test_a01_freezes_reader_context_and_state_changes_do_not_invalidate_cache(fixture, monkeypatch):
    f = fixture
    _put_concept(f)
    monkeypatch.setattr(
        "researchgraph.model_settings.snapshot_for",
        lambda *_args: {
            "provider": "test",
            "model": "reading-test",
            "base_url": "",
            "parameters": {},
        },
    )
    url = f"/api/v1/papers/{f.paper_id}/sections/{f.section_id}/guide"
    response = f.client.post(
        url + "/generate",
        json={"section_id": f.section_id, "allow_network": True, "adaptive": True},
    )
    assert response.status_code == 200
    view = response.json()
    assert view["reader_context"]["strategy"] == "BRIDGE_GAPS"

    class Provider:
        name = "test"
        model = "reading-test"
        calls = 0
        usage = {"input_tokens": 60, "output_tokens": 30, "total_tokens": 90}

        async def complete(self, prompt, data, schema):
            self.calls += 1
            assert data["reader_context"]["unresolved_concepts"] == ["共享记忆"]
            _put_concept(f, "CONFIDENT")
            return json.dumps(
                {
                    "section_id": f.section_id,
                    "overview_zh": "当前小节方法。",
                    "key_points": ["方法使用共享记忆。"],
                    "reading_questions": ["如何更新？", "假设是什么？"],
                    "evidence_span_ids": [f.span_id],
                },
                ensure_ascii=False,
            )

    provider = Provider()
    asyncio.run(execute_section_guide(f.engine, view["job_id"], f.path, provider=provider))
    completed = f.client.get(url, params={"adaptive": True}).json()
    assert completed["status"] == "COMPLETED"
    assert completed["reader_context"]["strategy"] == "BRIDGE_GAPS"
    assert provider.calls == 1
    with Session(f.engine) as session:
        assert session.get(SectionGuideResult, view["id"]).status == "COMPLETED"
    assert f.client.get(url, params={"adaptive": False}).json() is None


def test_lite0008_additive_upgrade_creates_four_tables_and_backup(tmp_path):
    engine = storage.make_engine(tmp_path)
    config = Config()
    config.set_main_option("script_location", str(Path(storage.__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "lite0008")
        # Shared Base imports future tables into 0001. Remove only empty new
        # tables so this is a real deployed 0008 schema, not a stamp-only test.
        for model in (
            SectionCloseReadingResult,
            UnderstandingCheckResult,
            ReadingState,
            ConceptUnderstanding,
        ):
            model.__table__.drop(connection, checkfirst=True)
        connection.execute(
            text(
                "INSERT INTO projects(id,name,description,created_at,experience_mode) "
                "VALUES('keep','keep source','',:created,'lite')"
            ),
            {"created": now()},
        )
    storage.migrate(engine, tmp_path)
    assert {
        "lite_section_close_readings",
        "lite_understanding_checks",
        "lite_reading_states",
        "lite_concept_understanding",
    } <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == storage.SCHEMA_HEAD
        )
        assert connection.scalar(text("SELECT name FROM projects WHERE id='keep'")) == "keep source"
    backups = list((tmp_path / "backups").glob("before-migration-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "lite0008"
        assert (
            backup.execute("SELECT name FROM projects WHERE id='keep'").fetchone()[0]
            == "keep source"
        )
        assert (
            backup.execute(
                "SELECT count(*) FROM sqlite_master WHERE name='lite_reading_states'"
            ).fetchone()[0]
            == 0
        )
    assert storage.diagnostics(engine)["integrity"] == "ok"
    engine.dispose()


def test_adaptive_context_never_sends_more_than_three_states(fixture):
    f = fixture
    with Session(f.engine) as session, session.begin():
        overview = session.get(PaperOverviewResult, f.overview_id)
        base_card = overview.paper_card_json["wire_draft"]["cards"][0]
        cards = [dict(base_card, id=f"c{index}", title_zh=f"概念{index}") for index in range(1, 5)]
        replacement = _overview(session, f.paper_id, f.project_id, f.revision_id, cards=cards)
        overview.paper_card_json = replacement.paper_card_json
        node_ids = [card["id"] for card in overview.paper_card_json["cards"]]
        expected_labels = [
            card["title_zh"]
            for card in sorted(overview.paper_card_json["cards"], key=lambda card: card["id"])[:3]
        ]
    for node_id in node_ids:
        response = f.client.put(
            _concept_url(f, node_id),
            json={"overview_result_id": f.overview_id, "self_level": "UNSURE"},
        )
        assert response.status_code == 200
    with Session(f.engine) as session:
        context = build_reader_context(
            session, f.paper_id, f.revision_id, f.section_id, "shared memory"
        )
        assert context["unresolved_concepts"] == expected_labels


def test_related_sections_use_current_a02_links_and_drop_stale_source_links(fixture):
    from researchgraph.close_reading_api import _hash, _pending_result, build_reading_input
    from researchgraph.models import Job

    f = fixture
    with Session(f.engine) as session, session.begin():
        overview = session.get(PaperOverviewResult, f.overview_id)
        replacement = _overview(
            session, f.paper_id, f.project_id, f.revision_id, label_en="a different indexed concept"
        )
        overview.paper_card_json = replacement.paper_card_json
        node_id = overview.paper_card_json["cards"][0]["id"]
        paper, revision, context = build_reading_input(
            session, f.paper_id, f.revision_id, f.section_id, [f.chunk_id]
        )
        row = _pending_result(
            session,
            Job(id=str(uuid4()), payload={}),
            paper,
            revision,
            context,
            "c" * 64,
            "test",
            "test",
            is_check=False,
        )
        row.status = "COMPLETED"
        row.input_hash = _hash(context)
        row.analysis_json = {
            "paragraphs": [{"paragraph_id": f.chunk_id, "related_graph_node_ids": [node_id]}]
        }
    views = f.client.get(f"/api/v1/papers/{f.paper_id}/concept-understanding").json()
    assert views[0]["related_sections"] == [{"section_id": f.section_id, "title": "Methods"}]
    f.node_id = node_id
    _put_concept(f)
    with Session(f.engine) as session, session.begin():
        session.get(Chunk, f.chunk_id).text = "The source has changed."
    changed = f.client.get(f"/api/v1/papers/{f.paper_id}/concept-understanding").json()
    assert changed[0]["related_sections"] == []
    assert changed[0]["association_status"] == "NEEDS_RELINK"
