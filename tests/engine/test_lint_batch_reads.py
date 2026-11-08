"""A bounded scan batches reads while validating every source link again per call."""

import copy
import gc
import weakref
from collections import Counter

import pytest
import researchgraph.lint_service as lint_service
from researchgraph.knowledge_models import (
    KnowledgeDependency,
    KnowledgeNode,
    NodeEvidence,
)
from researchgraph.knowledge_store import KnowledgeStore, digest
from researchgraph.lint_service import LintStore
from researchgraph.models import Chunk
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session
from test_knowledge import seeded as seeded
from test_lint import start, step
from test_lint_performance import statements
from test_query_graph import production


@pytest.fixture
def batch_sources(seeded):
    _, engine, eid = seeded
    ids = production(engine, eid)
    with Session(engine) as session, session.begin():
        template = session.get(KnowledgeNode, ids["c"])
        source = {
            column.name: copy.deepcopy(getattr(template, column.name))
            for column in KnowledgeNode.__table__.columns
        }
        nodes, links, dependencies = [], [], []
        for index in range(105):
            node = copy.deepcopy(source)
            node.update(id=f"batch-candidate-{index:03}", fingerprint=digest(["batch", index]))
            node["payload"]["local_ref"] = f"batch-{index:03}"
            nodes.append(node)
            links.append({"node_id": node["id"], "evidence_id": eid, "role": "supports"})
            dependencies.append({"node_id": node["id"], "dependee_id": ids["m"], "role": "method"})
        session.execute(insert(KnowledgeNode), nodes)
        session.execute(insert(NodeEvidence), links)
        session.execute(insert(KnowledgeDependency), dependencies)
    return engine, eid


def test_each_link_is_validated_with_batch_sql_and_all_retained_rows_are_released(
    batch_sources, monkeypatch
):
    engine, _ = batch_sources
    original_validate = lint_service.validate_evidence
    original_check = LintStore._check
    original_prefetch = LintStore._prefetch_checks
    active_target = {}
    validated = Counter()
    retained_lists, retained_references = [], []

    def check(self, run, target):
        active_target.clear()
        active_target.update(target)
        try:
            return original_check(self, run, target)
        finally:
            active_target.clear()

    def validate(*args, **kwargs):
        if active_target.get("type") == "node":
            validated[active_target["id"]] += 1
        return original_validate(*args, **kwargs)

    def prefetch(self, targets):
        retained = original_prefetch(self, targets)
        retained_lists.append(retained)
        retained_references.extend(
            weakref.ref(row)
            for row in retained
            if str(getattr(row, "id", getattr(row, "node_id", ""))).startswith("batch-candidate-")
        )
        return retained

    monkeypatch.setattr(LintStore, "_check", check)
    monkeypatch.setattr(LintStore, "_prefetch_checks", prefetch)
    monkeypatch.setattr(lint_service, "validate_evidence", validate)
    with Session(engine) as session:
        expected = Counter(session.scalars(select(NodeEvidence.node_id)))
    run = start(engine, project_id="project", key="batch-read-start")
    batches = []
    while run["processed"] < run["total"]:
        count_before = sum(validated.values())
        with statements(engine) as observed:
            with Session(engine) as session, session.begin():
                store = LintStore(KnowledgeStore(session))
                run = store.advance("project", run["id"], 100, f"batch-read-{run['processed']}")
                assert store._batch_links is None and store._batch_dependencies is None
                assert retained_lists[-1] == []
                gc.collect()
                assert all(reference() is None for reference in retained_references)
        counts = {
            table: sum(
                sql.lstrip().upper().startswith("SELECT") and table in sql for sql, _ in observed
            )
            for table in ("node_evidence_links", "knowledge_dependencies")
        }
        checked_nodes = sum(validated.values()) - count_before
        assert checked_nodes > 5
        assert all(0 < count <= 3 for count in counts.values()), counts
        batches.append(counts)
    assert len(batches) == 2
    assert validated == expected
    assert len([node_id for node_id in validated if node_id.startswith("batch-candidate-")]) == 105
    assert run["errors"] == []


@pytest.mark.parametrize("change", ["source", "node_link"])
def test_next_advance_revalidates_source_and_node_associations_before_any_checks(
    batch_sources, monkeypatch, change
):
    engine, _ = batch_sources
    run = start(engine, project_id="project", key="batch-fresh-start")
    run = step(engine, run)
    assert run["status"] == "running" and run["processed"] == 100
    with Session(engine) as session, session.begin():
        if change == "source":
            session.get(Chunk, "paragraph").text = "Changed source after the completed batch."
        else:
            session.execute(
                delete(NodeEvidence).where(NodeEvidence.node_id == "batch-candidate-104")
            )
    validations, prefetched = [], []

    def forbidden_validation(*args, **kwargs):
        validations.append(True)
        raise AssertionError("A changed frozen input must stop before the next rule check")

    def forbidden_prefetch(*args, **kwargs):
        prefetched.append(True)
        raise AssertionError("A changed frozen input must stop before loading a rule batch")

    monkeypatch.setattr(lint_service, "validate_evidence", forbidden_validation)
    monkeypatch.setattr(LintStore, "_prefetch_checks", forbidden_prefetch)
    stopped = step(engine, run, key="batch-after-change")
    assert stopped["status"] == "input_stale"
    assert stopped["processed"] == run["processed"]
    assert stopped["phase"] == "finished"
    assert validations == [] and prefetched == []
