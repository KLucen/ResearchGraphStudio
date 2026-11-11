import asyncio
import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.lite_models import LiteCacheEntry, LiteTokenUsage
from researchgraph.models import (
    AttachmentRevision,
    Base,
    Chunk,
    EvidenceSpan,
    Job,
    Paper,
    Project,
    Section,
    now,
)
from researchgraph.qa_api import (
    _configuration,
    _hash,
    _identity,
    build_qa_input,
    execute_qa,
    recover_qa,
    register_qa_api,
)
from researchgraph.qa_contracts import PROMPT_VERSION, SCHEMA_VERSION, TASK_KIND
from researchgraph.qa_models import LiteQARecord
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


class CountingProvider:
    name = "test-provider"
    model = "test-model"
    base_url = "https://provider.test/v1"
    parameters: dict[str, object] = {"temperature": 0}

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0
        self.usage = {"prompt_tokens": 90, "completion_tokens": 40, "total_tokens": 130}
        self.request_metadata: dict[str, object] = {}

    async def complete(self, prompt: str, data: dict, schema: dict) -> str:
        self.calls += 1
        return self.response


def _fixture() -> tuple[Engine, str, str, str, str, str]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import researchgraph.lite_models  # noqa: F401
    import researchgraph.qa_models  # noqa: F401

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE VIRTUAL TABLE chunk_fts USING fts5("
                "chunk_id UNINDEXED, paper_id UNINDEXED, document_version_id UNINDEXED, "
                "section_id UNINDEXED, text, tokenize='unicode61')"
            )
        )
    project_id, paper_id, revision_id, section_id, chunk_id, span_id = (
        str(uuid4()) for _ in range(6)
    )
    timestamp = now()
    with Session(engine) as session, session.begin():
        session.add(
            Project(
                id=project_id,
                name="qa-test",
                description="lite",
                experience_mode="lite",
                created_at=timestamp,
            )
        )
        session.add(
            Paper(id=paper_id, project_id=project_id, title="QA paper", created_at=timestamp)
        )
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="a" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at=timestamp,
            )
        )
        session.add(
            Section(
                id=section_id,
                document_version_id=revision_id,
                title="Methods",
                ordinal=1,
                role="method",
                parser="test",
                parent_id=None,
                level=1,
                start_page=0,
                end_page=0,
                excluded=False,
            )
        )
        session.add(
            Chunk(
                id=chunk_id,
                revision_id=revision_id,
                page_index=0,
                page_label="1",
                block_index=0,
                text="The method uses a shared memory module.",
                bbox=[0, 0, 1, 1],
            )
        )
        session.add(
            EvidenceSpan(
                id=span_id,
                document_version_id=revision_id,
                section_id=section_id,
                paragraph_id=chunk_id,
                page_index=0,
                start_offset=0,
                end_offset=39,
                quote="The method uses a shared memory module.",
                text_sha256="b" * 64,
                normalization="identity-v1",
                bbox_list=[[0, 0, 1, 1]],
            )
        )
        session.execute(
            text(
                "INSERT INTO chunk_fts("
                "chunk_id,paper_id,document_version_id,section_id,text) "
                "VALUES (:c,:p,:d,:s,:t)"
            ),
            {
                "c": chunk_id,
                "p": paper_id,
                "d": revision_id,
                "s": section_id,
                "t": "The method uses a shared memory module.",
            },
        )
    return engine, project_id, paper_id, revision_id, section_id, span_id


def _job(
    engine: Engine,
    provider: CountingProvider,
    project_id: str,
    paper_id: str,
    revision_id: str,
    section_id: str,
    *,
    allow_network: bool = True,
) -> str:
    with Session(engine) as session:
        paper = session.get(Paper, paper_id)
        revision = session.get(AttachmentRevision, revision_id)
        assert paper is not None and revision is not None
        request = {
            "document_version_id": revision_id,
            "section_id": section_id,
            "scope": "section",
            "question": "What method is used?",
            "selection_span_ids": [],
            "allow_network": allow_network,
        }
        context, spans = build_qa_input(
            session,
            paper,
            revision,
            question=request["question"],
            scope="section",
            section_id=section_id,
            selection_span_ids=[],
            optional_short_card=None,
        )
        input_hash = _hash(context)
        key, _ = _identity(
            project_id,
            paper_id,
            revision,
            section_id,
            "section",
            input_hash,
            provider.name,
            provider.model,
            _configuration({"base_url": provider.base_url, "parameters": provider.parameters}),
        )
    job_id = str(uuid4())
    with Session(engine) as session, session.begin():
        session.add(
            Job(
                id=job_id,
                project_id=project_id,
                kind=TASK_KIND,
                payload={
                    "paper_id": paper_id,
                    "document_version_id": revision_id,
                    "request": request,
                    "model_snapshot": {
                        "provider": provider.name,
                        "model": provider.model,
                        "base_url": provider.base_url,
                        "parameters": provider.parameters,
                    },
                    "input_hash": input_hash,
                    "cache_key": key,
                },
                status="queued",
                stage="queued",
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
        )
    return job_id


def test_qa_calls_once_then_hits_cache_without_new_tokens(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id, section_id, _span_id = _fixture()
    provider = CountingProvider(
        json.dumps(
            {
                "answer_zh": "使用共享记忆模块。",
                "evidence_citations": [{"span_id": _span_id, "reason_zh": "方法描述"}],
                "insufficient_evidence": False,
            }
        )
    )
    first = _job(engine, provider, project_id, paper_id, revision_id, section_id)
    second = _job(engine, provider, project_id, paper_id, revision_id, section_id)
    asyncio.run(execute_qa(engine, first, tmp_path, provider=provider))
    asyncio.run(execute_qa(engine, second, tmp_path, provider=provider))
    with Session(engine) as session:
        rows = session.scalars(select(LiteQARecord).order_by(LiteQARecord.created_at)).all()
        assert [row.status for row in rows] == ["COMPLETED", "COMPLETED"]
        assert rows[1].cache_hit is True
        usage = session.scalars(
            select(LiteTokenUsage).where(LiteTokenUsage.task_kind == TASK_KIND)
        ).all()
        assert sum(1 for item in usage if item.cache_hit) == 1
        assert session.query(LiteCacheEntry).count() == 1
    assert provider.calls == 1


def test_no_retrieval_returns_insufficient_without_provider_call(tmp_path: Path) -> None:
    engine, _project_id, paper_id, revision_id, section_id, _span_id = _fixture()
    provider = CountingProvider("not called")
    app = FastAPI()
    register_qa_api(app, lambda: engine, tmp_path)
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/papers/{paper_id}/qa/ask",
            json={
                "document_version_id": revision_id,
                "section_id": section_id,
                "scope": "section",
                "question": "unmatchedxyzterm",
                "allow_network": True,
            },
        )
    assert response.status_code == 200
    queued = response.json()
    assert queued["status"] == "PENDING"
    job_id = queued["job_id"]
    asyncio.run(execute_qa(engine, job_id, tmp_path))
    with Session(engine) as session:
        record = session.get(LiteQARecord, queued["id"])
        assert record is not None and record.answer_json["insufficient_evidence"] is True
    assert provider.calls == 0


def test_response_citation_outside_allowed_spans_fails(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id, section_id, _span_id = _fixture()
    provider = CountingProvider(
        json.dumps(
            {
                "answer_zh": "答案",
                "evidence_citations": [{"span_id": "ghost", "reason_zh": "错误"}],
                "insufficient_evidence": False,
            }
        )
    )
    job_id = _job(engine, provider, project_id, paper_id, revision_id, section_id)
    asyncio.run(execute_qa(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as session:
        record = session.scalar(select(LiteQARecord).where(LiteQARecord.job_id == job_id))
        assert record is not None and record.status == "FAILED"
        assert record.error_code == "QA_GENERATION_FAILED"


def test_qa_route_requires_consent_and_get_is_read_only(tmp_path: Path) -> None:
    engine, _project_id, paper_id, revision_id, section_id, _span_id = _fixture()
    app = FastAPI()
    register_qa_api(app, lambda: engine, tmp_path)
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/papers/{paper_id}/qa/ask",
            json={
                "document_version_id": revision_id,
                "section_id": section_id,
                "scope": "section",
                "question": "What?",
                "allow_network": False,
            },
        )
        assert response.status_code == 409
        assert (
            client.get(
                f"/api/v1/papers/{paper_id}/qa?document_version_id={revision_id}&section_id={section_id}"
            ).json()
            == []
        )


def test_recovery_marks_pending_qa_interrupted(tmp_path: Path) -> None:
    engine, project_id, paper_id, revision_id, section_id, _span_id = _fixture()
    job_id, record_id = str(uuid4()), str(uuid4())
    timestamp = now()
    with Session(engine) as session, session.begin():
        session.add(
            Job(
                id=job_id,
                project_id=project_id,
                kind=TASK_KIND,
                payload={},
                status="running",
                stage="generating",
                attempt=1,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        session.add(
            LiteQARecord(
                id=record_id,
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                section_id=section_id,
                scope="section",
                question="Q",
                source_hash="a" * 64,
                input_hash="b" * 64,
                retrieval_spans_json=[],
                cache_key="c" * 64,
                schema_version=SCHEMA_VERSION,
                prompt_version=PROMPT_VERSION,
                provider_id="p",
                model_id="m",
                status="PENDING",
                job_id=job_id,
                usage_json={},
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        session.add(
            LiteTokenUsage(
                id=str(uuid4()),
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                section_id=section_id,
                task_run_id=job_id,
                task_kind=TASK_KIND,
                status="started",
                created_at=timestamp,
            )
        )
    assert recover_qa(engine) == 1
    with Session(engine) as session:
        assert session.get(Job, job_id).status == "interrupted"
        assert session.get(LiteQARecord, record_id).error_code == "INTERRUPTED"
