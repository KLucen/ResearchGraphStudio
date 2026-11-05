"""All local matches are pageable; display filtering never changes model context."""

import asyncio
import copy
import time

import pytest
import test_knowledge
import test_query_api
from researchgraph.graph_contracts import ProjectionQuery
from researchgraph.graph_projection import GraphProjectionService
from researchgraph.knowledge_models import AuthorizedRoot, EvidenceSpan, KnowledgeNode
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import Chunk, now
from researchgraph.providers import MockProvider
from researchgraph.query_browse import QueryBrowseRequest, browse, graph_membership
from researchgraph.query_contracts import QueryRequest
from researchgraph.query_models import QueryRun
from researchgraph.query_retrieval import retrieve
from researchgraph.reading_models import ReadingHead, ReadingSelection
from researchgraph.reading_pipeline import finish_reading
from researchgraph.reading_projection import collect_backbone, project
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_query_api import PREFIX, error, prepare
from test_query_graph import production, second_paper
from test_query_retrieval import document, notes, science_rows
from test_reading_extraction import candidate_batch
from test_reading_selection import setup_job

seeded = test_knowledge.seeded
api_setup = test_query_api.api_setup


def command(*, page=1, **changes):
    return QueryBrowseRequest(
        request=QueryRequest(project_id="project", question="accuracy"), page=page, **changes
    )


def add_raw(engine, count=27):
    with Session(engine) as session, session.begin():
        for index in range(count):
            session.add(
                Chunk(
                    id=f"accuracy-raw-{index:04}",
                    revision_id="version",
                    page_index=0,
                    page_label="1",
                    block_index=100 + index,
                    text=f"Accuracy observation number {index}.",
                    bbox=[0, 0, 10, 10],
                )
            )


def test_all_matches_pages_of_ten_leave_frozen_preparation_and_science_unchanged(api_setup):
    api, engine = api_setup
    add_raw(engine)
    prepared = prepare(api)
    original_snapshot = copy.deepcopy(prepared["snapshot"])
    assert len(original_snapshot["retrieval"]["hits"]) == 20
    with Session(engine) as session:
        before = science_rows(session)
        run_count = session.scalar(select(func.count()).select_from(QueryRun))
    body = {"request": {"project_id": "project", "question": "accuracy"}}
    first = api.post(PREFIX + "/search/page", json=body)
    assert first.status_code == 200, first.text
    first = first.json()
    assert first["total"] == 28 and first["total_pages"] == 3
    assert first["page_size"] == 10 and len(first["hits"]) == 10
    ids = [h["entry_id"] for h in first["hits"]]
    for page, expected in [(2, 10), (3, 8)]:
        response = api.post(
            PREFIX + "/search/page",
            json={**body, "page": page, "expected_result_hash": first["result_hash"]},
        )
        assert response.status_code == 200, response.text
        value = response.json()
        assert len(value["hits"]) == expected and value["result_hash"] == first["result_hash"]
        assert set(value["presentation"]["hits"]) == {h["entry_id"] for h in value["hits"]}
        ids += [h["entry_id"] for h in value["hits"]]
    assert len(set(ids)) == 28
    with Session(engine) as session, session.begin():
        all_hits = retrieve(session, "project", "accuracy", [], limit=None)["hits"]
        assert ids == [h["entry_id"] for h in all_hits]
        assert science_rows(session) == before
        assert session.scalar(select(func.count()).select_from(QueryRun)) == run_count
        run = session.get(QueryRun, prepared["query_id"])
        assert run.snapshot == original_snapshot and run.input_hash == prepared["input_hash"]


def test_display_paper_filter_is_independent_and_complete(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    second_paper(engine)
    with Session(engine) as session, session.begin():
        all_results = browse(session, "project", command())
        filtered = browse(session, "project", command(display_paper_ids=["paper2"]))
        assert filtered["total"] and filtered["total"] < all_results["total"]
        assert all(p["paper_ids"] == ["paper2"] for p in filtered["presentation"]["hits"].values())
        both = browse(session, "project", command(display_paper_ids=["paper2", "paper"]))
        assert both["total"] == all_results["total"]
        restricted = command(display_paper_ids=["paper2"])
        restricted.request.paper_ids = ["paper"]
        assert browse(session, "project", restricted)["total"] == 0
        with pytest.raises(KnowledgeError, match="不属于"):
            browse(session, "project", command(display_paper_ids=["other-project-paper"]))


def test_result_change_and_invalid_page_do_not_return_mixed_content(api_setup):
    api, engine = api_setup
    add_raw(engine)
    body = {"request": {"project_id": "project", "question": "accuracy"}}
    first = api.post(PREFIX + "/search/page", json=body).json()
    with Session(engine) as session, session.begin():
        session.get(Chunk, "accuracy-raw-0000").text = "A changed unrelated paragraph."
    changed = api.post(
        PREFIX + "/search/page",
        json={**body, "page": 2, "expected_result_hash": first["result_hash"]},
    )
    error(changed, "QUERY_RESULTS_CHANGED")
    error(api.post(PREFIX + "/search/page", json={**body, "page": 99}), "QUERY_PAGE_INVALID")
    assert api.post(PREFIX + "/search/page", json={**body, "page_size": 20}).status_code == 422
    assert (
        api.post(
            PREFIX + "/search/page", json={**body, "display_paper_ids": ["paper", "paper"]}
        ).status_code
        == 422
    )


def test_revocation_revalidates_later_pages_and_clears_private_hits(seeded, tmp_path):
    _, engine, eid = seeded
    production(engine, eid)
    notes(engine, tmp_path)
    add_raw(engine)
    body = command()
    body.request.include_personal = True
    with Session(engine) as session, session.begin():
        first = browse(session, "project", body)
    with Session(engine) as session, session.begin():
        session.get(AuthorizedRoot, "root").active = False
    with Session(engine) as session, session.begin():
        with pytest.raises(KnowledgeError, match="已变化"):
            browse(
                session,
                "project",
                body.model_copy(update={"page": 2, "expected_result_hash": first["result_hash"]}),
            )
        refreshed = retrieve(session, "project", "accuracy", [], limit=None, include_personal=True)
        assert not any(h["source_kind"] == "note" for h in refreshed["hits"])


def test_graph_badges_use_default_selected_nodes_and_their_original_evidence(seeded):
    _, engine, eid = seeded
    data = candidate_batch(eid)
    extra = copy.deepcopy(data["items"][1])
    extra.update(local_ref="unused", kind="Concept", aliases=[])
    extra.pop("method_role")
    extra["label"]["original"] = "Accuracy background concept"
    data["items"].append(extra)
    ids = production(engine, eid, data)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    document(engine)
    with Session(engine) as session, session.begin():
        before = science_rows(session)
        results = browse(session, "project", command())
        cards = results["presentation"]["hits"]
        by_id = {
            hit["object_id"]: cards[hit["entry_id"]]["graph_presence"] for hit in results["hits"]
        }
        assert by_id[ids["c"]]["state"] == "in_graph"
        assert by_id[ids["c"]]["representation"] == "node"
        assert by_id[ids["unused"]]["state"] == "retrieval_only"
        assert by_id["paragraph"]["state"] == "in_graph"
        assert by_id["paragraph"]["representation"] == "evidence"
        wiki = next(hit for hit in results["hits"] if hit["source_kind"] == "wiki")
        assert cards[wiki["entry_id"]]["graph_presence"]["state"] == "not_applicable"
        assert science_rows(session) == before
        previous = digest(results)
        current = KnowledgeStore(session).reading().current("paper")
        current.data = {**current.data, "units": []}
        changed = browse(session, "project", command())
        assert digest(changed) != previous
        claim = next(h for h in changed["hits"] if h["object_id"] == ids["c"])
        assert (
            changed["presentation"]["hits"][claim["entry_id"]]["graph_presence"]["state"]
            == "retrieval_only"
        )


def test_large_actual_backbone_membership_is_built_once_before_canvas_pagination(
    seeded, monkeypatch
):
    _, engine, eid = seeded
    data = candidate_batch(eid)
    root = copy.deepcopy(data["items"][0])
    method = copy.deepcopy(data["items"][1])
    for start, stop in [(0, 90), (90, 140)]:
        batch = (
            copy.deepcopy(data)
            if start == 0
            else {**data, "items": [root], "links": [], "chunk_id": "later-batch"}
        )
        for index in range(start, stop):
            item = copy.deepcopy(method)
            item["local_ref"] = f"support-{index}"
            item["label"]["original"] = f"Accuracy supporting method {index}"
            item["summary"]["original"] = f"Accuracy supporting method {index}"
            batch["items"].append(item)
            batch["links"].append(
                {
                    "source_local_ref": "c",
                    "target_local_ref": item["local_ref"],
                    "relation": "ASSOCIATED_METHOD",
                    "evidence_ids": [eid],
                }
            )
        if start == 0:
            ids = production(engine, eid, batch)
        else:
            with Session(engine) as session, session.begin():
                KnowledgeStore(session).reading().apply_candidates(
                    candidate=batch,
                    version_id="version",
                    paper_id="paper",
                    chunk_id="later-batch",
                    allowed={eid},
                    run_id="run",
                    key="later-supports",
                )
    with Session(engine) as session, session.begin():
        rows = list(session.scalars(select(KnowledgeNode)))
        session.add(
            ReadingSelection(
                id="selected",
                paper_id="paper",
                document_version_id="version",
                revision=1,
                snapshot_hash="a" * 64,
                created_at=now(),
                data={
                    "candidate_scope": "reading-candidates-only-v1",
                    "selection_mode": "ranked",
                    "coverage_gaps": [],
                    "entries": [
                        {
                            "candidate_id": n.id,
                            "graph_role": "core" if n.id == ids["c"] else "supporting",
                        }
                        for n in rows
                    ],
                    "units": [{"id": "selected-unit", "root_claim_id": ids["c"], "caveats": []}],
                },
            )
        )
        session.flush()
        session.add(ReadingHead(paper_id="paper", selection_id="selected", revision=1))
    calls = []

    def counted(service, body):
        calls.append(body.cursor)
        return collect_backbone(service, body)

    monkeypatch.setattr("researchgraph.query_browse.collect_backbone", counted)
    with Session(engine) as session:
        first = project(
            GraphProjectionService(session, "project"),
            ProjectionQuery(view="paper_backbone", limit=120),
        )
        assert first.has_more
        started = time.perf_counter()
        nodes, revision = graph_membership(session, "project")
        elapsed = time.perf_counter() - started
        assert set(nodes) - {n.id for n in first.nodes}
        assert len(nodes) == 145 and calls == [""]
        assert revision == first.graph_revision and elapsed < 10


def test_complete_multipaper_browse_skips_quadratic_comparisons_only_for_preview(
    seeded, monkeypatch
):
    _, engine, eid = seeded
    data = candidate_batch(eid)
    for index in range(24):
        claim = copy.deepcopy(data["items"][0])
        claim["local_ref"] = f"claim-{index}"
        claim["statement"]["original"] = f"Accuracy scientific result {index}"
        data["items"].append(claim)
    production(engine, eid, data)
    second_paper(engine)
    with Session(engine) as session, session.begin():
        second_eid = session.scalar(
            select(EvidenceSpan.id).where(EvidenceSpan.document_version_id == "version2")
        )
        second = {**data, "document_version_id": "version2", "chunk_id": "later-second"}
        second["items"] = [{**item, "evidence_ids": [second_eid]} for item in data["items"]]
        second["links"] = [{**link, "evidence_ids": [second_eid]} for link in data["links"]]
        KnowledgeStore(session).reading().apply_candidates(
            candidate=second,
            version_id="version2",
            paper_id="paper2",
            chunk_id="later-second",
            allowed={second_eid},
            run_id="run2",
            key="many-second-claims",
        )

    def forbidden(*args):
        raise AssertionError("preview must not compute all Claim-pair comparisons")

    monkeypatch.setattr("researchgraph.query_graph._compare", forbidden)
    with Session(engine) as session, session.begin():
        started = time.perf_counter()
        result = browse(session, "project", command())
        assert result["total"] > 50 and result["graph_node_count"] > 50
        assert time.perf_counter() - started < 10
        with pytest.raises(AssertionError, match="Claim-pair"):
            retrieve(session, "project", "accuracy", [])
