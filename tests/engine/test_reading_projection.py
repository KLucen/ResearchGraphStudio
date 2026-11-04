import asyncio

import test_knowledge
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.providers import MockProvider
from researchgraph.reading_pipeline import finish_reading
from sqlalchemy.orm import Session
from test_engine import post
from test_reading_extraction import candidate_batch, save
from test_reading_selection import setup_job


def build(engine, eid):
    save(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))


def test_backbone_expansion_has_no_paper_to_support_edges(seeded):
    api, engine, eid = seeded
    build(engine, eid)
    url = "/projects/project/graph/projection"
    body = {
        "view": "paper_backbone",
        "include_test_data": True,
        "kinds": ["Paper", "Claim", "Method", "Finding", "Condition"],
    }
    graph = post(api, url, body).json()
    assert len(graph["nodes"]) == 5
    assert {e["relation"] for e in graph["edges"]} == {"HAS_CORE_CLAIM", "UNIT_MEMBER"}
    root = next(n for n in graph["nodes"] if n["kind"] == "Claim")
    collapsed = post(api, url, {**body, "collapsed_unit_ids": root["unit_ids"]}).json()
    assert len(collapsed["nodes"]) == 2
    assert {e["relation"] for e in collapsed["edges"]} == {"HAS_CORE_CLAIM"}
    expanded = post(
        api,
        url,
        {**body, "collapsed_unit_ids": root["unit_ids"], "expanded_unit_ids": root["unit_ids"]},
    ).json()
    assert len(expanded["nodes"]) == 5
    assert all(e["target"] == root["id"] for e in expanded["edges"] if e["source"] == "paper")
    assert all(e["epistemic_status"] == "navigation" for e in expanded["edges"])
    assert post(api, url, body).json()["nodes"] == graph["nodes"]


def test_provisional_graph_keeps_support_but_does_not_claim_core_ranking(seeded):
    import pytest
    from researchgraph.providers import ProviderError
    from test_reading_semantic_flow import SemanticFixture
    from test_reading_semantic_flow import setup_job as semantic_job

    api, engine, eid = seeded
    save(engine, eid)
    semantic_job(engine)
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "job", SemanticFixture("p13_timeout")))
    body = {"view": "paper_backbone", "include_test_data": True}
    result = post(api, "/projects/project/graph/projection", body).json()
    assert result["build_state"] == "partial"
    assert result["paper_builds"][0]["ranking_status"] == "pending"
    assert result["paper_builds"][0]["selection_mode"] == "provisional"
    assert len(result["nodes"]) == 5
    root = next(n for n in result["nodes"] if n["kind"] == "Claim")
    assert root["graph_role"] == "provisional"
    assert {e["relation"] for e in result["edges"]} == {"HAS_CANDIDATE_CLAIM", "UNIT_MEMBER"}
    assert all(e["target"] == root["id"] for e in result["edges"] if e["source"] == "paper")
    collapsed = post(
        api,
        "/projects/project/graph/projection",
        {**body, "collapsed_unit_ids": root["unit_ids"]},
    ).json()
    assert len(collapsed["nodes"]) == 2
    assert collapsed["selections"] == result["selections"]


def test_preferences_do_not_delete_and_candidates_remain_searchable(seeded):
    api, engine, eid = seeded
    build(engine, eid)
    with Session(engine) as session:
        data = KnowledgeStore(session).reading().current("paper").data
    root = data["units"][0]["root_claim_id"]
    response = post(
        api,
        "/papers/paper/graph-selection/preferences",
        {
            "candidate_id": root,
            "action": "exclude_core",
            "expected_revision": 1,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["units"] == []
    candidates = api.get("/api/v1/papers/paper/candidates?limit=2").json()
    assert candidates["next_cursor"]
    next_page = api.get(
        "/api/v1/papers/paper/candidates", params={"limit": 2, "cursor": candidates["next_cursor"]}
    ).json()
    assert len(next_page["items"]) == 2
    restored = post(
        api,
        "/papers/paper/graph-selection/preferences",
        {
            "candidate_id": root,
            "action": "reset_automatic",
            "expected_revision": 2,
        },
        "restore-reading-preference",
    )
    assert restored.status_code == 200, restored.text
    assert len(restored.json()["units"]) == 1
    stale = api.get("/api/v1/papers/paper/candidates", params={"cursor": candidates["next_cursor"]})
    assert stale.status_code >= 400


def test_density_cached_rebuild_and_cross_paper_scope(seeded):
    api, engine, eid = seeded
    build(engine, eid)
    response = post(
        api,
        "/papers/paper/graph-selection/rebuild",
        {
            "document_version_id": "version",
            "density": "concise",
            "expected_revision": 1,
        },
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "succeeded"
    assert (
        post(
            api,
            "/papers/other/graph-selection/rebuild",
            {
                "document_version_id": "version",
                "expected_revision": 2,
            },
            "restore-reading-preference",
        ).status_code
        >= 400
    )


def test_shared_member_is_one_node_and_survives_other_unit_collapse(seeded):
    import copy

    api, engine, eid = seeded
    data = candidate_batch(eid)
    second = copy.deepcopy(data["items"][0])
    second["local_ref"] = "c2"
    second["statement"]["original"] = "The method also reduces memory requirements."
    data["items"].append(second)
    data["links"] += [{**edge, "source_local_ref": "c2"} for edge in list(data["links"])]
    save(engine, eid, data)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session:
        units = KnowledgeStore(session).reading().current("paper").data["units"]
    assert len(units) == 2
    body = {
        "view": "paper_backbone",
        "include_test_data": True,
        "kinds": ["Paper", "Claim", "Method", "Finding", "Condition"],
    }
    both = post(api, "/projects/project/graph/projection", body).json()
    assert len(both["nodes"]) == 6
    assert len({n["id"] for n in both["nodes"]}) == 6
    body["collapsed_unit_ids"] = [units[0]["id"]]
    collapsed = post(api, "/projects/project/graph/projection", body).json()
    assert {n["id"] for n in collapsed["nodes"]} == {n["id"] for n in both["nodes"]}
    assert all(
        units[0]["id"] not in n["unit_ids"]
        for n in collapsed["nodes"]
        if n["graph_role"] == "supporting"
    )
    body["collapsed_unit_ids"] = [u["id"] for u in units]
    assert len(post(api, "/projects/project/graph/projection", body).json()["nodes"]) == 3


def test_published_selection_display_completes_valid_paths_without_mutation(seeded):
    api, engine, eid = seeded
    build(engine, eid)
    with Session(engine) as session, session.begin():
        current = KnowledgeStore(session).reading().current("paper")
        data = {**current.data, "units": [{**u, "memberships": []} for u in current.data["units"]]}
        current.data = data
        snapshot, revision = current.snapshot_hash, current.revision
    graph = post(
        api,
        "/projects/project/graph/projection",
        {"view": "paper_backbone", "include_test_data": True},
    ).json()
    assert {n["kind"] for n in graph["nodes"]} == {
        "Paper",
        "Claim",
        "Method",
        "Finding",
        "Condition",
    }
    with Session(engine) as session:
        current = KnowledgeStore(session).reading().current("paper")
        assert current.snapshot_hash == snapshot and current.revision == revision
        assert current.data == data


def test_support_pagination_keeps_root_and_paper_and_hides_invalid_sources(seeded):
    from researchgraph.knowledge_models import KnowledgeNode
    from sqlalchemy import select

    api, engine, eid = seeded
    build(engine, eid)
    body = {"view": "paper_backbone", "include_test_data": True, "limit": 1}
    seen = set()
    while True:
        response = post(api, "/projects/project/graph/projection", body)
        assert response.status_code == 200, response.text
        graph = response.json()
        ids = {n["id"] for n in graph["nodes"]}
        seen |= ids
        assert all(e["source"] in ids and e["target"] in ids for e in graph["edges"])
        for node in graph["nodes"]:
            if node["graph_role"] == "supporting":
                assert any(e["target"] == node["id"] for e in graph["edges"])
                assert "paper" in ids
        if not graph["next_cursor"]:
            break
        body["cursor"] = graph["next_cursor"]
    assert len(seen) == 5
    with Session(engine) as session, session.begin():
        node = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "method"))
        node.source_status = "unresolved"
        invalid = node.id
    result = post(
        api,
        "/projects/project/graph/projection",
        {"view": "paper_backbone", "include_test_data": True},
    ).json()
    assert invalid not in {n["id"] for n in result["nodes"]}


# Explicit alias keeps the shared fixture registered when lint removes unused imports.
seeded = test_knowledge.seeded
