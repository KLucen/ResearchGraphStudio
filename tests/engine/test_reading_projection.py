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
    assert len(graph["nodes"]) == 2
    assert {e["relation"] for e in graph["edges"]} == {"HAS_CORE_CLAIM"}
    root = next(n for n in graph["nodes"] if n["kind"] == "Claim")
    expanded = post(api, url, {**body, "expanded_unit_ids": root["unit_ids"]}).json()
    assert len(expanded["nodes"]) == 5
    assert all(e["target"] == root["id"] for e in expanded["edges"] if e["source"] == "paper")
    assert all(e["epistemic_status"] == "navigation" for e in expanded["edges"])
    assert post(api, url, body).json()["nodes"] == graph["nodes"]


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
        "expanded_unit_ids": [u["id"] for u in units],
    }
    both = post(api, "/projects/project/graph/projection", body).json()
    assert len(both["nodes"]) == 6
    assert len({n["id"] for n in both["nodes"]}) == 6
    body["expanded_unit_ids"] = [units[1]["id"]]
    collapsed = post(api, "/projects/project/graph/projection", body).json()
    assert {n["id"] for n in collapsed["nodes"]} == {n["id"] for n in both["nodes"]}


# Explicit alias keeps the shared fixture registered when lint removes unused imports.
seeded = test_knowledge.seeded
