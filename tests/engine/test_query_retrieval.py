"""Q02/Q04 deterministic retrieval on synthetic data; zero provider calls."""

import pytest
import test_knowledge
from pydantic import ValidationError
from researchgraph.knowledge_models import AuthorizedRoot, EvidenceSpan, KnowledgeNode, NoteSnapshot
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, text_hash
from researchgraph.models import AttachmentRevision, Chunk, Project, now
from researchgraph.query_context import build_context, validate_context
from researchgraph.query_contracts import QueryRequest
from researchgraph.query_models import QueryPassage
from researchgraph.query_retrieval import rebuild_index, retrieve
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_query_graph import production, second_paper

seeded = test_knowledge.seeded


def request(question="accuracy", **changes):
    return QueryRequest(project_id="project", question=question, **changes).model_dump()


def document(engine, text_value="Saved accuracy explanation", *, personal=False, state="saved"):
    with Session(engine) as session, session.begin():
        dep = {
            "type": "chunk",
            "id": "paragraph",
            "sha256": text_hash(session.get(Chunk, "paragraph").text),
            "start": 0,
            "end": len(session.get(Chunk, "paragraph").text),
            "quote": session.get(Chunk, "paragraph").text,
        }
        if personal:
            note = session.get(NoteSnapshot, "note")
            dep = {"type": "note", "id": "note", "sha256": note.sha256}
        return (
            KnowledgeStore(session)
            .query()
            .save_document(
                {
                    "project_id": "project",
                    "kind": "wiki",
                    "title": "Synthetic Wiki",
                    "state": state,
                    "passages": [
                        {
                            "local_ref": "p",
                            "text": text_value,
                            "attribution": "user_view" if personal else "model_synthesis",
                            "dependencies": [dep],
                        }
                    ],
                },
                "doc:" + text_value,
            )
        )


def notes(engine, tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    content = "Private synthetic note about accuracy"
    (root / "reading.md").write_text(content, encoding="utf-8")
    with Session(engine) as session, session.begin():
        session.add(
            AuthorizedRoot(
                id="root", project_id="project", path=str(root), active=True, created_at=now()
            )
        )
        session.flush()
        session.add(
            NoteSnapshot(
                id="note",
                root_id="root",
                relative_path="reading.md",
                sha256=text_hash(content),
                text=content,
                created_at=now(),
            )
        )
    return root


def science_rows(session):
    tables = [
        "knowledge_nodes",
        "node_evidence_links",
        "reading_selections",
        "reading_heads",
        "graph_revisions",
        "graph_layouts",
        "model_runs",
        "chunks",
        "evidence_spans",
    ]
    return {t: list(session.execute(text(f'SELECT * FROM "{t}"'))) for t in tables}


@pytest.mark.parametrize(
    "question",
    ["accuracy", "81%", "3 agents", "合成", "shared memory", "Smith", '" OR *', "", "   "],
)
def test_lexical_chinese_numeric_and_special_queries(seeded, question):
    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session, session.begin():
        before = science_rows(session)
        result = retrieve(session, "project", question, [])
        assert science_rows(session) == before
        if question.strip() and question not in {"shared memory", '" OR *'}:
            assert result["hits"]
        if not question.strip():
            assert result["status"] == "empty" and result["hits"] == []
        assert all(h["data"].get("paper_id", "paper") == "paper" for h in result["hits"])


def test_index_rebuild_is_derived_stable_and_recovers_removed_fts(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session, session.begin():
        before = science_rows(session)
        first = rebuild_index(session, "project")
        second = rebuild_index(session, "project")
        assert second["updated"] == 0 and first["fingerprint"] == second["fingerprint"]
        hits = retrieve(session, "project", "accuracy", [])["hits"]
        session.execute(text("DELETE FROM query_index_entries"))
        session.execute(text("DELETE FROM query_fts"))
        assert retrieve(session, "project", "accuracy", [])["hits"] == hits
        assert before == science_rows(session)


def test_raw_only_unextracted_is_searchable_and_reference_excluded(seeded):
    _, engine, _ = seeded
    with Session(engine) as session, session.begin():
        session.add(
            Chunk(
                id="raw-only",
                revision_id="version",
                page_index=0,
                page_label="1",
                block_index=4,
                text="Unextracted novelpressure 7 kPa",
                bbox=[0, 0, 10, 10],
            )
        )
        assert (
            retrieve(session, "project", "novelpressure", [])["hits"][0]["object_id"] == "raw-only"
        )
        section = session.get(EvidenceSpan, session.scalar(select(EvidenceSpan.id))).section_id
        from researchgraph.knowledge_models import Section

        session.get(Section, section).role = "references"
        result = retrieve(session, "project", "accuracy", [])
        assert not any(h["source_kind"] == "chunk" for h in result["hits"])


def test_scope_and_old_version_rejected(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    second_paper(engine)
    with Session(engine) as session, session.begin():
        result = retrieve(session, "project", "accuracy", ["paper2"])
        assert all(h["data"]["paper_id"] == "paper2" for h in result["hits"])
        with pytest.raises(KnowledgeError):
            retrieve(session, "project", "accuracy", ["not-in-project"])
        with pytest.raises(KnowledgeError):
            retrieve(session, "project", "accuracy", [], version_ids=["forged"])
        session.add(Project(id="another", name="Other", description="", created_at=now()))
        assert retrieve(session, "another", "accuracy", [])["hits"] == []


def test_wiki_duplicate_root_count_draft_and_stale_passage(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    saved = document(engine)
    document(engine, "Draft accuracy explanation", state="draft")
    with Session(engine) as session, session.begin():
        result = retrieve(session, "project", "accuracy", [])
        assert any(h["source_kind"] == "wiki" for h in result["hits"])
        assert result["independent_sources"] == ["paper:version"]
        assert not any("Draft" in h["text"] for h in result["hits"])
        session.get(Chunk, "paragraph").text += " updated"
        assert not any(
            h["source_kind"] == "wiki" for h in retrieve(session, "project", "accuracy", [])["hits"]
        )
        assert (
            session.get(QueryPassage, saved["passage_ids"][0]).text == "Saved accuracy explanation"
        )


def test_notes_and_transitive_wiki_never_bypass_purpose_or_revocation(seeded, tmp_path):
    _, engine, _ = seeded
    notes(engine, tmp_path)
    document(engine, "Private wiki accuracy", personal=True)
    with Session(engine) as session, session.begin():
        assert retrieve(session, "project", "Private", [])["hits"] == []
        assert {
            h["source_kind"]
            for h in retrieve(session, "project", "Private", [], include_personal=True)["hits"]
        } == {"note", "wiki"}
        assert (
            retrieve(session, "project", "Private", [], include_personal=True, purpose="model")[
                "hits"
            ]
            == []
        )
        KnowledgeStore(session).query().set_note_grant("project", "root", True, True)
        assert retrieve(session, "project", "Private", [], include_personal=True, purpose="model")[
            "hits"
        ]
        session.get(AuthorizedRoot, "root").active = False
        assert (
            retrieve(session, "project", "Private", [], include_personal=True, purpose="model")[
                "hits"
            ]
            == []
        )


def test_context_keeps_original_and_graph_support_replays_without_writes(seeded):
    _, engine, eid = seeded
    ids = production(engine, eid)
    second_paper(engine)
    with Session(engine) as session, session.begin():
        before = science_rows(session)
        found = retrieve(session, "project", "accuracy", [])
        context = build_context(session, request(), found)
        assert context["status"] == "ready"
        assert {
            r["document_version_id"] for r in context["references"] if r.get("document_version_id")
        } == {"version", "version2"}
        assert any(r["id"] == ids["d"] for r in context["references"])
        assert len({r["ref"] for r in context["references"]}) == len(context["references"])
        assert all(
            r["current_file_status"] == "not_checked"
            for r in context["references"]
            if r["type"] in {"chunk", "evidence"}
        )
        assert validate_context(session, context, found)["valid"]
        assert science_rows(session) == before


@pytest.mark.parametrize(
    "fault", ["raw", "quote", "offset", "version", "node", "payload", "relation", "hash"]
)
def test_replay_rejects_forgery_and_mutation(seeded, fault):
    _, engine, eid = seeded
    ids = production(engine, eid)
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "accuracy", [])
        context = build_context(session, request(), found)
        if fault == "raw":
            session.get(Chunk, "paragraph").text += "changed"
        elif fault == "quote":
            session.get(EvidenceSpan, eid).quote = "forged"
        elif fault == "offset":
            session.get(EvidenceSpan, eid).end_offset -= 1
        elif fault == "version":
            session.get(AttachmentRevision, "version").sha256 = "f" * 64
        elif fault == "node":
            session.get(KnowledgeNode, ids["c"]).revision += 1
        elif fault == "payload":
            n = session.get(KnowledgeNode, ids["c"])
            n.payload = {**n.payload, "statement": {"original": "changed", "language": "en"}}
        elif fault == "relation":
            from researchgraph.graph_models import SourceAssertion

            edge = session.scalar(select(SourceAssertion))
            edge.evidence_ids = []
        else:
            context["references"][0]["id"] = "forged"
        session.flush()
        with pytest.raises(KnowledgeError):
            validate_context(session, context, found)


def test_capacity_stop_keeps_all_support_and_no_fixed_48k_limit(seeded):
    _, engine, eid = seeded
    with Session(engine) as session, session.begin():
        content = "Accuracy protocol " * 5000
        span = session.get(EvidenceSpan, eid)
        session.get(Chunk, "paragraph").text = content
        span.quote, span.end_offset, span.text_sha256 = content, len(content), text_hash(content)
    production(engine, eid)
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "accuracy", [])
        full = build_context(session, request(), found)
        assert full["status"] == "ready"
        assert max(len(r.get("quote", "")) for r in full["references"]) > 48000
        limited = build_context(
            session,
            request(),
            found,
            model_snapshot={
                "parameters": {"capabilities": {"context_window": 1024, "max_output_tokens": 512}}
            },
        )
        assert limited["status"] == "insufficient"
        assert limited["references"] == full["references"]


@pytest.mark.parametrize(
    "body",
    [dict(question=" "), dict(question="x", paper_ids=["p", "p"]), dict(question="x", extra="no")],
)
def test_query_contract_rejects_invalid_request(body):
    with pytest.raises(ValidationError):
        QueryRequest(project_id="project", **body)


def test_api_prepare_idempotent_read_restart_and_crossproject(seeded):
    api, engine, eid = seeded
    production(engine, eid)
    response = api.post(
        "/api/v1/projects/project/query/prepare",
        json=request(),
        headers={"Idempotency-Key": "query-prepare-1"},
    )
    assert response.status_code == 200, response.text
    first = response.json()
    again = api.post(
        "/api/v1/projects/project/query/prepare",
        json=request(),
        headers={"Idempotency-Key": "query-prepare-1"},
    )
    assert again.json() == first
    assert first["snapshot"]["model"] is None
    assert first["snapshot"]["prompt"]["generation_enabled"] is False
    assert api.get(f"/api/v1/projects/project/query/runs/{first['query_id']}").json() == first
    wrong = api.get(f"/api/v1/projects/other/query/runs/{first['query_id']}")
    assert wrong.status_code == 404
    conflict = api.post(
        "/api/v1/projects/project/query/prepare",
        json=request("changed"),
        headers={"Idempotency-Key": "query-prepare-1"},
    )
    assert conflict.status_code == 409
    with Session(engine) as session:
        from researchgraph.query_models import QueryRun

        assert session.get(QueryRun, first["query_id"]).input_hash == first["input_hash"]


def test_api_cached_personal_context_does_not_escape_revocation(seeded, tmp_path):
    api, engine, _ = seeded
    notes(engine, tmp_path)
    response = api.post(
        "/api/v1/projects/project/query/prepare",
        json=request("Private", include_personal=True),
        headers={"Idempotency-Key": "private-query-1"},
    )
    assert response.status_code == 200, response.text
    qid = response.json()["query_id"]
    with Session(engine) as session, session.begin():
        session.get(AuthorizedRoot, "root").active = False
    assert api.get(f"/api/v1/projects/project/query/runs/{qid}").status_code == 422
    repeat = api.post(
        "/api/v1/projects/project/query/prepare",
        json=request("Private", include_personal=True),
        headers={"Idempotency-Key": "private-query-1"},
    )
    assert repeat.status_code == 422 and "Private synthetic" not in repeat.text


@pytest.mark.parametrize(
    "base_url,model_id,profile_capabilities,expected",
    [
        (
            "https://tokenhub.tencentmaas.com/plan/v3",
            "deepseek-v4.1-flash",
            {},
            (1_000_000, 393216),
        ),
        (
            "https://compatible.example/v1",
            "deepseek-v4.1-flash",
            {},
            (None, None),
        ),
        (
            "https://tokenhub.tencentmaas.com/plan/v3",
            "unregistered-model",
            {},
            (None, None),
        ),
        (
            "https://tokenhub.tencentmaas.com/plan/v3",
            "deepseek-v4.1-flash",
            {
                "context_window": 64000,
                "max_output_tokens": 8192,
                "source": "endpoint_metadata",
            },
            (64000, 8192),
        ),
    ],
)
def test_prepare_freezes_effective_model_capabilities_without_provider_calls(
    seeded, base_url, model_id, profile_capabilities, expected
):
    from researchgraph.model_settings import GlobalModelRole, ModelParameters, ModelProfile

    api, engine, eid = seeded
    production(engine, eid)
    parameters = ModelParameters(capabilities=profile_capabilities).model_dump()
    with Session(engine) as session, session.begin():
        session.add(
            ModelProfile(
                id="query-model",
                project_id=None,
                name="Synthetic model with no network",
                provider="compatible",
                base_url=base_url,
                model=model_id,
                parameters=parameters,
                credential_ref=None,
                secret_refs=[],
                active=True,
                updated_at=now(),
            )
        )
        session.flush()
        session.add(GlobalModelRole(role="reasoning", profile_id="query-model"))
    with Session(engine) as session:
        before = science_rows(session)
    response = api.post(
        "/api/v1/projects/project/query/prepare",
        json=request(),
        headers={"Idempotency-Key": "query-model-capabilities"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    frozen = result["snapshot"]["model"]["parameters"]["capabilities"]
    capacity = result["snapshot"]["context"]["capacity"]
    assert (frozen["context_window"], frozen["max_output_tokens"]) == expected
    assert (capacity["context_window"], capacity["reserved_output_tokens"]) == expected
    assert frozen["source"] == (
        "endpoint_metadata"
        if profile_capabilities
        else "tencent_documentation_2026-11-02"
        if expected[0]
        else "provider_default"
    )
    with Session(engine) as session, session.begin():
        assert science_rows(session) == before
        profile = session.get(ModelProfile, "query-model")
        assert profile.parameters == parameters
        # Existing preparations replay the frozen model, not today's settings.
        profile.model = "changed-model"
        profile.parameters = ModelParameters().model_dump()
    replay = api.get(f"/api/v1/projects/project/query/runs/{result['query_id']}")
    assert replay.status_code == 200 and replay.json() == result


def test_source_type_filters_precede_ranking_and_chinese_question_recall(seeded):
    _, engine, eid = seeded
    ids = production(engine, eid)
    with Session(engine) as session, session.begin():
        node = session.get(KnowledgeNode, ids["c"])
        payload = dict(node.payload)
        payload["label"] = {**payload["label"], "zh": "准确率提高"}
        node.payload = payload
        result = retrieve(
            session,
            "project",
            "这篇论文的准确率是多少",
            [],
            source_kinds=["knowledge"],
            knowledge_kinds=["claim"],
        )
        assert [h["object_id"] for h in result["hits"]] == [ids["c"]]
        assert "准确" in result["terms"]
        assert all(
            h["source_kind"] == "knowledge" and h["data"]["kind"] == "claim" for h in result["hits"]
        )


def test_rebuild_recovers_fts_only_corruption(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session, session.begin():
        first = retrieve(session, "project", "accuracy", [])
        session.execute(text("DELETE FROM query_fts"))
        assert retrieve(session, "project", "accuracy", []) == first


def test_query_api_runs_and_context_survive_real_engine_restart(tmp_path):
    from test_document_structure import synthetic
    from test_engine import client, post
    from test_ingest import queue, wait_job

    source = tmp_path / "query-source.pdf"
    synthetic(source)
    data = tmp_path / "data"
    with client(data, worker=True) as api:
        project = post(api, "/projects", {"name": "Synthetic query restart"}).json()["id"]
        assert wait_job(api, queue(api, project, source, "query-source"))["status"] == "succeeded"
        result = post(
            api,
            f"/projects/{project}/query/prepare",
            {"project_id": project, "question": "method"},
            key="query-restart",
        ).json()
        assert result["status"] == "prepared"
        runs = f"/api/v1/projects/{project}/query/runs/{result['query_id']}"
    with client(data) as api:
        assert api.get(runs).json() == result
        assert api.post(runs + "/validate").json()["valid"]
