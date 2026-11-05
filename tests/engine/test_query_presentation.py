"""Readable local source views do not rewrite snapshots or dispatch a provider."""

import copy

import test_knowledge
from researchgraph.graph_models import KnowledgeDisplay
from researchgraph.knowledge_models import EvidenceSpan, NodeEvidence
from researchgraph.knowledge_store import digest, text_hash
from researchgraph.models import AttachmentRevision, Chunk
from researchgraph.query_context import build_context, validate_context
from researchgraph.query_presentation import source_presentation
from researchgraph.query_retrieval import retrieve
from sqlalchemy.orm import Session
from test_query_graph import production
from test_query_retrieval import request, science_rows, second_paper

seeded = test_knowledge.seeded


def test_original_quotes_and_existing_chinese_summary_are_readable_without_snapshot_drift(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "accuracy", [])
        context = build_context(session, request(), found)
        original = copy.deepcopy((found, context))
        fingerprint = digest(context)
        rows = science_rows(session)
        presentation = source_presentation(session, "project", found, context)
        assert (found, context) == original and digest(context) == fingerprint
        assert science_rows(session) == rows and not session.new and not session.dirty
        validate_context(session, context, found)
        span = session.get(EvidenceSpan, eid)
        knowledge = [h for h in found["hits"] if h["source_kind"] == "knowledge"]
        assert knowledge
        for hit in knowledge:
            display = presentation["hits"][hit["entry_id"]]
            assert display["original"] == span.quote
            assert display["summary_zh"] and display["summary_origin"] == "extracted_translation"
            assert hit["object_id"] not in display["original"]
            assert display["page_index"] == span.page_index
        evidence = next(r for r in context["references"] if r["type"] == "evidence")
        shown = presentation["references"][evidence["ref"]]
        assert shown["original"] == span.quote and shown["summary_zh"]


def test_missing_translation_is_explicit_and_does_not_borrow_other_paper_summary(seeded):
    _, engine, eid = seeded
    ids = production(engine, eid)
    second_paper(engine)
    with Session(engine) as session, session.begin():
        for nid in ids.values():
            display = session.get(KnowledgeDisplay, nid)
            display.data = {**display.data, "summary_zh": ""}
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "accuracy", ["paper"])
        context = build_context(session, request(paper_ids=["paper"]), found)
        presentation = source_presentation(session, "project", found, context)
        assert all(s["summary_zh"] is None for s in presentation["hits"].values())
        assert all(s["paper_id"] in {"paper", None} for s in presentation["references"].values())


def test_multi_page_node_quotes_do_not_claim_a_single_page(seeded):
    _, engine, eid = seeded
    ids = production(engine, eid)
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "accuracy", [])
        node_id = next(iter(ids.values()))
        old = session.get(EvidenceSpan, eid)
        session.get(AttachmentRevision, "version").page_count = 2
        quote = "A second-page supporting sentence."
        session.add(
            Chunk(
                id="later-page",
                revision_id="version",
                page_index=1,
                page_label="2",
                block_index=0,
                text=quote,
                bbox=[0.0, 0.0, 100.0, 20.0],
            )
        )
        session.flush()
        session.add(
            EvidenceSpan(
                id="later-span",
                document_version_id="version",
                section_id=old.section_id,
                paragraph_id="later-page",
                page_index=1,
                start_offset=0,
                end_offset=len(quote),
                quote=quote,
                text_sha256=text_hash(quote),
                normalization="exact",
                bbox_list=[[0.0, 0.0, 100.0, 20.0]],
            )
        )
        session.flush()
        session.add(NodeEvidence(node_id=node_id, evidence_id="later-span", role="support"))
        session.flush()
        display = source_presentation(session, "project", found)
        hit = next(h for h in found["hits"] if h["object_id"] == node_id)
        shown = display["hits"][hit["entry_id"]]
        assert old.quote in shown["original"] and quote in shown["original"]
        assert shown["page_index"] is None
