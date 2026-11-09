"""Offline P3 workflow, unsafe inference rejection, stale review and migration."""

import json
import sqlite3
from pathlib import Path

import pymupdf
import pytest
from alembic import command
from alembic.config import Config
from researchgraph import reasoning
from researchgraph.knowledge_models import KnowledgeDependency, KnowledgeNode, NodeEvidence
from researchgraph.knowledge_store import KnowledgeError
from researchgraph.models import AttachmentRevision, Paper
from researchgraph.providers import MockProvider
from researchgraph.reasoning_context import node_context, pair_context
from researchgraph.reasoning_contracts import ComparabilityReport, RelationInference
from researchgraph.reasoning_store import validate_inference
from researchgraph.storage import make_engine
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import queue, wait_job


@pytest.fixture
def paired(tmp_path):
    data = tmp_path / "data"
    with client(data, worker=True) as api:
        project = post(api, "/projects", {"name": "P3 synthetic"}).json()["id"]
        nodes = []
        for index, word in enumerate(["accuracy", "cooperation"]):
            source = tmp_path / f"Source {index}.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page()
                page.insert_text(
                    (50, 60), f"Our shared memory method improves {word} in the synthetic task."
                )
                pdf.save(source)
            imported = wait_job(api, queue(api, project, source, f"import-{index}"))
            assert imported["status"] == "succeeded", imported
            version = imported["result"]["revision_id"]
            extracted = wait_job(
                api,
                post(
                    api, "/knowledge/extract", {"document_version_id": version}, f"extract-{index}"
                ).json(),
            )
            assert extracted["status"] == "succeeded", extracted
            nodes.append(api.get(f"/api/v1/revisions/{version}/knowledge").json()["items"])
        yield api, project, nodes, data


def pair(nodes, kind="claim"):
    return [next(n for n in group if n["kind"] == kind) for group in nodes]


def infer(api, nodes, mode="relations", key="infer-test"):
    a, b = pair(nodes, "claim" if mode == "relations" else "method")
    response = post(
        api, f"/knowledge/{mode}/infer", {"source_id": a["id"], "target_id": b["id"]}, key
    )
    assert response.status_code == 202, response.text
    return wait_job(api, response.json())


def test_offline_workflow_retrieval_review_cache_and_restart(paired):
    api, project, nodes, data = paired
    a, b = pair(nodes)
    retrieved = post(api, "/knowledge/candidates", {"source_id": a["id"], "top_k": 1}).json()
    assert [n["id"] for n in retrieved["items"]] == [b["id"]]
    result = infer(api, nodes)
    assert result["status"] == "succeeded", result
    proposal_id = result["result"]["proposal_id"]
    detail = api.get(f"/api/v1/knowledge/relations/{proposal_id}").json()
    assert detail["proposal"]["review_status"] == "proposed"
    assert {r["prompt_name"] for r in detail["runs"]} == {
        "P04_compare_conditions",
        "P05_infer_relation",
    }
    assert detail["attempt"]["comparison"]["overall"] == "limited"
    assert all(d["comparison"] == "unknown" for d in detail["attempt"]["comparison"]["dimensions"])
    for index, action in enumerate(["accept", "reject"], 1):
        response = post(
            api,
            "/knowledge/semantic-reviews",
            {
                "kind": "relation",
                "proposal_id": proposal_id,
                "expected_revision": index,
                "action": action,
                "reason": "Synthetic workflow review only",
            },
            f"review-{index}",
        )
        assert response.status_code == 200, response.text
        if action == "accept":
            accepted = api.get(
                f"/api/v1/graph/subgraph?project_id={project}&status=accepted"
            ).json()
            assert accepted["relations"][0]["id"] == proposal_id
            assert len(accepted["nodes"]) == 2
    repeated = infer(api, nodes, key="repeat-run")
    assert repeated["result"]["reused"] and repeated["result"]["proposal_id"] == proposal_id
    graph = api.get(f"/api/v1/graph/subgraph?project_id={project}").json()
    assert graph["relations"][0]["review_status"] == "rejected"
    limited = api.get(f"/api/v1/graph/subgraph?project_id={project}&limit=1").json()
    assert len(limited["nodes"]) == 1 and limited["next_cursor"] and not limited["relations"]
    second = api.get(
        f"/api/v1/graph/subgraph?project_id={project}&limit=1&cursor={limited['next_cursor']}"
    ).json()
    assert second["nodes"][0]["id"] != limited["nodes"][0]["id"]
    with sqlite3.connect(data / "researchgraph.sqlite3") as db:
        assert db.execute("select count(*) from reasoning_attempts").fetchone()[0] == 1
        assert db.execute("select count(*) from semantic_reviews").fetchone()[0] == 2
        assert (
            db.execute(
                "select count(*) from knowledge_events "
                "where event_type='SEMANTIC_PROPOSAL_REVIEWED'"
            ).fetchone()[0]
            == 2
        )
        restart_dir = data.parent / "restarted"
        restart_dir.mkdir()
        with sqlite3.connect(restart_dir / "researchgraph.sqlite3") as copied:
            db.backup(copied)
    # Start a new application against a consistent persisted snapshot, with a new lock/token.
    with client(restart_dir) as reopened:
        restored = reopened.get(f"/api/v1/knowledge/relations/{proposal_id}").json()
        assert restored["proposal"]["revision"] == 3
        assert restored["proposal"]["review_status"] == "rejected"
        assert len(restored["reviews"]) == 2
        assert restored["runs"] == detail["runs"]
        assert restored["attempt"] == detail["attempt"]


def test_condition_revision_blocks_stale_acceptance_but_keeps_original(paired):
    api, project, nodes, _ = paired
    result = infer(api, nodes)
    assert result["status"] == "succeeded", result
    proposal_id = result["result"]["proposal_id"]
    before = api.get(f"/api/v1/knowledge/relations/{proposal_id}").json()
    condition = next(n for n in nodes[0] if n["kind"] == "condition")
    detail = api.get(f"/api/v1/knowledge/nodes/{condition['id']}").json()
    revised = post(
        api,
        "/knowledge/reviews",
        {
            "node_id": condition["id"],
            "expected_revision": 1,
            "expected_graph_revision": detail["graph_revision"],
            "action": "revise",
            "reason": "Mark synthetic task not applicable",
            "payload": {**condition["payload"], "known_state": "not_applicable"},
        },
        "condition-change",
    )
    assert revised.status_code == 200, revised.text
    stale = api.get(f"/api/v1/knowledge/relations/{proposal_id}").json()
    assert stale["proposal"]["stale"] and stale["attempt"] == before["attempt"]
    response = post(
        api,
        "/knowledge/semantic-reviews",
        {
            "kind": "relation",
            "proposal_id": proposal_id,
            "expected_revision": 1,
            "action": "accept",
            "reason": "Attempt stale acceptance",
        },
        "stale-review",
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "STALE_INPUT"
    again = infer(api, nodes, key="new-conditions")
    assert again["status"] == "succeeded" and not again["result"]["reused"]


@pytest.mark.parametrize(
    "attack",
    [
        "unknown_id",
        "one_side",
        "false_same",
        "false_conflict",
        "invalid_json",
        "timeout",
        "network",
    ],
)
def test_bad_model_output_never_creates_relation(paired, monkeypatch, attack):
    api, _, nodes, data = paired

    class Bad(MockProvider):
        async def complete(self, prompt, value, schema):
            raw = await super().complete(prompt, value, schema)
            output = json.loads(raw)
            if schema["title"] == "ComparabilityReport":
                if attack == "false_same":
                    output["dimensions"][0]["comparison"] = "same"
                return json.dumps(output)
            if attack == "invalid_json":
                return "not json"
            if attack == "timeout":
                raise TimeoutError()
            if attack == "network":
                raise ValueError("Fixture network failure")
            if attack == "unknown_id":
                output["evidence_ids"].append("invented")
            if attack == "one_side":
                output["evidence_ids"] = value["claim_a"]["evidence_ids"]
            if attack == "false_conflict":
                output["relation_type"] = "CONTRADICTS"
            return json.dumps(output)

    monkeypatch.setattr(reasoning, "MockProvider", Bad)
    result = infer(api, nodes)
    assert result["status"] == "failed", result
    with sqlite3.connect(data / "researchgraph.sqlite3") as db:
        assert db.execute("select count(*) from relation_assertions").fetchone()[0] == 0
        assert db.execute("select count(*) from reasoning_attempts").fetchone()[0] == 0
        assert (
            db.execute(
                "select count(*) from model_runs where status in ('failed','validation_failed')"
            ).fetchone()[0]
            >= 1
        )


def test_no_decision_is_history_only_and_alignment_does_not_merge(paired, monkeypatch):
    api, _, nodes, data = paired

    class Undecided(MockProvider):
        async def complete(self, prompt, value, schema):
            output = json.loads(await super().complete(prompt, value, schema))
            if schema["title"] == "RelationInference":
                output.update(decision="NO_DECISION", relation_type=None)
            return json.dumps(output)

    monkeypatch.setattr(reasoning, "MockProvider", Undecided)
    result = infer(api, nodes)
    assert result["status"] == "succeeded" and not result["result"]["proposal_id"]
    alignment = infer(api, nodes, mode="alignments", key="align-methods")
    assert alignment["status"] == "succeeded", alignment
    assert alignment["result"]["proposal_id"]
    with sqlite3.connect(data / "researchgraph.sqlite3") as db:
        assert db.execute("select count(*) from relation_assertions").fetchone()[0] == 0
        assert (
            db.execute("select count(*) from knowledge_nodes where kind='method'").fetchone()[0]
            == 2
        )
        assert db.execute("select count(*) from entity_alignments").fetchone()[0] == 1


def test_scope_rejection_and_search_input_is_not_sql(paired):
    api, _, nodes, _ = paired
    a, b = pair(nodes)
    same = post(
        api, "/knowledge/relations/infer", {"source_id": a["id"], "target_id": a["id"]}, "self-pair"
    )
    assert same.status_code == 422
    result = post(
        api,
        "/knowledge/candidates",
        {"source_id": a["id"], "query": '" OR 1=1; DROP TABLE papers --', "top_k": 2},
    )
    assert result.status_code == 200
    with Session(api.app.state.engine) as session:
        snapshot = pair_context(session, a["id"], b["id"], "relation")
        # Comparable report cannot turn different task/metric units into contradiction.
        for side in ("source", "target"):
            snapshot[side]["dimensions"] = {
                k: {"known_state": "known", "value": "toy", "unit": None}
                for k in ("task_type", "dataset", "metric")
            }
        snapshot["target"]["dimensions"]["metric"]["unit"] = "seconds"
        report = ComparabilityReport(
            source_claim_id=a["id"],
            target_claim_id=b["id"],
            topic_overlap="same",
            overall="comparable",
            dimensions=[],
            rationale="fixture",
        )
        inference = RelationInference(
            source_claim_id=a["id"],
            target_claim_id=b["id"],
            decision="PROPOSE_RELATION",
            relation_type="CONTRADICTS",
            reason="fixture",
            evidence_ids=snapshot["source"]["root_evidence_ids"]
            + snapshot["target"]["root_evidence_ids"],
        )
        with pytest.raises(KnowledgeError, match="对齐"):
            validate_inference(inference, report, snapshot)


def test_0007_upgrade_preserves_existing_tables_and_fts_backfills(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).parents[2] / "services/engine/researchgraph/migrations"),
    )
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "0007")
        conn.exec_driver_sql("INSERT INTO projects VALUES ('p','old project','','now')")
    with Session(engine) as session, session.begin():
        session.add(Paper(id="paper", project_id="p", title="Old paper", created_at="now"))
        session.flush()
        session.add(
            AttachmentRevision(
                id="v",
                paper_id="paper",
                sha256="a" * 64,
                parser_version="old",
                page_count=1,
                warnings=[],
                created_at="now",
            )
        )
        session.flush()
        session.add(
            KnowledgeNode(
                id="old-node",
                paper_id="paper",
                document_version_id="v",
                kind="claim",
                text="Preserved scientific memory",
                payload={},
                origin="paper_author",
                authorship="author",
                source_status="verified",
                review_status="accepted",
                issues=[],
                fingerprint="b" * 64,
                revision=2,
                created_at="now",
                updated_at="now",
            )
        )
    engine.dispose()
    with client(tmp_path) as api:
        assert api.get("/api/v1/projects").json()["items"][0]["name"] == "old project"
        assert api.get("/api/v1/health").json()["schema_version"] == "0022"
        with sqlite3.connect(tmp_path / "researchgraph.sqlite3") as db:
            assert db.execute(
                "select node_id from knowledge_fts where knowledge_fts match 'memory'"
            ).fetchall() == [("old-node",)]
            assert db.execute(
                "select text,review_status,revision from knowledge_nodes where id='old-node'"
            ).fetchone() == ("Preserved scientific memory", "accepted", 2)
    backups = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("select version_num from alembic_version").fetchone()[0] == "0007"
        assert db.execute("select count(*) from knowledge_nodes").fetchone()[0] == 1


def test_other_project_is_excluded_from_retrieval_graph_and_inference(paired):
    api, project, nodes, _ = paired
    a, b = pair(nodes)
    other = post(api, "/projects", {"name": "Isolated project"}, "other-project").json()["id"]
    with Session(api.app.state.engine) as session, session.begin():
        session.get(Paper, b["paper_id"]).project_id = other
    assert not post(api, "/knowledge/candidates", {"source_id": a["id"]}).json()["items"]
    graph = api.get(f"/api/v1/graph/subgraph?project_id={project}").json()
    assert all(n["paper_id"] == a["paper_id"] for n in graph["nodes"])
    rejected = post(api, "/knowledge/relations/infer", {"source_id": a["id"], "target_id": b["id"]})
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "PAIR_SCOPE_MISMATCH"


def test_alignment_cannot_reference_unprovided_candidate(paired, monkeypatch):
    api, _, nodes, data = paired

    class WrongCandidate(MockProvider):
        async def complete(self, prompt, value, schema):
            output = json.loads(await super().complete(prompt, value, schema))
            output["alignments"][0]["candidate_concept_id"] = "unprovided"
            return json.dumps(output)

    monkeypatch.setattr(reasoning, "MockProvider", WrongCandidate)
    result = infer(api, nodes, mode="alignments")
    assert result["status"] == "failed"
    with sqlite3.connect(data / "researchgraph.sqlite3") as db:
        assert db.execute("select count(*) from entity_alignments").fetchone()[0] == 0


def test_missing_condition_is_not_a_conflict_with_explicit_evidenced_context(paired):
    api, _, nodes, _ = paired
    a, _ = pair(nodes)
    with Session(api.app.state.engine) as session, session.begin():
        root = session.get(KnowledgeNode, a["id"])
        before = node_context(session, root)
        assert before["dimensions"]["metric"]["known_state"] == "unknown"
        template = session.get(
            KnowledgeNode, next(n["id"] for n in nodes[0] if n["kind"] == "condition")
        )
        evidence_id = before["root_evidence_ids"][0]
        for index, value in enumerate(("accuracy", "duration")):
            fields = {c.name: getattr(template, c.name) for c in template.__table__.columns}
            fields.update(
                id=f"explicit-{index}",
                fingerprint=f"explicit-{index}",
                dimension="metric",
                known_state="known",
                value=value,
                source_status="source_verified",
                payload={
                    "dimension": "metric",
                    "known_state": "known",
                    "value": value,
                    "evidence_span_ids": [evidence_id],
                },
            )
            condition = KnowledgeNode(**fields)
            session.add(condition)
            session.flush()
            session.add(NodeEvidence(node_id=condition.id, evidence_id=evidence_id, role="direct"))
            session.add(
                KnowledgeDependency(node_id=root.id, dependee_id=condition.id, role="HAS_CONDITION")
            )
            session.flush()
            current = node_context(session, root)["dimensions"]["metric"]
            assert current["known_state"] == ("known" if index == 0 else "conflicting")
            assert current["value"] == ("accuracy" if index == 0 else None)
