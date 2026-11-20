"""Model-only postprocess receipts remain source-scoped and counted exactly once."""

from uuid import uuid4

from researchgraph.import_plan_models import ImportSession
from researchgraph.lite_models import LiteTokenUsage
from researchgraph.lite_usage import aggregate_usage, record_usage
from researchgraph.model_document_models import LlmDocumentOutput, LlmDocumentParse
from researchgraph.models import AttachmentRevision, Base, Job, Paper, Project, now
from researchgraph.storage import make_engine, read_session
from sqlalchemy.orm import Session


def _seed(db, *, project_id=None, requests=None, kind="paper_overview", legacy_raw=None):
    project_id = project_id or str(uuid4())
    paper_id, session_id, parse_id, output_id, job_id = (str(uuid4()) for _ in range(5))
    timestamp = now()
    if db.get(Project, project_id) is None:
        db.add(Project(id=project_id, name="Synthetic", description="", created_at=timestamp))
        db.flush()
    db.add(Paper(id=paper_id, project_id=project_id, title="Model-only", created_at=timestamp))
    db.flush()
    db.add(
        ImportSession(
            id=session_id,
            project_id=project_id,
            source_kind="pdf",
            selection_id=str(uuid4()),
            source_snapshot={"paper_id": paper_id},
            plan={},
            status="failed",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    db.flush()
    db.add(
        LlmDocumentParse(
            id=parse_id,
            import_session_id=session_id,
            parse_version="llm-document-1",
            modality="text",
            status="succeeded",
            warnings=[],
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    db.flush()
    receipts = (
        [{**receipt, "job_id": job_id} for receipt in requests] if requests is not None else None
    )
    db.add(
        LlmDocumentOutput(
            id=output_id,
            import_session_id=session_id,
            parse_id=parse_id,
            item_kind=kind,
            status="failed" if legacy_raw else "pending",
            raw_response=legacy_raw,
            usage={"requests": receipts} if receipts is not None else {},
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    db.add(
        Job(
            id=job_id,
            project_id=project_id,
            kind="llm_document_postprocess",
            status="failed",
            attempt=2,
            payload={
                "import_session_id": session_id,
                "llm_document_parse_id": parse_id,
                "paper_id": paper_id,
                "output_id": output_id,
                "item_kind": kind,
            },
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    db.flush()
    return {
        "project": project_id,
        "paper": paper_id,
        "session": session_id,
        "parse": parse_id,
        "output": output_id,
        "job": job_id,
    }


def _receipt(attempt=1, *, purpose="generate", status="received", tokens=None):
    return {
        "attempt": attempt,
        "purpose": purpose,
        "status": status,
        "usage_source": "provider" if tokens else "unknown",
        "usage": tokens or {},
    }


def _engine(tmp_path):
    engine = make_engine(tmp_path / "usage.sqlite3")
    Base.metadata.create_all(engine)
    return engine


def test_postprocess_receipts_are_deduplicated_and_unknown_sent_calls_are_preserved(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as db, db.begin():
        ids = _seed(
            db,
            requests=[
                _receipt(status="sent"),
                _receipt(tokens={"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10}),
                _receipt(attempt=2, status="failed"),
                _receipt(
                    attempt=3, purpose="repair", tokens={"prompt_tokens": 5, "completion_tokens": 1}
                ),
                _receipt(attempt=4, status="not_sent"),
            ],
        )
    with read_session(engine) as db:
        before = db.get(LlmDocumentOutput, ids["output"]).usage
        value = aggregate_usage(db, ids["project"], ids["paper"]).model_dump()
        assert value["calls"] == 3 and value["retry_count"] == 2
        assert value["input_tokens"] == 13 and value["output_tokens"] == 3
        assert value["total_tokens"] == 16
        assert value["unknown_usage_calls"] == 1 and value["calls_known"] is True
        assert value["cost_known"] is False and value["cost_estimate"] is None
        assert value == aggregate_usage(db, ids["project"], ids["paper"]).model_dump()
        assert before == db.get(LlmDocumentOutput, ids["output"]).usage
        assert not db.dirty and not db.new
        assert db.query(AttachmentRevision).count() == db.query(LiteTokenUsage).count() == 0
    engine.dispose()
    reopened = make_engine(tmp_path / "usage.sqlite3")
    with read_session(reopened) as db:
        assert aggregate_usage(db, ids["project"], ids["paper"]).model_dump() == value


def test_global_project_and_paper_filters_do_not_mix_parser_sources(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as db, db.begin():
        first = _seed(db, requests=[_receipt()])
        second = _seed(
            db,
            project_id=first["project"],
            kind="paper_reading",
            requests=[_receipt(), _receipt(attempt=2, purpose="repair")],
        )
        third = _seed(db, kind="translation", requests=[_receipt()])
    with read_session(engine) as db:
        assert aggregate_usage(db, None).calls == 4
        assert aggregate_usage(db, first["project"]).calls == 3
        assert aggregate_usage(db, first["project"], first["paper"]).calls == 1
        assert aggregate_usage(db, first["project"], second["paper"]).calls == 2
        assert aggregate_usage(db, third["project"]).calls == 1
        assert aggregate_usage(db, first["project"], third["paper"]).calls == 0


def test_legacy_raw_has_unknown_run_count_and_unsent_pending_or_config_failure_has_zero(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as db, db.begin():
        legacy = _seed(db, legacy_raw="Preserved old model response")
        _seed(db, project_id=legacy["project"], requests=[_receipt(status="not_sent")])
        _seed(db, project_id=legacy["project"])
    with read_session(engine) as db:
        result = aggregate_usage(db, legacy["project"])
        assert result.calls == 0 and result.unrecorded_runs == 1
        assert result.calls_known is False and result.cost_known is False
        assert result.unknown_usage_calls == 0


def test_postprocess_receipt_wins_over_same_lite_ledger_without_suppressing_other_calls(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as db, db.begin():
        ids = _seed(db, requests=[_receipt(tokens={"prompt_tokens": 8, "completion_tokens": 2})])
        revision_id = str(uuid4())
        db.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=ids["paper"],
                sha256="a" * 64,
                parser_version="independent-local-parser",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        db.flush()
        source = {
            "project_id": ids["project"],
            "paper_id": ids["paper"],
            "document_version_id": revision_id,
        }
        record_usage(
            db,
            task_kind="paper_overview",
            task_run_id=ids["job"],
            input_tokens=8,
            output_tokens=2,
            usage_source="provider",
            **source,
        )
        record_usage(
            db,
            task_kind="paper_overview",
            task_run_id=str(uuid4()),
            extra={"model_document_output_id": ids["output"]},
            **source,
        )
        record_usage(
            db,
            task_kind="paper_reading",
            task_run_id=ids["job"],
            input_tokens=5,
            output_tokens=1,
            usage_source="provider",
            **source,
        )
        record_usage(
            db, task_kind="paper_overview", task_run_id=ids["job"], cache_hit=True, **source
        )
        record_usage(db, task_kind="paper_overview", task_run_id=str(uuid4()), **source)
    with read_session(engine) as db:
        result = aggregate_usage(db, ids["project"])
        assert result.calls == 3 and result.cache_hits == 1
        assert result.total_tokens == 16
        by_kind = {item.task_kind: item for item in result.by_kind}
        assert by_kind["paper_overview"].calls == 2
        assert by_kind["paper_reading"].calls == 1


def test_malformed_receipts_and_bad_usage_values_cannot_become_free_or_cross_source_calls(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as db, db.begin():
        ids = _seed(
            db,
            requests=[
                _receipt(tokens={"prompt_tokens": True, "completion_tokens": -3, "total_tokens": 7})
            ],
        )
        output = db.get(LlmDocumentOutput, ids["output"])
        output.usage = {
            "requests": [*output.usage["requests"], {**_receipt(), "job_id": "another-project-job"}]
        }
    with read_session(engine) as db:
        value = aggregate_usage(db, ids["project"])
        assert value.calls == 1 and value.unknown_usage_calls == 1
        assert value.input_tokens == value.output_tokens == 0 and value.total_tokens == 7
        assert value.unrecorded_runs == 1 and value.calls_known is False
        assert value.cost_known is False
