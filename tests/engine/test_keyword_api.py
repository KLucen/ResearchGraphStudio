import asyncio
from uuid import uuid4

from researchgraph.keyword_api import (
    _configuration,
    _hash,
    _identity,
    build_keyword_input,
    execute_keyword_expansion,
)
from researchgraph.keyword_contracts import KeywordGenerate
from researchgraph.keyword_models import LiteKeywordRecord
from researchgraph.lite_models import LiteTokenUsage
from researchgraph.models import AttachmentRevision, Base, Job, Paper, Project, Section, now
from sqlalchemy import create_engine, select
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
        self.usage = {"prompt_tokens": 18, "completion_tokens": 7, "total_tokens": 25}
        self.request_metadata: dict[str, object] = {}

    async def complete(self, prompt: str, data: dict, schema: dict) -> str:
        self.calls += 1
        assert set(data) == {"question", "paper_title", "section_heading"}
        assert "allowed_spans" not in data
        assert "PDF" not in str(data)
        return self.response


def _fixture() -> tuple[Engine, str, str, str, str]:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    import researchgraph.keyword_models  # noqa: F401
    import researchgraph.lite_models  # noqa: F401

    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id, section_id = (str(uuid4()) for _ in range(4))
    timestamp = now()
    with Session(engine) as session, session.begin():
        session.add(
            Project(
                id=project_id,
                name="keyword",
                description="lite",
                experience_mode="lite",
                created_at=timestamp,
            )
        )
        session.add(
            Paper(
                id=paper_id, project_id=project_id, title="Sparse Retrieval", created_at=timestamp
            )
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
    return engine, project_id, paper_id, revision_id, section_id


def test_build_keyword_input_excludes_document_text() -> None:
    engine, _project, paper_id, revision_id, section_id = _fixture()
    with Session(engine) as session:
        paper = session.get(Paper, paper_id)
        revision = session.get(AttachmentRevision, revision_id)
        section = session.get(Section, section_id)
        assert paper is not None and revision is not None
        context = build_keyword_input(session, paper, revision, section, "方法是什么？")
    assert set(context) == {"question", "paper_title", "section_heading"}


def test_keyword_worker_records_usage_and_cache() -> None:
    engine, project_id, paper_id, revision_id, section_id = _fixture()
    provider = CountingProvider('{"english_queries":["sparse retrieval","method"]}')
    request = KeywordGenerate(
        document_version_id=revision_id,
        section_id=section_id,
        question="方法是什么？",
        allow_network=True,
    )
    snapshot = {
        "provider": provider.name,
        "model": provider.model,
        "base_url": provider.base_url,
        "parameters": provider.parameters,
    }
    with Session(engine) as session, session.begin():
        paper = session.get(Paper, paper_id)
        revision = session.get(AttachmentRevision, revision_id)
        section = session.get(Section, section_id)
        assert paper is not None and revision is not None
        context = build_keyword_input(session, paper, revision, section, request.question)
        key, identity = _identity(
            project_id,
            paper_id,
            revision,
            section_id,
            _hash(context),
            provider.name,
            provider.model,
            _configuration(snapshot),
        )
        job = Job(
            id=str(uuid4()),
            project_id=project_id,
            kind="search_keywords",
            payload={
                "paper_id": paper_id,
                "document_version_id": revision_id,
                "request": request.model_dump(),
                "allow_network": True,
                "model_snapshot": {
                    "provider": provider.name,
                    "model": provider.model,
                    "base_url": provider.base_url,
                    "parameters": provider.parameters,
                },
                "input_hash": _hash(context),
                "cache_key": key,
            },
            status="queued",
            stage="queued",
            attempt=0,
            created_at=now(),
            updated_at=now(),
        )
        session.add(job)
        job_id = job.id
    asyncio.run(
        execute_keyword_expansion(
            engine, job_id, __import__("pathlib").Path("."), provider=provider
        )
    )
    assert provider.calls == 1
    with Session(engine) as session:
        row = session.scalar(select(LiteKeywordRecord).where(LiteKeywordRecord.job_id == job_id))
        assert row is not None and row.status == "COMPLETED", (
            row.error_code,
            row.error,
            row.raw_output,
        )
        assert row.keywords_json == {"english_queries": ["sparse retrieval", "method"]}
        usage = session.scalar(select(LiteTokenUsage).where(LiteTokenUsage.task_run_id == job_id))
        assert usage is not None and usage.total_tokens == 25
