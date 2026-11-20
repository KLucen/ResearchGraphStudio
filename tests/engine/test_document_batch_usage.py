"""Batch-ledger usage is scoped, read-only, restart-stable and never free by default."""

from uuid import uuid4

import pytest
from researchgraph.document_batch_models import LlmDocumentBatch, LlmDocumentBatchRun
from researchgraph.import_plan_models import ImportSession
from researchgraph.lite_models import LiteTokenUsage
from researchgraph.lite_usage import aggregate_usage, record_usage
from researchgraph.models import AttachmentRevision, Job, Paper, Project, now
from researchgraph.storage import read_session
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine import client


def _request(purpose="extract", *, status="received", tokens=None):
    return {
        "purpose": purpose,
        "status": status,
        "usage_source": "provider" if tokens else "unknown",
        "usage": tokens or {},
        "started_at": now(),
    }


def _seed(db: Session, requests, *, project_id=None, request_count=None, repair_attempts=None):
    project_id = project_id or str(uuid4())
    paper_id, session_id, job_id, run_id, batch_id = (str(uuid4()) for _ in range(5))
    timestamp = now()
    if db.get(Project, project_id) is None:
        db.add(Project(id=project_id, name="Anonymous", description="", created_at=timestamp))
        db.flush()
    db.add(Paper(id=paper_id, project_id=project_id, title="Model-only", created_at=timestamp))
    db.add(
        Job(
            id=job_id,
            kind="llm_document_parse",
            project_id=project_id,
            payload={
                "paper_id": paper_id,
                "import_session_id": session_id,
                "provider_snapshot": {
                    "provider": "compatible",
                    "model": "anonymous-model",
                    "credential_ref": "private-reference-not-for-output",
                },
            },
            status="running",
            stage="document_batching",
            attempt=1,
            result={},
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    db.add(
        ImportSession(
            id=session_id,
            project_id=project_id,
            source_kind="pdf",
            selection_id=str(uuid4()),
            source_snapshot={"paper_id": paper_id},
            plan={"document_batching": True},
            status="running",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    db.flush()
    db.add(
        LlmDocumentBatchRun(
            id=run_id,
            import_session_id=session_id,
            job_id=job_id,
            source_version={"size": 100, "mtime_ns": 1, "page_count": 2},
            settings={"request_budget": 3},
            page_count=2,
            status="running",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    db.flush()
    count = (
        sum(entry.get("status") != "not_sent" for entry in requests)
        if request_count is None
        else request_count
    )
    repairs = (
        int(any(entry.get("purpose") == "repair" for entry in requests))
        if repair_attempts is None
        else repair_attempts
    )
    db.add(
        LlmDocumentBatch(
            id=batch_id,
            run_id=run_id,
            ordinal=0,
            kind="extract",
            page_start=1,
            page_end=2,
            send_start=1,
            send_end=2,
            status="sent" if count else "pending",
            attempts=int(count > 0),
            repair_attempts=repairs,
            request_count=count,
            usage={"requests": requests},
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    db.flush()
    return {
        "project": project_id,
        "paper": paper_id,
        "job": job_id,
        "run": run_id,
        "batch": batch_id,
    }


def test_model_only_batch_requests_appear_in_global_project_and_paper_usage(tmp_path):
    with client(tmp_path) as api:
        with Session(api.app.state.engine) as db, db.begin():
            ids = _seed(
                db,
                [
                    _request(
                        tokens={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
                    ),
                    _request("repair", tokens={"prompt_tokens": 25, "completion_tokens": 5}),
                    _request("boundary", status="uncertain"),
                ],
            )
            assert db.scalar(select(func.count()).select_from(AttachmentRevision)) == 0
            assert db.scalar(select(func.count()).select_from(LiteTokenUsage)) == 0
        for path in (
            "/api/v1/lite/usage",
            f"/api/v1/projects/{ids['project']}/lite/usage",
            f"/api/v1/projects/{ids['project']}/lite/usage?paper_id={ids['paper']}",
        ):
            response = api.get(path)
            assert response.status_code == 200, response.text
            value = response.json()
            assert value["calls"] == 3
            assert value["retry_count"] == 1
            assert value["input_tokens"] == 125 and value["output_tokens"] == 25
            assert value["total_tokens"] == 150
            assert value["unknown_usage_calls"] == 1
            assert value["cost_known"] is False and value["cost_estimate"] is None
            assert value["by_kind"][0]["task_kind"] == "llm_document_parse"
            assert "credential_ref" not in response.text and "anonymous-model" not in response.text


def test_project_and_paper_filters_do_not_mix_model_only_imports(tmp_path):
    with client(tmp_path) as api:
        with Session(api.app.state.engine) as db, db.begin():
            first = _seed(db, [_request()])
            second = _seed(db, [_request(), _request("repair")], project_id=first["project"])
            third = _seed(db, [_request("boundary")])
        assert api.get("/api/v1/lite/usage").json()["calls"] == 4
        assert api.get(f"/api/v1/projects/{first['project']}/lite/usage").json()["calls"] == 3
        assert (
            api.get(
                f"/api/v1/projects/{first['project']}/lite/usage?paper_id={first['paper']}"
            ).json()["calls"]
            == 1
        )
        assert (
            api.get(
                f"/api/v1/projects/{second['project']}/lite/usage?paper_id={second['paper']}"
            ).json()["retry_count"]
            == 1
        )
        assert api.get(f"/api/v1/projects/{third['project']}/lite/usage").json()["calls"] == 1
        assert (
            api.get(
                f"/api/v1/projects/{first['project']}/lite/usage?paper_id={third['paper']}"
            ).status_code
            == 404
        )


def test_dispatch_placeholder_and_partial_usage_remain_unknown_without_zero_cost(tmp_path):
    with client(tmp_path) as api:
        with Session(api.app.state.engine) as db, db.begin():
            ids = _seed(
                db,
                [
                    _request(status="unknown"),
                    {
                        **_request("repair"),
                        "usage_source": "provider",
                        "usage": {"total_tokens": 30, "prompt_tokens": True},
                    },
                    _request(status="not_sent"),
                ],
                request_count=3,
            )
        value = api.get(f"/api/v1/projects/{ids['project']}/lite/usage").json()
        assert value["calls"] == 2 and value["retry_count"] == 1
        assert value["unknown_usage_calls"] == 2
        assert value["input_tokens"] == value["output_tokens"] == 0
        assert value["total_tokens"] == 30
        assert value["cost_known"] is False and value["cost_estimate"] is None


def test_missing_request_receipt_retains_dispatched_unknown_slot_and_repair_count(tmp_path):
    with client(tmp_path) as api:
        with Session(api.app.state.engine) as db, db.begin():
            ids = _seed(db, [], request_count=2, repair_attempts=1)
        value = api.get(f"/api/v1/projects/{ids['project']}/lite/usage").json()
        assert value["calls"] == value["unknown_usage_calls"] == 2
        assert value["retry_count"] == 1
        assert value["cost_known"] is False


def test_pending_batch_with_no_dispatch_has_zero_calls_and_zero_known_cost(tmp_path):
    with client(tmp_path) as api:
        with Session(api.app.state.engine) as db, db.begin():
            ids = _seed(db, [_request(status="not_sent")])
        value = api.get(f"/api/v1/projects/{ids['project']}/lite/usage").json()
        assert value["calls"] == 0 and value["unknown_usage_calls"] == 0
        assert value["cost_known"] is True and value["cost_estimate"] == 0.0
        assert value["by_kind"] == []


@pytest.mark.parametrize("duplicate_key", ["job", "run", "batch", "metadata"])
def test_batch_requests_not_counted_again_from_old_lite_ledger(tmp_path, duplicate_key):
    with client(tmp_path) as api:
        with Session(api.app.state.engine) as db, db.begin():
            ids = _seed(db, [_request(tokens={"prompt_tokens": 7, "completion_tokens": 3})])
            revision = str(uuid4())
            db.add(
                AttachmentRevision(
                    id=revision,
                    paper_id=ids["paper"],
                    sha256="a" * 64,
                    parser_version="anonymous",
                    page_count=2,
                    warnings=[],
                    created_at=now(),
                )
            )
            db.flush()
            base = dict(
                project_id=ids["project"],
                paper_id=ids["paper"],
                document_version_id=revision,
                input_tokens=7,
                output_tokens=3,
                usage_source="provider",
            )
            record_usage(
                db,
                task_kind="llm_document_parse",
                task_run_id=ids.get(duplicate_key),
                extra={"document_batch_id": ids["batch"]} if duplicate_key == "metadata" else {},
                **base,
            )
            record_usage(db, task_kind="paper_overview", task_run_id=ids["job"], **base)
            record_usage(db, task_kind="llm_document_parse", task_run_id=str(uuid4()), **base)
        value = api.get(f"/api/v1/projects/{ids['project']}/lite/usage").json()
        assert value["calls"] == 3
        assert value["input_tokens"] == 21 and value["output_tokens"] == 9
        by_kind = {item["task_kind"]: item for item in value["by_kind"]}
        assert by_kind["llm_document_parse"]["calls"] == 2
        assert by_kind["paper_overview"]["calls"] == 1


def test_repeated_read_only_queries_and_restart_keep_batch_usage_stable(tmp_path):
    with client(tmp_path) as api:
        with Session(api.app.state.engine) as db, db.begin():
            ids = _seed(db, [_request(status="uncertain"), _request("repair")])
        with read_session(api.app.state.engine) as db:
            assert db.connection().exec_driver_sql("PRAGMA query_only").scalar() == 1
            before = db.get(LlmDocumentBatch, ids["batch"]).usage
            expected = aggregate_usage(db, None).model_dump()
            assert aggregate_usage(db, None).model_dump() == expected
            assert not db.dirty and not db.new
        assert api.get("/api/v1/lite/usage").json() == expected
        assert api.get("/api/v1/lite/usage").json() == expected
        with Session(api.app.state.engine) as db:
            assert db.get(LlmDocumentBatch, ids["batch"]).usage == before
            assert db.scalar(select(func.count()).select_from(LiteTokenUsage)) == 0
    with client(tmp_path) as reopened:
        assert reopened.get("/api/v1/lite/usage").json() == expected
