"""P5 model workflows: isolated synthetic data and explicit test-only provider."""

import asyncio
import json

import pytest
import test_knowledge
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.models import Chunk, Job
from researchgraph.p5_contracts import WorkflowPrepare
from researchgraph.p5_execution import execute
from researchgraph.p5_models import P5ModelRun, P5Workflow
from researchgraph.p5_transport import load_prompt, output_schema
from researchgraph.p5_workflows import enqueue, materialize, prepare, validate_workflow, view
from researchgraph.providers import ProviderError
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_query_answers import configure
from test_query_graph import production, second_paper
from test_query_retrieval import request, science_rows

seeded = test_knowledge.seeded


def prepared(engine, *, kind="wiki_synthesis", **kwargs):
    body = WorkflowPrepare(
        kind=kind, query=request("任意中文主题，没有英文词面命中", purpose="model"), **kwargs
    )
    with Session(engine) as session, session.begin():
        row = prepare(session, "project", body, "prepare-p5-test-" + kind)
        assert row.status == "prepared", row.snapshot["context"]
        return row.id


def dispatch(engine, wid, *, key=None, continuing=False):
    with Session(engine) as session, session.begin():
        return enqueue(
            session,
            session.get(P5Workflow, wid),
            key or "p5-attempt-" + wid,
            continue_requested=continuing,
        ).id


def run(engine, jid, provider):
    with Session(engine) as session, session.begin():
        session.get(Job, jid).status = "running"
    asyncio.run(execute(engine, jid, testing_provider=provider))


def read(engine, wid):
    with Session(engine) as session:
        return view(session, session.get(P5Workflow, wid))


class Provider:
    name, model, total_timeout = "compatible", "isolated-p5", 1
    usage = {"total_tokens": 71}
    request_metadata = {"finish_reason": "stop"}
    partial_output = None
    key = ""

    def __init__(self, engine, *, output=None, error=None, action=None):
        self.engine, self.output, self.error, self.action = engine, output, error, action
        self.calls = 0

    async def complete(self, prompt, data, schema):
        self.calls += 1
        with Session(self.engine) as session:
            ledger = session.scalar(select(P5ModelRun).order_by(P5ModelRun.created_at.desc()))
            assert (
                ledger.status == "running"
                and ledger.parameters["dispatch_policy"] == "persist-before-io-no-resend-1"
            )
        context = data["evidence_context"]
        direct = next(r for r in context["references"] if r["type"] == "chunk")
        assert (
            schema == output_schema("wiki_synthesis", context, [])
            or "affected_sections" in data
            or "deterministic_diagnostics" in data
        )
        if self.action:
            self.action()
        if self.error:
            raise self.error
        passage = {
            "heading": "关键结论",
            "text": "作者报告在所述实验条件下观察到改善。",
            "attribution": "model_synthesis",
            "source_refs": [direct["ref"]],
            "limitations": ["不外推至其他条件"],
            "conditions": [
                {"dimension": "实验条件", "state": "unknown", "value": None, "unit": None}
            ],
        }
        if self.output is not None:
            return self.output(data, passage) if callable(self.output) else self.output
        return json.dumps(
            {"title": "论文阅读整理", "passages": [passage], "coverage_gaps": ["未验证语义正确性"]},
            ensure_ascii=False,
        )


@pytest.fixture
def ready(seeded):
    api, engine, eid = seeded
    production(engine, eid)
    configure(engine)
    return api, engine, prepared(engine)


def test_synthesis_whole_scope_ledger_materialize_save_restart_and_science_unchanged(ready):
    api, engine, wid = ready
    with Session(engine) as session:
        before = science_rows(session)
    jid = dispatch(engine, wid)
    assert dispatch(engine, wid, key="parallel-attempt") == jid
    provider = Provider(engine)
    run(engine, jid, provider)
    result = read(engine, wid)
    assert result["status"] == "succeeded", result
    assert api.get(f"/api/v1/jobs/{jid}").json()["status"] == "succeeded"
    assert result["request_count"] == provider.calls == 1
    assert result["result"]["draft"]["passages"][0]["dependencies"]
    with Session(engine) as session, session.begin():
        draft = materialize(KnowledgeStore(session), "project", wid, "materialize-p5")
        again = materialize(KnowledgeStore(session), "project", wid, "materialize-again")
        assert (again["page_id"], again["version_id"]) == (draft["page_id"], draft["version_id"])
        assert science_rows(session) == before
    saved = api.post(
        f"/api/v1/projects/project/wiki/pages/{draft['page_id']}/save",
        json={
            "version_id": draft["version_id"],
            "expected_head_version_id": draft["version_id"],
            "expected_content_hash": draft["content_hash"],
        },
        headers={"Idempotency-Key": "save-p5-draft"},
    )
    assert saved.status_code == 200, saved.text
    saved_id = saved.json()["version_id"]
    assert saved_id != draft["version_id"]  # Saving creates an immutable saved snapshot.
    assert (
        api.get(f"/api/v1/projects/project/wiki/pages/{draft['page_id']}").json()[
            "saved_version_id"
        ]
        == saved_id
    )
    engine.dispose()
    assert read(engine, wid)["status"] == "succeeded"
    assert provider.calls == 1


@pytest.mark.parametrize(
    "output,code",
    [
        ("{broken", "P5_JSON_INVALID"),
        ('{"title":"x","passages":[],"coverage_gaps":[],"waiver":null}', "P5_SCHEMA_INVALID"),
        ('{"title":"x","title":"y","passages":[],"coverage_gaps":[]}', "P5_JSON_INVALID"),
        (
            lambda data, p: json.dumps(
                {"title": "x", "passages": [{**p, "source_refs": ["S99999"]}], "coverage_gaps": []}
            ),
            "QUERY_REFERENCE_UNKNOWN",
        ),
    ],
)
def test_bad_response_not_reused_and_explicit_slots_bounded(ready, output, code):
    _, engine, wid = ready
    jid = dispatch(engine, wid)
    provider = Provider(engine, output=output)
    run(engine, jid, provider)
    assert read(engine, wid)["error_code"] == code, read(engine, wid)
    run(engine, jid, provider)
    assert provider.calls == 1
    second = dispatch(engine, wid, key="explicit-second", continuing=True)
    assert second != jid
    run(engine, second, provider)
    assert provider.calls == 2
    with Session(engine) as session, session.begin(), pytest.raises(KnowledgeError, match="两次"):
        enqueue(session, session.get(P5Workflow, wid), "third-explicit", continue_requested=True)
    assert read(engine, wid)["result"] is None


def test_timeout_retains_ledger_no_auto_retry_and_can_continue(ready):
    _, engine, wid = ready
    provider = Provider(engine, error=ProviderError("timeout", "private raw failure"))
    run(engine, dispatch(engine, wid), provider)
    result = read(engine, wid)
    assert result["status"] == "failed" and result["can_continue"]
    assert "private" not in str(result)
    good = Provider(engine)
    run(engine, dispatch(engine, wid, key="timeout-continue", continuing=True), good)
    assert read(engine, wid)["status"] == "succeeded"
    assert good.calls == provider.calls == 1


def test_source_changed_during_io_does_not_publish_and_does_not_poison_raw(ready):
    _, engine, wid = ready

    def mutate():
        with Session(engine) as session, session.begin():
            session.get(Chunk, "paragraph").text += " source changed"

    provider = Provider(engine, action=mutate)
    run(engine, dispatch(engine, wid), provider)
    assert read(engine, wid)["status"] == "failed"
    with Session(engine) as session:
        record = session.scalar(select(P5ModelRun))
        assert record.raw_output and record.status == "received"
        assert "reuse_diagnostic" in record.parameters
    with Session(engine) as session, session.begin(), pytest.raises(KnowledgeError):
        enqueue(session, session.get(P5Workflow, wid), "changed-input", continue_requested=True)
    assert provider.calls == 1


def test_cancel_after_dispatch_no_result_or_hidden_retry(ready):
    _, engine, wid = ready
    jid = dispatch(engine, wid)

    def cancel():
        with Session(engine) as session, session.begin():
            session.get(Job, jid).status = "cancelled"

    provider = Provider(engine, action=cancel)
    run(engine, jid, provider)
    assert read(engine, wid)["status"] == "cancelled"
    assert provider.calls == 1


def test_provider_credential_echo_never_persisted(ready):
    _, engine, wid = ready
    provider = Provider(engine, output="test-secret-credential-echo")
    provider.key = "test-secret-credential-echo"
    run(engine, dispatch(engine, wid), provider)
    assert read(engine, wid)["error_code"] == "P5_CREDENTIAL_IN_OUTPUT"
    with Session(engine) as session:
        record = session.scalar(select(P5ModelRun))
        assert record.raw_output is None
        assert provider.key not in str(record.parameters)


def test_succeeded_response_raw_restore_zero_network(ready):
    _, engine, wid = ready
    first = Provider(engine)
    run(engine, dispatch(engine, wid), first)
    with Session(engine) as session, session.begin():
        workflow = session.get(P5Workflow, wid)
        workflow.status = "failed"
        session.get(Job, workflow.job_id).status = "failed"
        session.scalar(select(P5ModelRun)).status = "received"
    restore = Provider(engine, error=AssertionError("must not call"))
    run(engine, dispatch(engine, wid, key="restore-received", continuing=True), restore)
    assert read(engine, wid)["status"] == "succeeded" and restore.calls == 0


def test_two_selected_papers_complete_context_not_lexical_top_k(ready):
    _, engine, _ = ready
    second_paper(engine)
    body = WorkflowPrepare(
        kind="wiki_synthesis",
        query={
            **request("整理关键结论", purpose="model"),
            "paper_ids": ["paper", "paper2"],
            "limit": 1,
        },
    )
    with Session(engine) as session, session.begin():
        row = prepare(session, "project", body, "two-complete-papers")
        assert row.status == "prepared"
        assert {
            r.get("paper_id") for r in row.snapshot["context"]["references"] if r["type"] == "chunk"
        } == {"paper", "paper2"}
        assert len(row.snapshot["source_revisions"]) == 2


def test_prompt_and_deterministic_contract_match():
    for kind in ("lint_semantic", "wiki_synthesis", "wiki_delta"):
        assert "BEGIN GENERATED" in load_prompt(kind)


def lint_report(engine):
    from researchgraph.lint_contracts import LintRequest

    with Session(engine) as session, session.begin():
        lint = KnowledgeStore(session).lint()
        report = lint.start("project", LintRequest(), "p5-rules-report")
        step = 0
        while report["status"] in {"queued", "running"}:
            step += 1
            report = lint.advance("project", report["id"], 100, f"p5-rules-step-{step}")
        assert report["status"] in {"completed", "partial"}, report
        return report["id"]


def test_semantic_lint_is_suggestion_only_and_uses_frozen_rule_report(ready):
    _, engine, _ = ready
    report_id = lint_report(engine)
    wid = prepared(engine, kind="lint_semantic", lint_run_id=report_id)

    def suggestions(data, passage):
        assert data["deterministic_diagnostics"]["run_id"] == report_id
        assert all(
            "repair_plan" not in issue for issue in data["deterministic_diagnostics"]["issues"]
        )
        ref = passage["source_refs"][0]
        return json.dumps(
            {
                "issues": [
                    {
                        "code": "insufficient_context",
                        "severity": "warning",
                        "affected_refs": [ref],
                        "evidence_refs": [ref],
                        "rationale": "Different experimental conditions need comparison.",
                        "suggested_action": "Read the original conditions.",
                        "uncertainty": "This is not a verified contradiction.",
                    }
                ],
                "limitations": ["Synthetic semantic suggestion only."],
            }
        )

    with Session(engine) as session:
        before = science_rows(session)
    provider = Provider(engine, output=suggestions)
    run(engine, dispatch(engine, wid), provider)
    outcome = read(engine, wid)
    assert outcome["status"] == "succeeded", outcome
    assert outcome["result"]["suggestions"][0]["kind"] == "model_suggestion"
    with Session(engine) as session, session.begin():
        assert science_rows(session) == before
        with pytest.raises(KnowledgeError, match="建议"):
            materialize(KnowledgeStore(session), "project", wid, "no-lint-actions")
        cached = prepare(
            session,
            "project",
            WorkflowPrepare.model_validate(session.get(P5Workflow, wid).request),
            "same-lint-input",
        )
        assert cached.id == wid
    assert dispatch(engine, wid, key="same-lint-generate") == outcome["job_id"]
    assert provider.calls == 1


def test_current_repair_guidance_preserves_legacy_p09_snapshot_and_raw(ready, monkeypatch):
    from researchgraph import lint_service

    api, engine, _ = ready
    report_id = lint_report(engine)
    current_issue_view = lint_service.issue_view

    def legacy_issue_view(row):
        return {
            key: value for key, value in current_issue_view(row).items() if key != "repair_plan"
        }

    # Prepare exactly the pre-presentation shape, without rewriting any frozen row.
    with monkeypatch.context() as legacy:
        legacy.setattr(lint_service, "issue_view", legacy_issue_view)
        wid = prepared(engine, kind="lint_semantic", lint_run_id=report_id)
    with Session(engine) as session:
        workflow = session.get(P5Workflow, wid)
        frozen = json.dumps(workflow.snapshot, sort_keys=True)
        input_hash, wire_hash = workflow.input_hash, workflow.snapshot["wire_hash"]
        assert workflow.snapshot["lint"]["issues"]
        assert all("repair_plan" not in issue for issue in workflow.snapshot["lint"]["issues"])
        science_before = science_rows(session)

    original_plan = lint_service._repair_plan

    def updated_plan(*args, **kwargs):
        return {**original_plan(*args, **kwargs), "summary": "Current read-only handling guidance."}

    monkeypatch.setattr(lint_service, "_repair_plan", updated_plan)
    response = api.get(f"/api/v1/projects/project/lint/runs/{report_id}/issues")
    assert response.status_code == 200, response.text
    assert all(
        issue["repair_plan"]["summary"] == "Current read-only handling guidance."
        for issue in response.json()["items"]
    )
    with Session(engine) as session, session.begin():
        workflow = session.get(P5Workflow, wid)
        validate_workflow(session, workflow)
        cached = prepare(
            session,
            "project",
            WorkflowPrepare.model_validate(workflow.request),
            "legacy-lint-cached",
        )
        assert cached.id == wid
    assert read(engine, wid)["status"] == "prepared"

    def suggestions(data, _passage):
        assert all(
            "repair_plan" not in issue for issue in data["deterministic_diagnostics"]["issues"]
        )
        return json.dumps({"issues": [], "limitations": ["Synthetic compatibility check."]})

    provider = Provider(engine, output=suggestions)
    run(engine, dispatch(engine, wid), provider)
    assert read(engine, wid)["status"] == "succeeded"
    with Session(engine) as session:
        workflow = session.get(P5Workflow, wid)
        validate_workflow(session, workflow)
        assert json.dumps(workflow.snapshot, sort_keys=True) == frozen
        assert (workflow.input_hash, workflow.snapshot["wire_hash"]) == (input_hash, wire_hash)
        recorded = session.scalar(select(P5ModelRun).where(P5ModelRun.workflow_id == wid))
        original_raw = (recorded.raw_output, recorded.parameters["raw_sha256"])
        assert recorded.input_hash == wire_hash
        assert science_rows(session) == science_before
    assert dispatch(engine, wid, key="legacy-lint-do-not-regenerate") == read(engine, wid)["job_id"]
    engine.dispose()
    assert read(engine, wid)["status"] == "succeeded"
    with Session(engine) as session:
        recorded = session.scalar(select(P5ModelRun).where(P5ModelRun.workflow_id == wid))
        assert (recorded.raw_output, recorded.parameters["raw_sha256"]) == original_raw
    assert provider.calls == 1


def test_semantic_lint_requires_report_and_identical_personal_scope(ready):
    from pydantic import ValidationError

    _, engine, _ = ready
    with pytest.raises(ValidationError):
        WorkflowPrepare(kind="lint_semantic", query=request("Inspect", purpose="model"))
    report_id = lint_report(engine)
    body = WorkflowPrepare(
        kind="lint_semantic",
        lint_run_id=report_id,
        query=request("Inspect", purpose="model", include_personal=True),
    )
    with (
        Session(engine) as session,
        session.begin(),
        pytest.raises(KnowledgeError, match="相同论文"),
    ):
        prepare(session, "project", body, "mismatched-personal-scope")


def delta_workflow(engine, draft):
    return prepared(
        engine,
        kind="wiki_delta",
        page_id=draft["page_id"],
        base_version_id=draft["version_id"],
        affected_section_ids=[draft["sections"][0]["section_id"]],
    )


def synthesis_page(engine, wid):
    run(engine, dispatch(engine, wid), Provider(engine))
    with Session(engine) as session, session.begin():
        return materialize(KnowledgeStore(session), "project", wid, "p5-base-page")


def test_delta_only_updates_selected_sections_and_retains_baseline(ready):
    _, engine, wid = ready
    draft = synthesis_page(engine, wid)
    delta_id = delta_workflow(engine, draft)

    def changes(data, passage):
        assert len(data["affected_sections"]) == 1
        target = data["affected_sections"][0]["section_ref"]
        return json.dumps(
            {
                "edits": [
                    {
                        "op": "replace",
                        "section_ref": target,
                        "passage": {
                            **passage,
                            "text": "An updated interpretation with explicit limits.",
                        },
                    },
                    {"op": "append", "after_section_ref": target, "passage": passage},
                ],
                "coverage_gaps": [],
            }
        )

    run(engine, dispatch(engine, delta_id), Provider(engine, output=changes))
    outcome = read(engine, delta_id)
    assert outcome["status"] == "succeeded", outcome
    with Session(engine) as session, session.begin():
        updated = materialize(KnowledgeStore(session), "project", delta_id, "p5-delta-save")
        assert updated["page_id"] == draft["page_id"]
        assert updated["version_id"] != draft["version_id"]
        assert len(updated["sections"]) == 2
        assert updated["sections"][0]["section_id"] == draft["sections"][0]["section_id"]
        assert "updated interpretation" in updated["diff"]
        from researchgraph.wiki_store import read_page

        original = read_page(session, "project", draft["page_id"], draft["version_id"])
        assert original["markdown"] == draft["markdown"]


def test_delta_rejects_out_of_scope_target_and_base_competition(ready):
    _, engine, wid = ready
    draft = synthesis_page(engine, wid)
    delta_id = delta_workflow(engine, draft)
    provider = Provider(
        engine,
        output=json.dumps(
            {
                "edits": [
                    {"op": "mark_stale", "section_ref": "T99999", "reason": "Unknown target"}
                ],
                "coverage_gaps": [],
            }
        ),
    )
    run(engine, dispatch(engine, delta_id), provider)
    assert read(engine, delta_id)["error_code"] == "P5_DELTA_SCOPE_INVALID"
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).wiki().apply_patch(
            "project",
            draft["page_id"],
            {
                "base_version_id": draft["version_id"],
                "base_content_hash": draft["content_hash"],
                "operations": [
                    {
                        "op": "mark_stale",
                        "section_id": draft["sections"][0]["section_id"],
                        "reason": "Needs new source verification",
                    }
                ],
            },
            "competing-draft",
        )
    with pytest.raises(KnowledgeError, match="基线"):
        dispatch(engine, delta_id, key="competing-continue", continuing=True)
    assert provider.calls == 1


def test_two_slots_can_restore_received_response_without_credentials_or_network(ready, monkeypatch):
    _, engine, wid = ready
    run(engine, dispatch(engine, wid), Provider(engine, output="{bad"))
    run(engine, dispatch(engine, wid, key="valid-second-slot", continuing=True), Provider(engine))
    with Session(engine) as session, session.begin():
        workflow = session.get(P5Workflow, wid)
        workflow.status = "failed"
        session.get(Job, workflow.job_id).status = "failed"
        session.scalar(
            select(P5ModelRun).where(P5ModelRun.status == "succeeded")
        ).status = "received"
    assert read(engine, wid)["can_continue"]
    job_id = dispatch(engine, wid, key="recovery-after-two", continuing=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery must finish before reading credentials")

    monkeypatch.setattr("researchgraph.p5_execution.from_snapshot", forbidden)
    with Session(engine) as session, session.begin():
        session.get(Job, job_id).status = "running"
    asyncio.run(execute(engine, job_id))
    result = read(engine, wid)
    assert result["status"] == "succeeded", result
    assert result["request_count"] == 2


def test_corrupt_stored_raw_blocks_continuation_instead_of_spending_new_slot(ready):
    _, engine, wid = ready
    provider = Provider(engine)
    run(engine, dispatch(engine, wid), provider)
    with Session(engine) as session, session.begin():
        row = session.get(P5Workflow, wid)
        row.status = "failed"
        session.get(Job, row.job_id).status = "failed"
        record = session.scalar(select(P5ModelRun))
        record.raw_output += " "
    with pytest.raises(KnowledgeError, match="冻结请求"):
        dispatch(engine, wid, key="corrupt-raw-continue", continuing=True)
    assert provider.calls == 1
    assert not read(engine, wid)["can_continue"]


def test_workflow_api_is_project_scoped_and_requires_explicit_network_purpose(ready):
    api, engine, wid = ready
    with Session(engine) as session, session.begin():
        from researchgraph.models import Project, now

        session.add(
            Project(id="other", name="Other synthetic project", description="", created_at=now())
        )
    assert api.get(f"/api/v1/projects/other/workflows/{wid}").status_code == 404
    response = api.post(
        f"/api/v1/projects/project/workflows/{wid}/generate",
        json={"allow_network": False},
        headers={"Idempotency-Key": "no-network-consent"},
    )
    assert response.status_code == 422
    assert read(engine, wid)["request_count"] == 0
    with Session(engine) as session:
        assert session.get(P5Workflow, wid).job_id is None


def test_paper_titles_alone_are_insufficient_and_never_enqueue(ready):
    _, engine, _ = ready
    with Session(engine) as session, session.begin():
        body = WorkflowPrepare(
            kind="wiki_synthesis",
            query=request("Summarize", purpose="model", source_kinds=["paper"]),
        )
        row = prepare(session, "project", body, "titles-without-evidence")
        assert row.status == "insufficient"
        with pytest.raises(KnowledgeError, match="缺少证据"):
            enqueue(session, row, "no-evidence-generate", continue_requested=False)
        assert not runs_in_session(session, row.id)


def runs_in_session(session, workflow_id):
    return list(session.scalars(select(P5ModelRun).where(P5ModelRun.workflow_id == workflow_id)))


def test_delta_baseline_is_not_its_own_evidence_after_saved_update(ready):
    from researchgraph.wiki_store import read_page

    _, engine, wid = ready
    draft = synthesis_page(engine, wid)
    with Session(engine) as session, session.begin():
        saved = (
            KnowledgeStore(session)
            .wiki()
            .save_draft(
                "project",
                draft["page_id"],
                {
                    "version_id": draft["version_id"],
                    "expected_head_version_id": draft["version_id"],
                    "expected_content_hash": draft["content_hash"],
                },
                "baseline-save-before-update",
            )
        )
        baseline = read_page(session, "project", saved["page_id"])
    delta_id = delta_workflow(engine, baseline)
    with Session(engine) as session:
        refs = session.get(P5Workflow, delta_id).snapshot["context"]["references"]
        assert not any(r.get("document_id") == baseline["page_id"] for r in refs)

    def update(data, passage):
        return json.dumps(
            {
                "edits": [
                    {
                        "op": "replace",
                        "section_ref": data["affected_sections"][0]["section_ref"],
                        "passage": {
                            **passage,
                            "text": "A revised reading of the original evidence.",
                        },
                    }
                ],
                "coverage_gaps": [],
            }
        )

    run(engine, dispatch(engine, delta_id), Provider(engine, output=update))
    with Session(engine) as session, session.begin():
        changed = materialize(KnowledgeStore(session), "project", delta_id, "delta-materialize")
        KnowledgeStore(session).wiki().save_draft(
            "project",
            changed["page_id"],
            {
                "version_id": changed["version_id"],
                "expected_head_version_id": changed["version_id"],
                "expected_content_hash": changed["content_hash"],
            },
            "delta-explicit-save",
        )
    assert read(engine, delta_id)["status"] == "succeeded", read(engine, delta_id)
    engine.dispose()
    assert read(engine, delta_id)["status"] == "succeeded"
