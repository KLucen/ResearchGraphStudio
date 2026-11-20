import asyncio
import json
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pymupdf
import pytest
from researchgraph import model_document_api
from researchgraph.document_batch_contracts import (
    BatchResult,
    BatchValidationError,
    BoundaryResult,
)
from researchgraph.document_batch_models import LlmDocumentBatch, LlmDocumentBatchRun
from researchgraph.document_batch_recovery import (
    authorize_publication_retry,
    compatibility_retry_available,
    publication_retry_available,
)
from researchgraph.document_batches import _Dispatch, _repair_preserves_material, assemble_batches
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.model_document_api import execute_document_parse
from researchgraph.model_document_models import LlmDocumentParse, LlmDocumentSegment
from researchgraph.models import Base, Job, Paper, Project, now
from researchgraph.providers import ProviderError
from researchgraph.storage import make_engine
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def setup_job(tmp_path, *, repair=False, boundary=True, pages=7):
    path = tmp_path / "anonymous.pdf"
    with pymupdf.open() as pdf:
        for n in range(pages):
            pdf.new_page().insert_text((30, 40), f"Synthetic page {n + 1}")
        pdf.save(path)
    engine = make_engine(tmp_path)
    Base.metadata.create_all(engine)
    project, session_id, job_id = (str(uuid4()) for _ in range(3))
    with Session(engine) as db, db.begin():
        db.add(Project(id=project, name="synthetic", description="", created_at=now()))
        db.flush()
        db.add(
            ImportSession(
                id=session_id,
                project_id=project,
                source_kind="pdf",
                selection_id="synthetic",
                source_snapshot={},
                status="queued",
                plan={
                    "modality": "pdf",
                    "document_batching": True,
                    "pages_per_batch": 3,
                    "allow_network": True,
                    "allow_format_repair": repair,
                    "allow_boundary_review": boundary,
                },
                created_at=now(),
                updated_at=now(),
            )
        )
        db.add(
            Job(
                id=job_id,
                project_id=project,
                kind="llm_document_parse",
                status="running",
                attempt=1,
                payload={
                    "import_session_id": session_id,
                    "modality": "pdf",
                    "path": str(path),
                    "allow_network": True,
                },
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.add(
            ImportPlanItem(
                id=str(uuid4()),
                session_id=session_id,
                item_kind="document_parse",
                status="queued",
                config={},
                job_id=job_id,
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
        )
    return engine, session_id, job_id, path


def segment(page, text=None, **extra):
    return {
        "chapter_ref": "intro",
        "chapter_title": "Introduction",
        "chapter_level": 1,
        "chapter_order": 0,
        "kind": "paragraph",
        "ordinal": 0,
        "text": text or f"Material page {page}",
        "page_start": page,
        "page_end": page,
        **extra,
    }


class FakeProvider:
    name, model = "synthetic", "synthetic-vision"
    capabilities = SimpleNamespace(
        document_input="pdf",
        document_transport="chat_file",
        multimodal=True,
        max_output_tokens=None,
        context_window=None,
    )

    def __init__(
        self, *, fail=None, invalid=False, bad_repair=False, continuation=False, cancel=None
    ):
        self.calls, self.repairs, self.boundaries = [], [], []
        self.fail, self.invalid, self.bad_repair = fail, invalid, bad_repair
        self.continuation, self.cancel = continuation, cancel
        self.usage, self.request_metadata = {}, {}
        self.original = None

    async def complete_document(self, payload, schema=None, *, before_send=None, on_progress=None):
        assert before_send()
        on_progress("document_connecting", {})
        context = payload["document_batch_context"]
        assert "path" not in payload and payload["document_base64"]
        if context["task"] == "boundary":
            self.boundaries.append(context)
            return json.dumps(
                {
                    "version": "document-boundary-1",
                    "action": "merge",
                    "separator": "space",
                    "reason": "continuation",
                }
            )
        self.calls.append(context)
        if self.cancel:
            self.cancel()
        if self.fail == len(self.calls):
            raise ProviderError("timeout", "synthetic timeout")
        first, end = context["page_start"], context["page_end"]
        result = {
            "version": "document-batch-1",
            "page_start": first,
            "page_end": end,
            "segments": [
                segment(
                    p,
                    continues_before=self.continuation and p == first and first > 1,
                    continues_after=self.continuation
                    and p == end
                    and end < context["document_pages"],
                )
                for p in range(first, end + 1)
            ],
        }
        self.original = result
        self.usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        if self.invalid:
            result = {**result, "extra_private_source_text": "never persist me"}
        return json.dumps(result)

    async def repair_document_format(
        self, raw, schema, errors, *, before_send=None, on_progress=None
    ):
        assert before_send()
        on_progress("document_connecting", {})
        self.repairs.append({"raw": raw, "errors": errors})
        value = json.loads(json.dumps(self.original))
        if self.bad_repair:
            value["segments"][0]["text"] = "invented replacement"
        return json.dumps(value)


def readback(engine, job_id):
    with Session(engine) as db:
        job = db.get(Job, job_id)
        return (
            job.status,
            job.result,
            list(
                db.scalars(
                    select(LlmDocumentBatch).order_by(
                        LlmDocumentBatch.ordinal, LlmDocumentBatch.kind
                    )
                ).all()
            ),
        )


def test_complete_batches_publish_original_pages_without_overlap(tmp_path):
    engine, _, job, _ = setup_job(tmp_path)
    provider = FakeProvider()
    asyncio.run(execute_document_parse(engine, job, tmp_path, provider=provider))
    status, result, rows = readback(engine, job)
    assert status == "succeeded"
    assert [(r["page_start"], r["page_end"], r["send_start"]) for r in provider.calls] == [
        (1, 3, 1),
        (4, 5, 3),
        (6, 7, 5),
    ]
    assert result["document_batches"]["completed"] == 3
    assert result["document_batches"]["requests_sent"] == 3
    assert len([r for r in rows if r.kind == "boundary" and r.status == "validated"]) == 2
    assert provider.boundaries == []
    with Session(engine) as db:
        segments = list(db.scalars(select(LlmDocumentSegment).order_by(LlmDocumentSegment.ordinal)))
        assert len(segments) == 7
        assert [s.locator["page_start"] for s in segments] == list(range(1, 8))
        assert db.scalar(select(LlmDocumentParse)).raw_response is None


@pytest.mark.parametrize(
    "item_kinds",
    [("paper_overview",), ("paper_overview", "paper_reading", "translation")],
)
def test_publication_queues_selected_jobs_before_linking_plan_items(tmp_path, item_kinds):
    engine, session_id, job_id, _ = setup_job(tmp_path)
    with Session(engine) as db, db.begin():
        assert db.scalar(text("PRAGMA foreign_keys")) == 1
        session = db.get(ImportSession, session_id)
        session.source_snapshot = {"paper_id": "synthetic-paper"}
        db.add(
            Paper(
                id="synthetic-paper",
                project_id=session.project_id,
                title="Synthetic paper",
                created_at=now(),
            )
        )
        for kind in item_kinds:
            db.add(
                ImportPlanItem(
                    id=str(uuid4()),
                    session_id=session_id,
                    item_kind=kind,
                    status="planned",
                    config={},
                    attempt=0,
                    created_at=now(),
                    updated_at=now(),
                )
            )
    provider = FakeProvider()
    asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as db, db.begin():
        assert db.get(Job, job_id).status == "succeeded"
        parse = db.scalar(select(LlmDocumentParse).where(LlmDocumentParse.status == "succeeded"))
        queued = list(db.scalars(select(Job).where(Job.kind == "llm_document_postprocess")))
        assert {job.payload["item_kind"] for job in queued} == set(item_kinds)
        assert len(queued) == len(item_kinds)
        for job in queued:
            item = db.scalar(select(ImportPlanItem).where(ImportPlanItem.job_id == job.id))
            assert item is not None and item.status == "queued"
            assert item.item_kind == job.payload["item_kind"]
            assert job.payload["llm_document_parse_id"] == parse.id
        # Re-entering the post-publication transition must not create more jobs.
        session = db.get(ImportSession, session_id)
        model_document_api._queue_selected_postprocessing(db, session, parse)
        model_document_api._queue_selected_postprocessing(db, session, parse)
        assert len(
            list(db.scalars(select(Job).where(Job.kind == "llm_document_postprocess")))
        ) == len(item_kinds)
        assert not db.execute(text("PRAGMA foreign_key_check")).all()
    assert len(provider.calls) == 3


@pytest.mark.parametrize("legacy_fk", [False, True])
def test_integrity_error_can_recover_publication_without_provider_requests(
    tmp_path, monkeypatch, legacy_fk
):
    engine, session_id, job_id, _ = setup_job(tmp_path, pages=7)
    provider = FakeProvider()
    with Session(engine) as db, db.begin():
        session = db.get(ImportSession, session_id)
        session.plan = {**session.plan, "overview": True}
        session.source_snapshot = {"paper_id": "synthetic-paper"}
        db.add(
            Paper(
                id="synthetic-paper",
                project_id=session.project_id,
                title="Synthetic paper",
                created_at=now(),
            )
        )
        db.add(
            ImportPlanItem(
                id=str(uuid4()),
                session_id=session_id,
                item_kind="paper_overview",
                status="planned",
                config={},
                job_id=None,
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
        )
        job = db.get(Job, job_id)
        job.payload = {**job.payload, "paper_id": "synthetic-paper"}

    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys=ON")
    if legacy_fk:
        connection.execute("CREATE TABLE synthetic_parent (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE synthetic_child (parent_id INTEGER REFERENCES synthetic_parent(id))"
        )
        statement = "INSERT INTO synthetic_child VALUES (99)"
    else:
        connection.execute("CREATE TABLE synthetic_unique (value TEXT UNIQUE)")
        connection.execute("INSERT INTO synthetic_unique VALUES ('duplicate')")
        statement = "INSERT INTO synthetic_unique VALUES ('duplicate')"
    try:
        connection.execute(statement)
    except sqlite3.IntegrityError as original_error:
        integrity_error = IntegrityError(
            "INSERT INTO private_table VALUES (?)",
            {"private_value": "must-not-be-saved"},
            original_error,
        )
    else:  # pragma: no cover - fixture guard
        raise AssertionError("synthetic constraint violation was not raised")
    finally:
        connection.close()

    def fail_publication(*_args, **_kwargs):
        raise integrity_error

    original_publish = model_document_api.materialize_document_parse
    monkeypatch.setattr(
        "researchgraph.model_document_api.materialize_document_parse", fail_publication
    )
    with pytest.raises(IntegrityError):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as db:
        job = db.get(Job, job_id)
        run = db.scalar(select(LlmDocumentBatchRun).where(LlmDocumentBatchRun.job_id == job_id))
        batches = list(
            db.scalars(select(LlmDocumentBatch).where(LlmDocumentBatch.run_id == run.id))
        )
        assert job.status == "failed" and job.attempt == 1
        assert job.result["failure_diagnostics"] == {
            "database_dialect": "sqlite",
            "sqlite_errorcode": (
                sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY
                if legacy_fk
                else sqlite3.SQLITE_CONSTRAINT_UNIQUE
            ),
            "sqlite_errorname": (
                "SQLITE_CONSTRAINT_FOREIGNKEY" if legacy_fk else "SQLITE_CONSTRAINT_UNIQUE"
            ),
            "constraint_category": "foreign_key" if legacy_fk else "unique",
        }
        serialized = json.dumps(job.result)
        assert "private_table" not in serialized
        assert "must-not-be-saved" not in serialized
        assert all(row.status == "validated" for row in batches)
        checkpoints = {
            row.id: (row.result_json, row.request_count, row.attempts, row.usage) for row in batches
        }
        assert publication_retry_available(db, job)
    assert len(provider.calls) == 3
    monkeypatch.setattr(
        "researchgraph.model_document_api.materialize_document_parse", original_publish
    )

    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session_id,
                ImportPlanItem.item_kind == "document_parse",
            )
        )
        if legacy_fk:
            job.result = {**job.result, "publication_recovery_attempts": 2}
            assert "publication_recovery_version" not in job.result
            assert publication_retry_available(db, job)
        job.status, job.attempt = "running", 6 if legacy_fk else 5
        job.stage = "saving_document"
        authorize_publication_retry(job)
        assert job.result["publication_recovery_attempts"] == (3 if legacy_fk else 1)
        item.status = "running"
        db.get(ImportSession, session_id).status = "running"

    asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=None))
    with Session(engine) as db:
        job = db.get(Job, job_id)
        session = db.get(ImportSession, session_id)
        parse_item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session_id,
                ImportPlanItem.item_kind == "document_parse",
            )
        )
        overview_item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session_id,
                ImportPlanItem.item_kind == "paper_overview",
            )
        )
        parses = list(
            db.scalars(
                select(LlmDocumentParse).where(LlmDocumentParse.import_session_id == session_id)
            )
        )
        assert job.status == "succeeded"
        assert session.status == "queued"
        assert parse_item.status == "succeeded"
        assert job.result["publication_recovered"] is True
        assert len([parse for parse in parses if parse.status == "succeeded"]) == 1
        assert (
            len(
                list(
                    db.scalars(
                        select(LlmDocumentSegment).where(
                            LlmDocumentSegment.parse_id
                            == next(parse.id for parse in parses if parse.status == "succeeded")
                        )
                    )
                )
            )
            == 7
        )
        assert overview_item.status == "queued" and overview_item.job_id
        assert db.get(Job, overview_item.job_id).kind == "llm_document_postprocess"
        assert len(list(db.scalars(select(Job).where(Job.kind == "llm_document_postprocess")))) == 1
        assert db.get(LlmDocumentBatchRun, run.id).status == "succeeded"
        assert {
            row.id: (row.result_json, row.request_count, row.attempts, row.usage)
            for row in db.scalars(select(LlmDocumentBatch))
        } == checkpoints
        assert not db.execute(text("PRAGMA foreign_key_check")).all()
    assert len(provider.calls) == 3


def test_changed_checkpoint_after_publication_authorization_never_initializes_provider(
    tmp_path, monkeypatch
):
    engine, session_id, job_id, _ = setup_job(tmp_path)

    def fail_publication(*_args, **_kwargs):
        raise ValueError("synthetic publication failure")

    monkeypatch.setattr(model_document_api, "materialize_document_parse", fail_publication)
    provider = FakeProvider()
    with pytest.raises(ValueError, match="synthetic publication failure"):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        assert publication_retry_available(db, job)
        authorize_publication_retry(job)
        job.status = "running"
        job.payload = {**job.payload, "provider_snapshot": {"synthetic": "not-a-provider"}}
        item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session_id,
                ImportPlanItem.item_kind == "document_parse",
            )
        )
        item.status = "running"
        first = db.scalar(select(LlmDocumentBatch).where(LlmDocumentBatch.kind == "extract"))
        first.status = "failed"
        first.result_json = None
    initialized = []

    def forbidden_provider(*_args, **_kwargs):
        initialized.append(True)
        raise AssertionError("publication-only recovery must not initialize a provider")

    monkeypatch.setattr("researchgraph.model_settings.from_snapshot", forbidden_provider)
    with pytest.raises(ProviderError, match="仅发布恢复条件已变化"):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=None))
    assert initialized == []
    assert len(provider.calls) == 3
    with Session(engine) as db:
        assert db.get(Job, job_id).status == "failed"
        assert not list(
            db.scalars(select(LlmDocumentParse).where(LlmDocumentParse.status == "succeeded"))
        )


def test_publication_retry_is_not_available_with_incomplete_or_changed_checkpoints(tmp_path):
    engine, session_id, job_id, _ = setup_job(tmp_path, pages=2)
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        job.status, job.attempt = "failed", 4
        item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session_id,
                ImportPlanItem.item_kind == "document_parse",
            )
        )
        item.status = "failed"
        assert not publication_retry_available(db, job)


def test_failure_keeps_completed_and_explicit_retry_only_unfinished(tmp_path):
    engine, _, job, _ = setup_job(tmp_path)
    first = FakeProvider(fail=2)
    with pytest.raises(ProviderError):
        asyncio.run(execute_document_parse(engine, job, tmp_path, provider=first))
    assert readback(engine, job)[0] == "failed"
    with Session(engine) as db, db.begin():
        task = db.get(Job, job)
        task.status, task.attempt = "running", 2
    second = FakeProvider()
    asyncio.run(execute_document_parse(engine, job, tmp_path, provider=second))
    assert [r["page_start"] for r in second.calls] == [4, 6]
    assert readback(engine, job)[0] == "succeeded"


def test_same_attempt_does_not_resend_uncertain_request(tmp_path):
    engine, _, job, _ = setup_job(tmp_path)
    with pytest.raises(ProviderError):
        asyncio.run(execute_document_parse(engine, job, tmp_path, provider=FakeProvider(fail=1)))
    with Session(engine) as db, db.begin():
        db.get(Job, job).status = "running"
    provider = FakeProvider()
    with pytest.raises(ProviderError, match="显式继续"):
        asyncio.run(execute_document_parse(engine, job, tmp_path, provider=provider))
    assert provider.calls == []


def test_source_change_refuses_checkpoint_reuse(tmp_path):
    engine, _, job, path = setup_job(tmp_path)
    with pytest.raises(ProviderError):
        asyncio.run(execute_document_parse(engine, job, tmp_path, provider=FakeProvider(fail=2)))
    path.write_bytes(path.read_bytes() + b"\n")
    with Session(engine) as db, db.begin():
        task = db.get(Job, job)
        task.status, task.attempt = "running", 2
    provider = FakeProvider()
    with pytest.raises(ProviderError, match="版本"):
        asyncio.run(execute_document_parse(engine, job, tmp_path, provider=provider))
    assert provider.calls == []


@pytest.mark.parametrize("repair", [False, True])
def test_schema_failure_repair_authorization_and_private_values(tmp_path, repair):
    engine, _, job, _ = setup_job(tmp_path, repair=repair, pages=2)
    provider = FakeProvider(invalid=True)
    if repair:
        asyncio.run(execute_document_parse(engine, job, tmp_path, provider=provider))
    else:
        with pytest.raises(BatchValidationError):
            asyncio.run(execute_document_parse(engine, job, tmp_path, provider=provider))
    status, result, rows = readback(engine, job)
    assert len(provider.repairs) == int(repair)
    assert rows[0].repair_attempts == int(repair)
    assert rows[0].request_count == 1 + int(repair)
    assert "never persist me" not in json.dumps(result)
    assert "extra_private_source_text" not in json.dumps(result)
    assert status == ("succeeded" if repair else "failed")


def test_format_repair_cannot_replace_content_or_repeat(tmp_path):
    engine, _, job, _ = setup_job(tmp_path, repair=True, pages=2)
    provider = FakeProvider(invalid=True, bad_repair=True)
    with pytest.raises(BatchValidationError):
        asyncio.run(execute_document_parse(engine, job, tmp_path, provider=provider))
    assert len(provider.repairs) == 1
    assert readback(engine, job)[2][0].result_json is None
    with Session(engine) as db, db.begin():
        task = db.get(Job, job)
        task.status, task.attempt = "running", 2
    provider2 = FakeProvider(invalid=True)
    with pytest.raises(BatchValidationError):
        asyncio.run(execute_document_parse(engine, job, tmp_path, provider=provider2))
    assert provider2.repairs == []


def test_boundary_review_merges_only_original_text(tmp_path):
    engine, _, job, _ = setup_job(tmp_path, pages=5)
    provider = FakeProvider(continuation=True)
    asyncio.run(execute_document_parse(engine, job, tmp_path, provider=provider))
    assert len(provider.boundaries) == 1
    assert provider.boundaries[0]["send_end"] - provider.boundaries[0]["send_start"] == 1
    with Session(engine) as db:
        segments = list(db.scalars(select(LlmDocumentSegment).order_by(LlmDocumentSegment.ordinal)))
        assert len(segments) == 4
        assert segments[2].text == "Material page 3 Material page 4"
        assert segments[2].locator["page_start"] == 3
        assert segments[2].locator["page_end"] == 4


def test_cancel_after_dispatch_never_publishes_or_sends_next_batch(tmp_path):
    engine, _, job, _ = setup_job(tmp_path)

    def cancel():
        with Session(engine) as db, db.begin():
            db.get(Job, job).status = "cancelled"

    provider = FakeProvider(cancel=cancel)
    asyncio.run(execute_document_parse(engine, job, tmp_path, provider=provider))
    assert len(provider.calls) == 1
    assert readback(engine, job)[0] == "cancelled"
    with Session(engine) as db:
        assert db.scalar(select(LlmDocumentParse)) is None


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (("ok", "ok"), ("needs_review", "needs_review")),
        (("degraded", "needs_review"), ("needs_review", "needs_review")),
        (("unavailable", "failed"), ("unavailable", "failed")),
        (("failed", "ok"), ("failed", "needs_review")),
    ],
)
def test_uncertain_boundary_preserves_both_fragments(statuses, expected):
    batches = [
        BatchResult(
            version="document-batch-1",
            page_start=i,
            page_end=i,
            segments=[
                segment(
                    i,
                    status=statuses[i - 1],
                    continues_after=i == 1,
                    continues_before=i == 2,
                )
            ],
        )
        for i in (1, 2)
    ]
    body = assemble_batches(
        batches,
        [
            BoundaryResult(
                version="document-boundary-1",
                action="uncertain",
                separator="space",
                reason="uncertain",
            )
        ],
    )
    assert len(body.segments) == 2 and body.warnings
    assert tuple(s.status for s in body.segments) == expected
    assert tuple(batch.segments[0].status for batch in batches) == statuses


def test_table_merge_drops_only_exact_repeated_header():
    parts = []
    for page, rows in [(1, [["1", "2"]]), (2, [["A", "B"], ["3", "4"]])]:
        item = segment(
            page, kind="table", text=None, table_data={"columns": ["A", "B"], "rows": rows}
        )
        parts.append(
            BatchResult(version="document-batch-1", page_start=page, page_end=page, segments=[item])
        )
    body = assemble_batches(
        parts,
        [
            BoundaryResult(
                version="document-boundary-1",
                action="merge",
                separator="newline",
                reason="table_header_repeat",
            )
        ],
    )
    assert len(body.segments) == 1
    assert body.segments[0].table_data["rows"] == [["1", "2"], ["3", "4"]]


def test_repair_rejects_same_words_reattributed_to_different_pages():
    original = {
        "version": "document-batch-1",
        "page_start": 1,
        "page_end": 2,
        "segments": [segment(1, "Alpha"), segment(2, "Beta")],
    }
    changed = json.loads(json.dumps(original))
    changed["segments"][0]["text"] = "Beta"
    changed["segments"][1]["text"] = "Alpha"
    assert not _repair_preserves_material(json.dumps(original), BatchResult.model_validate(changed))


def test_merge_preserves_worst_source_status_and_unknown_confidence():
    parts = [
        BatchResult(
            version="document-batch-1",
            page_start=i,
            page_end=i,
            segments=[
                segment(
                    i, status="ok" if i == 1 else "needs_review", confidence=1.0 if i == 1 else None
                )
            ],
        )
        for i in (1, 2)
    ]
    body = assemble_batches(
        parts,
        [
            BoundaryResult(
                version="document-boundary-1",
                action="merge",
                separator="space",
                reason="continuation",
            )
        ],
    )
    assert body.segments[0].status == "needs_review"
    assert body.segments[0].confidence is None


def test_overlong_merge_keeps_valid_parts_without_private_error():
    marker = "private_scientific_material" + "x" * 600_000
    parts = [
        BatchResult(
            version="document-batch-1", page_start=i, page_end=i, segments=[segment(i, marker)]
        )
        for i in (1, 2)
    ]
    body = assemble_batches(
        parts,
        [
            BoundaryResult(
                version="document-boundary-1",
                action="merge",
                separator="space",
                reason="continuation",
            )
        ],
    )
    assert len(body.segments) == 2
    assert body.warnings and "private_scientific_material" not in str(body.warnings)


def test_mutated_range_checkpoint_refused_before_request(tmp_path):
    engine, _, job, _ = setup_job(tmp_path)
    with pytest.raises(ProviderError):
        asyncio.run(execute_document_parse(engine, job, tmp_path, provider=FakeProvider(fail=2)))
    with Session(engine) as db, db.begin():
        task = db.get(Job, job)
        task.status, task.attempt = "running", 2
        row = db.scalar(
            select(LlmDocumentBatch).where(
                LlmDocumentBatch.kind == "extract", LlmDocumentBatch.ordinal == 1
            )
        )
        row.send_start = 2
    provider = FakeProvider()
    with pytest.raises(ProviderError, match="范围"):
        asyncio.run(execute_document_parse(engine, job, tmp_path, provider=provider))
    assert provider.calls == []


class Boundary400Provider(FakeProvider):
    async def complete_document(self, payload, schema=None, *, before_send=None, on_progress=None):
        if payload["document_batch_context"]["task"] == "boundary":
            self.request_metadata = {"http_status": 400, "boundary_prompt_version": 2}
            raise ProviderError("client", "synthetic boundary HTTP 400")
        return await super().complete_document(
            payload, schema, before_send=before_send, on_progress=on_progress
        )


def _legacy_exhausted_boundary(tmp_path):
    engine, _, job_id, _ = setup_job(tmp_path, pages=5)
    with pytest.raises(ProviderError):
        asyncio.run(
            execute_document_parse(
                engine, job_id, tmp_path, provider=Boundary400Provider(continuation=True)
            )
        )
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        job.attempt = 3
        run = db.scalar(select(LlmDocumentBatchRun))
        run.settings = {**run.settings, "job_attempt": 3, "request_budget": 5}
        boundary = db.scalar(select(LlmDocumentBatch).where(LlmDocumentBatch.kind == "boundary"))
        boundary.attempts = boundary.request_count = 3
        boundary.request_metadata = {"http_status": 400}
        boundary.usage = {
            "requests": [{"purpose": "boundary", "status": "unknown"} for _ in range(3)]
        }
        assert compatibility_retry_available(db, job)
    return engine, job_id


def test_old_three_boundary_400_attempts_can_resume_without_reextracting(tmp_path):
    engine, job_id = _legacy_exhausted_boundary(tmp_path)
    with Session(engine) as db:
        originals = {
            row.id: (row.result_json, row.request_count, row.usage)
            for row in db.scalars(
                select(LlmDocumentBatch).where(LlmDocumentBatch.kind == "extract")
            )
        }
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        job.status, job.attempt = "running", 4
    provider = FakeProvider(continuation=True)
    asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))
    assert provider.calls == [] and len(provider.boundaries) == 1
    assert readback(engine, job_id)[0] == "succeeded"
    with Session(engine) as db:
        boundary = db.scalar(select(LlmDocumentBatch).where(LlmDocumentBatch.kind == "boundary"))
        assert boundary.attempts == boundary.request_count == 4
        assert boundary.usage["requests"][-1]["boundary_prompt_version"] == 2
        for row in db.scalars(select(LlmDocumentBatch).where(LlmDocumentBatch.kind == "extract")):
            assert (row.result_json, row.request_count, row.usage) == originals[row.id]


def test_corrected_boundary_failure_consumes_single_legacy_recovery(tmp_path):
    engine, job_id = _legacy_exhausted_boundary(tmp_path)
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        job.status, job.attempt = "running", 4
    with pytest.raises(ProviderError):
        asyncio.run(
            execute_document_parse(
                engine, job_id, tmp_path, provider=Boundary400Provider(continuation=True)
            )
        )
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        assert not compatibility_retry_available(db, job)
        job.status, job.attempt = "running", 5
    provider = FakeProvider(continuation=True)
    with pytest.raises(ProviderError, match="3次"):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))
    assert provider.calls == provider.boundaries == []


def test_cancel_before_dispatch_keeps_legacy_recovery_and_prior_diagnostics(tmp_path):
    engine, job_id = _legacy_exhausted_boundary(tmp_path)
    with Session(engine) as db:
        job = db.get(Job, job_id)
        run = db.scalar(select(LlmDocumentBatchRun))
        row = db.scalar(select(LlmDocumentBatch).where(LlmDocumentBatch.kind == "boundary"))
        row_id, path, version = row.id, job.payload["path"], run.source_version
    dispatch = _Dispatch(engine, job_id, row_id, "boundary", path, version)
    provider = FakeProvider()
    provider.request_metadata = {"boundary_prompt_version": 2, "phase": "rendering"}
    dispatch.finish(provider, "not_sent")
    with Session(engine) as db:
        row = db.get(LlmDocumentBatch, row_id)
        assert row.request_metadata == {"http_status": 400}
        assert row.attempts == row.request_count == len(row.usage["requests"]) == 3
        assert compatibility_retry_available(db, db.get(Job, job_id))
