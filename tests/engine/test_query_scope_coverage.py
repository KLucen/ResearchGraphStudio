"""Explicit multi-paper contexts require real roots from every selected paper."""

import copy

import pytest
import test_knowledge
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, text_hash
from researchgraph.models import AttachmentRevision, Chunk, Paper, now
from researchgraph.query_context import build_context, validate_context
from researchgraph.query_retrieval import retrieve
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_query_answers import OfflineProvider, enqueue, run, view
from test_query_retrieval import request, science_rows

seeded = test_knowledge.seeded


def raw_paper(engine, *, content="Accuracy protocol for a second synthetic experiment."):
    with Session(engine) as session, session.begin():
        session.add(Paper(id="paper2", project_id="project", title="Synthetic2", created_at=now()))
        session.flush()
        session.add(
            AttachmentRevision(
                id="version2",
                paper_id="paper2",
                sha256="d" * 64,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        session.flush()
        session.add(
            Chunk(
                id="paragraph2",
                revision_id="version2",
                page_index=0,
                page_label="1",
                block_index=0,
                text=content,
                bbox=[0.0, 0.0, 100.0, 100.0],
            )
        )


def test_explicit_two_papers_keep_both_actual_roots_even_with_small_limit(seeded):
    _, engine, _ = seeded
    raw_paper(engine)
    with Session(engine) as session, session.begin():
        before = science_rows(session)
        found = retrieve(session, "project", "accuracy", ["paper", "paper2"], limit=2)
        context = build_context(session, request(paper_ids=["paper", "paper2"]), found)
        assert context["status"] == "ready"
        assert context["scope_coverage"] == {
            "requested_paper_ids": ["paper", "paper2"],
            "covered_paper_ids": ["paper", "paper2"],
            "missing_paper_ids": [],
        }
        assert {ref["paper_id"] for ref in context["references"]} == {"paper", "paper2"}
        assert validate_context(session, context, found)["valid"]
        assert science_rows(session) == before


def test_context_rechecks_roots_instead_of_trusting_retrieval_claimed_coverage(seeded):
    _, engine, _ = seeded
    raw_paper(engine)
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "accuracy", ["paper", "paper2"])
        found["hits"] = [hit for hit in found["hits"] if hit["data"]["paper_id"] == "paper"]
        assert found["scope_coverage"]["missing_paper_ids"] == []
        context = build_context(session, request(paper_ids=["paper", "paper2"]), found)
        assert context["status"] == "insufficient"
        assert context["scope_coverage"]["missing_paper_ids"] == ["paper2"]
        assert context["coverage_gaps"]
        assert not any(ref.get("paper_id") == "paper2" for ref in context["references"])


def test_paper_title_matches_do_not_count_as_scientific_coverage(seeded):
    _, engine, _ = seeded
    raw_paper(engine)
    with Session(engine) as session, session.begin():
        found = retrieve(
            session, "project", "Synthetic", ["paper", "paper2"], source_kinds=["paper"]
        )
        assert found["hits"]
        context = build_context(session, request("Synthetic", paper_ids=["paper", "paper2"]), found)
        assert all(ref["type"] == "paper" for ref in context["references"])
        assert context["scope_coverage"]["covered_paper_ids"] == []
        assert context["scope_coverage"]["missing_paper_ids"] == ["paper", "paper2"]
        assert context["status"] == "insufficient" and context["coverage_gaps"]


def test_missing_match_is_not_filled_by_unrelated_source_or_title(seeded):
    _, engine, _ = seeded
    raw_paper(engine, content="Unrelated methods and no matching keywords.")
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "accuracy", ["paper", "paper2"])
        context = build_context(session, request(paper_ids=["paper", "paper2"]), found)
        assert context["status"] == "insufficient"
        assert context["scope_coverage"] == {
            "requested_paper_ids": ["paper", "paper2"],
            "covered_paper_ids": ["paper"],
            "missing_paper_ids": ["paper2"],
        }
        assert {ref["paper_id"] for ref in context["references"]} == {"paper"}


def test_selected_paper_without_pdf_stays_missing_on_context_replay(seeded):
    _, engine, _ = seeded
    with Session(engine) as session, session.begin():
        session.add(Paper(id="paper2", project_id="project", title="No PDF", created_at=now()))
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "accuracy", ["paper", "paper2"])
        context = build_context(session, request(paper_ids=["paper", "paper2"]), found)
        assert context["scope_coverage"]["missing_paper_ids"] == ["paper2"]
        assert context["request"]["paper_ids"] == ["paper", "paper2"]
        assert context["status"] == "insufficient"
        assert validate_context(session, context, found)["status"] == "insufficient"
        forged = copy.deepcopy(found)
        forged["scope_coverage"]["requested_paper_ids"] = ["paper"]
        with pytest.raises(KnowledgeError, match="显式选定"):
            build_context(session, request(paper_ids=["paper", "paper2"]), forged)


@pytest.mark.parametrize("paper_ids", [[], ["paper", "paper2"]])
def test_explicit_version_filter_uses_its_actual_paper_scope_and_replays(seeded, paper_ids):
    _, engine, _ = seeded
    raw_paper(engine)
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "accuracy", paper_ids, version_ids=["version2"])
        context = build_context(
            session,
            request(paper_ids=paper_ids, document_version_ids=["version2"]),
            found,
        )
        assert context["scope_coverage"] == {
            "requested_paper_ids": ["paper2"],
            "covered_paper_ids": ["paper2"],
            "missing_paper_ids": [],
        }
        assert context["request"]["paper_ids"] == ["paper2"]
        assert context["status"] == "ready"
        assert validate_context(session, context, found)["valid"]


def test_wiki_wrapper_coverage_requires_and_expands_its_valid_paper_roots(seeded):
    _, engine, _ = seeded
    raw_paper(engine)
    with Session(engine) as session, session.begin():
        roots = []
        for chunk_id in ["paragraph", "paragraph2"]:
            chunk = session.get(Chunk, chunk_id)
            roots.append(
                {
                    "type": "chunk",
                    "id": chunk_id,
                    "sha256": text_hash(chunk.text),
                    "start": 0,
                    "end": len(chunk.text),
                    "quote": chunk.text,
                }
            )
        KnowledgeStore(session).query().save_document(
            {
                "project_id": "project",
                "kind": "wiki",
                "title": "Synthetic comparison",
                "state": "saved",
                "passages": [
                    {
                        "local_ref": "comparison",
                        "text": "Accuracy comparison with two explicit source roots.",
                        "attribution": "model_synthesis",
                        "dependencies": roots,
                    }
                ],
            },
            "two-paper-wiki-coverage",
        )
        found = retrieve(session, "project", "accuracy", ["paper", "paper2"], source_kinds=["wiki"])
        assert {hit["source_kind"] for hit in found["hits"]} == {"wiki"}
        context = build_context(session, request(paper_ids=["paper", "paper2"]), found)
        assert context["scope_coverage"]["covered_paper_ids"] == ["paper", "paper2"]
        assert context["scope_coverage"]["missing_paper_ids"] == []
        assert {ref["id"] for ref in context["references"] if ref["type"] == "chunk"} == {
            "paragraph",
            "paragraph2",
        }
        assert context["status"] == "ready"


def test_old_retrieval_without_scope_field_keeps_original_manifest_hash(seeded):
    _, engine, _ = seeded
    with Session(engine) as session, session.begin():
        # Freeze the pre-scope protocol, as already persisted by Q01-Q04/real q09.
        found = retrieve(session, "project", "accuracy", ["paper"])
        found.pop("scope_coverage")
        found["ranking_policy"] = "lexical-graph-1"
        context = build_context(session, request(paper_ids=["paper"]), found)
        assert "scope_coverage" not in context
        assert (
            context["input_hash"]
            == "242a5639d69bf99bbd25781dfd8cf1a4a166fe252bdf85ce8695ce062030f3cc"
        )
        old = copy.deepcopy(context)
        assert validate_context(session, context, found)["valid"]
        assert context == old


def test_missing_scope_produces_insufficient_answer_without_dispatch_or_save(seeded):
    from researchgraph.query_models import QueryModelRun

    api, engine, _ = seeded
    raw_paper(engine, content="Unrelated protocols without the requested term.")
    prepared = api.post(
        "/api/v1/projects/project/query/prepare",
        json=request(paper_ids=["paper", "paper2"], purpose="model"),
        headers={"Idempotency-Key": "missing-scope-prepare"},
    )
    assert prepared.status_code == 200, prepared.text
    prepared = prepared.json()
    assert prepared["snapshot"]["context"]["status"] == "insufficient"
    provider = OfflineProvider(engine)
    with Session(engine) as session:
        before = science_rows(session)
    job_id = enqueue(engine, prepared["query_id"])
    run(engine, job_id, provider)
    result = view(engine, prepared["query_id"])
    assert result.status == "insufficient"
    assert result.answer.knowledge_status == "insufficient" and not result.answer.passages
    assert result.request_count == provider.calls == 0
    assert any("未全部" in limitation for limitation in result.answer.limitations)
    with Session(engine) as session, session.begin():
        assert session.scalar(select(func.count()).select_from(QueryModelRun)) == 0
        assert science_rows(session) == before
        with pytest.raises(KnowledgeError, match="来源完整"):
            KnowledgeStore(session).save_query(
                {
                    "source_query_id": prepared["query_id"],
                    "answer_version_id": result.answer.answer_version_id,
                    "selected_passage_refs": ["A00001"],
                    "expected_input_hash": prepared["input_hash"],
                },
                "missing-scope-cannot-save",
                project_id="project",
            )


def test_scope_coverage_cannot_claim_different_selected_papers(seeded):
    _, engine, _ = seeded
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "accuracy", ["paper"])
        found["scope_coverage"]["requested_paper_ids"] = ["foreign"]
        with pytest.raises(KnowledgeError, match="显式选定"):
            build_context(session, request(paper_ids=["paper"]), found)
