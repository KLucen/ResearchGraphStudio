"""Deterministic Lint and reverse dependencies over isolated sources and a temporary Vault."""

import hashlib

import pytest
from researchgraph.graph_models import GraphLayout
from researchgraph.knowledge_models import GraphRevision, KnowledgeNode
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.lint_contracts import LintRepairPlan, LintRequest
from researchgraph.lint_models import DependencyCursor, DependencyIndex, LintRun
from researchgraph.lint_service import (
    RULES,
    LintStore,
    _repair_plan,
    dependencies,
    get_run,
    list_issues,
)
from researchgraph.models import Chunk
from researchgraph.query_models import QueryPassage
from researchgraph.wiki_publish import WikiPublisher
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_knowledge import seeded as seeded
from test_query_documents import add_note
from test_query_documents import engine as engine
from test_query_documents import request as document_request
from test_wiki_documents import draft, patch, save
from test_wiki_publication import output


def start(engine, *, key="lint-start-one", project_id="p", **scope):
    with Session(engine) as session, session.begin():
        return LintStore(KnowledgeStore(session)).start(project_id, LintRequest(**scope), key)


def step(engine, run, count=100, key=None):
    with Session(engine) as session, session.begin():
        return LintStore(KnowledgeStore(session)).advance(
            run["project_id"],
            run["id"],
            count,
            key
            or "advance-"
            + run["id"]
            + "-"
            + run.get("phase", "scanning")
            + "-"
            + str(run["processed"]),
        )


def scan(engine, **scope):
    run = start(engine, **scope)
    while run["status"] in {"queued", "running"}:
        run = step(engine, run)
    return run


def issues(engine, run, **filters):
    with Session(engine) as session:
        return list_issues(session, run["project_id"], run["id"], page_size=100, **filters)["items"]


def codes(engine, run):
    return {issue["code"] for issue in issues(engine, run)}


def document(engine, key="save-document-one", **changes):
    with Session(engine) as session, session.begin():
        return KnowledgeStore(session).query().save_document(document_request(**changes), key)


def rebuild(engine, key="rebuild-dependencies-one"):
    with Session(engine) as session, session.begin():
        return LintStore(KnowledgeStore(session)).rebuild_dependencies("p", key)


def test_clean_scan_is_read_only_and_fingerprints_persist_then_resolve(engine):
    first = scan(engine)
    assert first["status"] == "completed" and first["processed"] == first["total"]
    assert codes(engine, first) == {"SOURCE_UNCHECKED"}
    second = scan(engine, key="lint-start-two")
    assert second["diff"] == {"new": 0, "persistent": 1, "resolved": 0}
    assert issues(engine, first)[0]["fingerprint"] == issues(engine, second)[0]["fingerprint"]
    with Session(engine) as session:
        assert session.get(Chunk, "c").text == "A method at 20 K."
        assert session.get(GraphRevision, "p") is None
        assert list(session.scalars(select(KnowledgeNode))) == []


def test_information_issues_include_safe_repair_plans_without_auto_fixing(engine):
    first = scan(engine)
    source = next(item for item in issues(engine, first) if item["code"] == "SOURCE_UNCHECKED")
    assert source["repair_plan"]["status"] == "informational"
    assert [step["action"] for step in source["repair_plan"]["steps"]] == [
        "inspect_source",
        "refresh_check",
        "recheck_lint",
    ]
    assert all(not step["automated"] for step in source["repair_plan"]["steps"])
    assert "不把未检查解释为文件丢失或科学错误。" in source["repair_plan"]["safeguards"]


@pytest.mark.parametrize("code", RULES)
def test_each_rule_has_valid_non_executing_repair_guidance(code):
    severity, category, _, suggestion = RULES[code]
    plan = LintRepairPlan.model_validate(_repair_plan(code, severity, category, suggestion))
    assert plan.summary and plan.steps and plan.safeguards
    assert all(step.title and step.description and not step.automated for step in plan.steps)
    assert plan.steps[-1].action == "recheck_lint"


@pytest.mark.parametrize(
    "code,action",
    [
        ("NOTE_CHANGED", "refresh_personal_snapshot"),
        ("NOTE_UNTRACKED", "inspect_attribution"),
        ("DEPENDENCY_UNVERIFIED", "inspect_attribution"),
        ("LINK_UNVERIFIABLE", "inspect_authorization"),
        ("FILE_MODIFIED", "inspect_file_diff"),
    ],
)
def test_private_unverified_or_modified_text_is_not_directed_to_managed_publication(code, action):
    severity, category, _, suggestion = RULES[code]
    plan = _repair_plan(code, severity, category, suggestion)
    assert plan["steps"][1]["action"] == action
    assert all(step["requires_model"] is False for step in plan["steps"])
    assert all(
        step["action"] not in {"prepare_export", "recover_publication"} for step in plan["steps"]
    )


@pytest.mark.parametrize(
    "state,code,action",
    [
        ("modified", "FILE_MODIFIED", "register_external_version"),
        ("missing", "FILE_MISSING", "inspect_external_source"),
        ("unavailable", "FILE_UNAVAILABLE", "inspect_authorization"),
    ],
)
def test_external_file_findings_offer_read_only_source_actions_and_keep_snapshots(
    engine, tmp_path, state, code, action
):
    from researchgraph.external_documents import validate_external_version
    from test_external_documents import persistence, register
    from test_external_documents import request as external_request

    with Session(engine) as session, session.begin():
        root, _, path = add_note(session, tmp_path)
        source = {"root_id": root.id, "relative_path": "note.md", "path": path}
    saved = register(engine, external_request(source))
    before = persistence(engine)
    if state == "modified":
        path.write_bytes(b"User-edited external text.\n")
    else:
        path.unlink()
        if state == "unavailable":
            path.mkdir()  # A directory at the former file path cannot be read as a file.

    report = scan(
        engine,
        key="external-file-plan-" + state,
        document_ids=[saved["document_id"]],
        include_personal=True,
    )
    finding = next(
        item
        for item in issues(engine, report)
        if item["code"] == code and item["object_type"] == "external"
    )
    plan = finding["repair_plan"]
    assert plan["steps"][1]["action"] == action
    assert all(step["requires_model"] is False and not step["automated"] for step in plan["steps"])
    assert all(
        step["action"] not in {"prepare_export", "recover_publication", "prepare_document_update"}
        for step in plan["steps"]
    )
    assert "旧快照" in str(plan)
    assert persistence(engine) == before
    with Session(engine) as session:
        historical = validate_external_version(
            session, "p", saved["version_id"], include_personal=True
        )
        assert (historical["text"], historical["sha256"]) == (saved["text"], saved["sha256"])
        assert historical["file_state"] == state
        assert session.get(GraphRevision, "p") is None
    if state == "modified":
        assert path.read_bytes() == b"User-edited external text.\n"
    elif state == "missing":
        assert not path.exists()
    else:
        assert path.is_dir() and list(path.iterdir()) == []


@pytest.mark.parametrize("code", ["FILE_MODIFIED", "FILE_CONFLICT", "MANAGED_IDENTITY_INVALID"])
def test_managed_conflicts_use_existing_directory_selection_instead_of_filename_editing(code):
    severity, category, _, suggestion = RULES[code]
    plan = _repair_plan(code, severity, category, suggestion, object_type="wiki_page")
    detail = plan["steps"][1]["description"]
    assert "授权目录与 Markdown 导出" in detail
    assert "不同的独立授权目录" in detail and "由程序" in detail and "受管路径" in detail
    assert "文件名" not in detail
    assert all(step["requires_model"] is False for step in plan["steps"])


def test_broken_link_plan_only_offers_model_free_target_or_private_editor_actions():
    severity, category, _, suggestion = RULES["LINK_BROKEN"]
    plan = _repair_plan("LINK_BROKEN", severity, category, suggestion)
    detail = plan["steps"][1]["description"]
    assert "原文件管理器" in detail and "原编辑器" in detail
    assert "草稿" not in detail
    assert all(step["requires_model"] is False for step in plan["steps"])


@pytest.mark.parametrize("code", ["RELATION_BROKEN", "CONDITION_STATE_INVALID", "DEPENDENCY_STALE"])
def test_controlled_scientific_repair_does_not_claim_to_be_model_free(code):
    severity, category, _, suggestion = RULES[code]
    plan = _repair_plan(code, severity, category, suggestion)
    assert plan["steps"][1]["requires_model"] is None
    assert plan["steps"][0]["requires_model"] is False
    assert plan["steps"][-1]["requires_model"] is False


def test_stale_and_resolved_findings_do_not_offer_outdated_repairs():
    severity, category, _, suggestion = RULES["FILE_MISSING"]
    stale = _repair_plan("FILE_MISSING", severity, category, suggestion, lifecycle="input_stale")
    resolved = _repair_plan("FILE_MISSING", severity, category, suggestion, lifecycle="resolved")
    assert stale["status"] == "blocked"
    assert [step["action"] for step in stale["steps"]] == ["recheck_lint"]
    assert resolved["status"] == "informational"
    assert [step["action"] for step in resolved["steps"]] == ["inspect_report"]


def test_injected_anchor_failure_and_fixed_input_report_diff(engine):
    with Session(engine) as session, session.begin():
        session.get(Chunk, "c").text = "Changed source text."
    failed = scan(engine)
    assert "EVIDENCE_INVALID" in codes(engine, failed)
    with Session(engine) as session, session.begin():
        session.get(Chunk, "c").text = "A method at 20 K."
    fixed = scan(engine, key="lint-fixed-input")
    resolved = issues(engine, fixed, lifecycle="resolved")
    assert {r["code"] for r in resolved} == {"EVIDENCE_INVALID"}
    assert resolved[0]["repair_plan"]["steps"][0]["action"] == "inspect_report"
    assert fixed["diff"]["resolved"] == 1
    assert "EVIDENCE_INVALID" in codes(engine, failed)  # immutable old report


def test_restart_bounded_progress_idempotency_and_cancel(engine):
    run = start(engine)
    run = step(engine, run, 1, "step-one")
    assert run["processed"] == 1
    assert step(engine, run, 1, "step-one")["processed"] == 1
    engine.dispose()
    with Session(engine) as session:
        resumed = get_run(session, "p", run["id"])
    assert resumed["processed"] == 1
    with Session(engine) as session, session.begin():
        cancelled = LintStore(KnowledgeStore(session)).cancel("p", run["id"], "cancel-one")
    assert cancelled["status"] == "cancelled"
    assert step(engine, cancelled)["processed"] == 1
    with pytest.raises(KnowledgeError, match="操作标识"):
        start(engine, document_ids=["different"], key="lint-start-one")


def test_changed_frozen_input_stops_without_mixing_results(engine):
    run = start(engine)
    run = step(engine, run, 1)
    with Session(engine) as session, session.begin():
        session.get(Chunk, "c").text = "Changed after frozen input."
    stale = step(engine, run)
    assert stale["status"] == "input_stale"
    assert stale["processed"] == 1
    assert all(i["lifecycle"] == "input_stale" for i in issues(engine, stale))


def test_rule_failure_keeps_completed_scope_and_reports_partial(engine, monkeypatch):
    original = LintStore._check

    def check(self, run, target):
        if target["type"] == "chunk":
            raise RuntimeError("private exception must not appear")
        return original(self, run, target)

    monkeypatch.setattr(LintStore, "_check", check)
    run = scan(engine)
    assert run["status"] == "partial" and run["processed"] == run["total"]
    assert run["errors"] == [{"object_type": "chunk", "object_id": "c", "code": "LINT_RULE_FAILED"}]
    assert "SOURCE_UNCHECKED" in codes(engine, run)


def test_document_only_and_paper_only_scopes_are_separate(engine):
    doc = document(engine)
    by_document = start(engine, document_ids=[doc["document_id"]])
    by_paper = start(engine, key="lint-paper-only", paper_ids=["paper"])
    with Session(engine) as session:
        assert {t["type"] for t in session.get(LintRun, by_document["id"]).targets} == {
            "document",
            "document_version",
            "passage",
        }
        assert "document" not in {t["type"] for t in session.get(LintRun, by_paper["id"]).targets}
    with pytest.raises(KnowledgeError, match="不属于当前项目"):
        start(engine, key="lint-wrong-scope", paper_ids=["missing"])


def test_passage_own_hash_and_explicit_stale_marker_are_diagnosed(engine):
    view = save(engine, draft(engine))
    changed = patch(
        engine,
        view,
        [
            {
                "op": "mark_stale",
                "section_id": view["sections"][0]["section_id"],
                "reason": "Needs update",
            }
        ],
    )
    run = scan(engine, document_ids=[view["page_id"]])
    assert "DEPENDENCY_STALE" in codes(engine, run)
    with Session(engine) as session, session.begin():
        session.get(QueryPassage, changed["sections"][1]["passage_id"]).text = "Tampered body."
    invalid = scan(engine, key="lint-tampered-body", document_ids=[view["page_id"]])
    assert "DEPENDENCY_INVALID" in codes(engine, invalid)


def test_private_markdown_requires_opt_in_never_writes_and_revoke_hides_report(engine, tmp_path):
    with Session(engine) as session, session.begin():
        root, _, path = add_note(session, tmp_path)
        root_id = root.id
    path.write_text("Personal viewpoint [[missing-note]].", encoding="utf-8")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    normal = scan(engine)
    assert not {"NOTE_UNTRACKED", "NOTE_CHANGED", "LINK_BROKEN"} & codes(engine, normal)
    personal = scan(engine, key="lint-personal", include_personal=True)
    assert {"NOTE_UNTRACKED", "NOTE_CHANGED", "LINK_BROKEN"} <= codes(engine, personal)
    assert not any(
        i["severity"] == "error" for i in issues(engine, personal) if i["object_type"] == "note"
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    with Session(engine) as session, session.begin():
        from researchgraph.knowledge_models import AuthorizedRoot

        session.get(AuthorizedRoot, root_id).active = False
    assert not [i for i in issues(engine, personal) if i["object_type"] == "note"]


def test_p5_managed_files_scan_identity_reference_and_sync_separately(engine, tmp_path):
    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    assert (
        WikiPublisher(engine).publish("p", view["page_id"], command, "publish-lint")["state"]
        == "succeeded"
    )
    clean = scan(engine, document_ids=[view["page_id"]])
    assert codes(engine, clean) == set()
    target.write_text("Externally edited [broken](#missing-reference).", encoding="utf-8")
    changed_bytes = target.read_bytes()
    modified = scan(engine, key="lint-file-modified", document_ids=[view["page_id"]])
    assert {"FILE_MODIFIED", "MANAGED_IDENTITY_INVALID", "LINK_BROKEN"} <= codes(engine, modified)
    assert not {"DEPENDENCY_STALE", "DEPENDENCY_INVALID"} & codes(engine, modified)
    assert target.read_bytes() == changed_bytes
    target.unlink()
    missing = scan(engine, key="lint-file-missing", document_ids=[view["page_id"]])
    assert "FILE_MISSING" in codes(engine, missing)
    assert not {"DEPENDENCY_STALE", "DEPENDENCY_INVALID"} & codes(engine, missing)


def test_file_change_between_advances_stales_p5_scan(engine, tmp_path):
    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    WikiPublisher(engine).publish("p", view["page_id"], command, "publish-lint-stale")
    run = start(engine, document_ids=[view["page_id"]])
    target.write_text("Externally edited after freeze.", encoding="utf-8")
    assert step(engine, run)["status"] == "input_stale"


def test_dependency_transitive_impact_layout_ignored_rebuild_recovers_missed_events(engine):
    first = document(engine)
    with Session(engine) as session:
        passage = session.get(QueryPassage, first["passage_ids"][0])
        child_dep = {"type": "passage", "id": passage.id, "sha256": passage.sha256}
    second_request = document_request(title="Dependent document")
    second_request["passages"][0]["dependencies"] = [child_dep]
    with Session(engine) as session, session.begin():
        second = KnowledgeStore(session).query().save_document(second_request, "save-dependent")
    rebuild(engine)
    with Session(engine) as session:
        result = dependencies(session, "p", object_type="chunk", object_id="c", page_size=100)
        impacted = {r["dependent_id"] for r in result["items"] if r["dependent_type"] == "passage"}
        assert impacted == set(first["passage_ids"] + second["passage_ids"])
        assert result["pending_events"] is False
        cursor_objects = dict(session.get(DependencyCursor, "p").objects)
    with Session(engine) as session, session.begin():
        session.add(
            GraphLayout(project_id="p", view_id="main", version=1, data={"x": 10}, updated_at="now")
        )
    unchanged = rebuild(engine, "rebuild-after-layout")
    assert unchanged["changes"] == []
    with Session(engine) as session:
        assert session.get(DependencyCursor, "p").objects == cursor_objects
    with Session(engine) as session, session.begin():
        # Missed/legacy event must still be recovered by deterministic reconciliation.
        session.get(Chunk, "c").text = "Changed without an Event."
    repaired = rebuild(engine, "rebuild-missed-event")
    assert any(c["object_type"] == "chunk" and c["object_id"] == "c" for c in repaired["changes"])
    with Session(engine) as session:
        edges = dependencies(session, "p", object_type="chunk", object_id="c", page_size=100)
        assert all(
            r["state"] == "invalid" for r in edges["items"] if r["dependent_type"] == "passage"
        )
        assert session.get(GraphRevision, "p") is None


def test_reverse_index_cycle_terminates_without_duplicate_edges(engine):
    document(engine)
    rebuild(engine)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                DependencyIndex(
                    id="cycle-a",
                    project_id="p",
                    dependent_type="passage",
                    dependent_id="a",
                    source_type="passage",
                    source_id="b",
                    role="citation",
                    category="evidence",
                    expected={},
                    state="invalid",
                ),
                DependencyIndex(
                    id="cycle-b",
                    project_id="p",
                    dependent_type="passage",
                    dependent_id="b",
                    source_type="passage",
                    source_id="a",
                    role="citation",
                    category="evidence",
                    expected={},
                    state="invalid",
                ),
            ]
        )
    with Session(engine) as session:
        result = dependencies(session, "p", object_type="passage", object_id="a", page_size=100)
        assert result["total"] == 2
        assert len({r["id"] for r in result["items"]}) == 2


@pytest.mark.parametrize(
    "state,expected",
    [
        ("known", None),
        ("not_applicable", None),
        ("unknown", "CONDITION_UNKNOWN"),
        ("conflicting", "CONDITION_CONFLICTING"),
        ("invented", "CONDITION_STATE_INVALID"),
    ],
)
def test_condition_states_are_gaps_not_invented_semantic_contradictions(seeded, state, expected):
    from test_query_graph import production

    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session, session.begin():
        condition = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "condition"))
        condition.known_state = state
    run = scan(engine, project_id="project")
    found = codes(engine, run) & {
        "CONDITION_UNKNOWN",
        "CONDITION_CONFLICTING",
        "CONDITION_STATE_INVALID",
    }
    assert found == ({expected} if expected else set())
    assert run["status"] == "completed"
    if state == "unknown":
        item = next(item for item in issues(engine, run) if item["code"] == "CONDITION_UNKNOWN")
        plan = item["repair_plan"]
        assert plan["status"] == "informational"
        assert [step["action"] for step in plan["steps"]] == [
            "inspect_source",
            "prepare_rebuild",
            "recheck_lint",
        ]
        assert plan["steps"][1]["requires_model"] is None
        assert "不把 unknown 推断为 conflicting，也不补造实验条件。" in plan["safeguards"]
    with Session(engine) as session:
        assert (
            session.scalar(
                select(KnowledgeNode.known_state).where(KnowledgeNode.kind == "condition")
            )
            == state
        )


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("node_evidence", "NODE_EVIDENCE_MISSING"),
        ("relation", "RELATION_BROKEN"),
        ("support", "SUPPORT_PATH_INVALID"),
        ("selection", "SELECTION_INVALID"),
    ],
)
def test_graph_rules_check_authoritative_support_not_canvas(seeded, fault, expected):
    import asyncio
    import copy

    from researchgraph.graph_models import SourceAssertion
    from researchgraph.knowledge_models import NodeEvidence
    from researchgraph.providers import MockProvider
    from researchgraph.reading_models import ReadingSelection
    from researchgraph.reading_pipeline import finish_reading
    from sqlalchemy import delete
    from test_query_graph import production
    from test_reading_selection import setup_job

    _, engine, eid = seeded
    ids = production(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    clean = scan(engine, project_id="project")
    assert clean["status"] == "completed"
    assert not {
        "NODE_EVIDENCE_MISSING",
        "RELATION_BROKEN",
        "SUPPORT_PATH_INVALID",
        "SELECTION_INVALID",
    } & codes(engine, clean)
    with Session(engine) as session, session.begin():
        if fault == "node_evidence":
            session.execute(delete(NodeEvidence).where(NodeEvidence.node_id == ids["m"]))
        elif fault == "relation":
            edge = session.scalar(
                select(SourceAssertion).where(SourceAssertion.target_id == ids["m"])
            )
            edge.relation = "NO_DECISION"
        elif fault == "support":
            session.execute(delete(SourceAssertion).where(SourceAssertion.target_id == ids["m"]))
        else:
            selected = session.scalar(select(ReadingSelection))
            data = copy.deepcopy(selected.data)
            data["units"][0]["id"] = "missing-unit"
            selected.data = data
    broken = scan(engine, key="lint-broken-graph", project_id="project")
    assert broken["status"] == "completed" and expected in codes(engine, broken)


def test_maintenance_is_opt_in_and_unchanged_inputs_create_no_report(engine):
    from researchgraph.lint_maintenance import reconcile_pending
    from researchgraph.models import Event

    with Session(engine) as session:
        before = len(list(session.scalars(select(Event))))
    reconcile_pending(engine)
    with Session(engine) as session:
        assert len(list(session.scalars(select(Event)))) == before
        assert list(session.scalars(select(LintRun))) == []
    baseline = scan(engine)
    assert baseline["status"] == "completed"
    with Session(engine) as session:
        assert session.get(DependencyCursor, "p") is not None
    reconcile_pending(engine)
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).audit_event("p", "UNRELATED_EXECUTION", {})
    reconcile_pending(engine)
    with Session(engine) as session:
        assert len(list(session.scalars(select(LintRun)))) == 1
        assert dependencies(session, "p")["pending_events"] is False


@pytest.mark.parametrize("mode", ["lite", "legacy"])
@pytest.mark.parametrize("trigger", ["event", "interval"])
def test_automatic_maintenance_excludes_lite_cursors(engine, monkeypatch, mode, trigger):
    from researchgraph import lint_maintenance
    from researchgraph.models import Project

    baseline = scan(engine)
    assert baseline["status"] == "completed"
    with Session(engine) as session, session.begin():
        assert session.get(DependencyCursor, "p") is not None
        session.get(Project, "p").experience_mode = mode
        if trigger == "event":
            KnowledgeStore(session).audit_event("p", "UNRELATED_EXECUTION", {})
    monkeypatch.setattr(lint_maintenance.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        lint_maintenance,
        "_last_attempt",
        {(str(engine.url), "p"): 99.0 if trigger == "event" else 0.0},
    )
    calls = []

    def reconcile(_self, project_id, *, max_items):
        calls.append((project_id, max_items))

    monkeypatch.setattr(lint_maintenance.LintStore, "reconcile", reconcile)
    lint_maintenance.reconcile_pending(engine)
    assert calls == ([] if mode == "lite" else [("p", 25)])


def test_automatic_incremental_only_checks_impacted_subset_and_preserves_full_lifecycle(engine):
    from researchgraph.knowledge_store import text_hash
    from researchgraph.query_models import QueryDocument

    first = document(engine)
    with Session(engine) as session, session.begin():
        session.add(
            Chunk(
                id="independent",
                revision_id="v",
                page_index=0,
                page_label="1",
                block_index=1,
                text="Independent source.",
                bbox=[0, 0, 100, 50],
            )
        )
        session.flush()
        body = document_request(title="Independent document")
        body["passages"][0]["dependencies"] = [
            {
                "type": "chunk",
                "id": "independent",
                "sha256": text_hash("Independent source."),
                "start": 0,
                "end": len("Independent source."),
                "quote": "Independent source.",
            }
        ]
        second = KnowledgeStore(session).query().save_document(body, "save-independent")
    full = scan(engine)
    with Session(engine) as session, session.begin():
        session.get(Chunk, "c").text = "Changed synthetic source."
        KnowledgeStore(session).event("p", "SOURCE_CHANGED", {"chunk_id": "c"})
    with Session(engine) as session, session.begin():
        incremental = LintStore(KnowledgeStore(session)).reconcile("p", max_items=1)
    assert incremental["scope"]["incremental"] is True
    assert incremental["total"] < full["total"] and incremental["processed"] == 1
    engine.dispose()
    while incremental["status"] in {"queued", "running"}:
        with Session(engine) as session, session.begin():
            incremental = LintStore(KnowledgeStore(session)).reconcile("p", max_items=1)
    assert incremental["status"] == "completed" and incremental["previous_run_id"] is None
    assert incremental["diff"]["resolved"] == 0
    with Session(engine) as session:
        row = session.get(LintRun, incremental["id"])
        checked_passages = {t["id"] for t in row.targets if t["type"] == "passage"}
        assert checked_passages == set(first["passage_ids"])
        assert not checked_passages & set(second["passage_ids"])
        assert (
            session.get(QueryDocument, second["document_id"]).current_version_id
            == second["version_id"]
        )
        assert get_run(session, "p", full["id"])["status"] == "completed"
    assert "DEPENDENCY_INVALID" in codes(engine, incremental)


def test_explicit_rebuild_repairs_index_even_when_source_inputs_are_unchanged(engine):
    from sqlalchemy import delete

    document(engine)
    rebuilt = rebuild(engine)
    assert rebuilt["edge_count"] > 0
    with Session(engine) as session, session.begin():
        session.execute(delete(DependencyIndex).where(DependencyIndex.project_id == "p"))
    fixed = rebuild(engine, "repair-derived-index")
    assert fixed["changes"] == [] and fixed["edge_count"] == rebuilt["edge_count"]
    with Session(engine) as session:
        assert dependencies(session, "p")["total"] == fixed["edge_count"]


def test_unsaved_wiki_draft_dependency_impact_reaches_its_page(engine):
    view = draft(engine)
    rebuild(engine)
    with Session(engine) as session:
        impacted = dependencies(session, "p", object_type="chunk", object_id="c", page_size=100)
        assert {
            r["dependent_id"] for r in impacted["items"] if r["dependent_type"] == "document"
        } == {view["page_id"]}


def test_running_worker_creates_deterministic_incremental_report_without_model_job(
    engine, tmp_path
):
    import time

    from researchgraph.models import Job
    from test_engine import client

    document(engine)
    scan(engine)
    with client(tmp_path / "data", worker=True):
        with Session(engine) as session, session.begin():
            session.get(Chunk, "c").text = "Synthetic source changed while worker runs."
            KnowledgeStore(session).event("p", "SOURCE_CHANGED", {"chunk_id": "c"})
        deadline = time.monotonic() + 6
        report = None
        while time.monotonic() < deadline:
            with Session(engine) as session:
                report = next(
                    (
                        r
                        for r in session.scalars(select(LintRun))
                        if r.scope.get("incremental") and r.status == "completed"
                    ),
                    None,
                )
            if report:
                break
            time.sleep(0.05)
        assert report is not None, "worker did not consume the deterministic dependency change"
        assert report.scope["incremental"] is True
    with Session(engine) as session:
        assert list(session.scalars(select(Job))) == []


@pytest.mark.parametrize(
    "change,expected",
    [("support", "SUPPORT_CONTEXT_CHANGED"), ("selection", "ORGANIZATION_CHANGED")],
)
def test_incremental_support_and_organization_reach_node_citing_passages(seeded, change, expected):
    import asyncio
    import copy

    from researchgraph.graph_models import SourceAssertion
    from researchgraph.knowledge_store import digest, text_hash
    from researchgraph.providers import MockProvider
    from researchgraph.reading_models import ReadingSelection
    from researchgraph.reading_pipeline import finish_reading
    from sqlalchemy import delete
    from test_query_graph import production
    from test_reading_selection import setup_job

    _, engine, eid = seeded
    ids = production(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        root = session.get(KnowledgeNode, ids["c"])
        doc = (
            KnowledgeStore(session)
            .query()
            .save_document(
                {
                    "project_id": "project",
                    "title": "Node-dependent reading",
                    "kind": "wiki",
                    "passages": [
                        {
                            "local_ref": "one",
                            "text": "Bounded reading interpretation.",
                            "attribution": "model_synthesis",
                            "dependencies": [
                                {
                                    "type": "node",
                                    "id": root.id,
                                    "revision": root.revision,
                                    "sha256": text_hash(root.text),
                                    "payload_sha256": digest(root.payload),
                                }
                            ],
                        }
                    ],
                },
                "node-citing-document",
            )
        )
    scan(engine, project_id="project")
    with Session(engine) as session, session.begin():
        if change == "support":
            session.execute(delete(SourceAssertion).where(SourceAssertion.target_id == ids["m"]))
        else:
            selection = session.scalar(select(ReadingSelection))
            selection.data = {**copy.deepcopy(selection.data), "density": "detailed"}
        KnowledgeStore(session).event("project", "SYNTHETIC_CHANGE", {"kind": change})
    with Session(engine) as session, session.begin():
        report = LintStore(KnowledgeStore(session)).reconcile("project", max_items=100)
    assert report["status"] == "completed"
    located = [i for i in issues(engine, report) if i["code"] == expected]
    assert {i["object_id"] for i in located} == set(doc["passage_ids"])
    if change == "selection":
        assert not {"DEPENDENCY_INVALID", "DEPENDENCY_STALE"} & codes(engine, report)
