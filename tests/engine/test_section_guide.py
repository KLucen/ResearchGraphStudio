from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

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
)
from researchgraph.section_guide_api import (
    SYSTEM_PROMPT,
    _configuration,
    _hash,
    _identity,
    _model_context,
    build_guide_input,
    execute_section_guide,
)
from researchgraph.section_guide_contracts import (
    TASK_KIND,
    guide_schema,
    validate_response,
)
from researchgraph.section_guide_models import SectionGuideResult
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


class CountingProvider:
    name = "test"
    model = "guide-test"
    usage = {"prompt_tokens": 42, "completion_tokens": 18, "total_tokens": 60}
    calls = 0

    async def complete(self, prompt, data, schema):
        assert prompt == SYSTEM_PROMPT
        assert schema["title"] == "ReadingGuideDraft"
        assert data["allowed_spans"]
        assert set(data) == {
            "paper_title",
            "section_id",
            "section_heading",
            "depth",
            "allowed_spans",
        }
        self.calls += 1
        span_id = data["allowed_spans"][0]["span_id"]
        return json.dumps(
            {
                "section_id": data["section_id"],
                "overview_zh": "说明当前小节的作用。",
                "key_points": ["关注方法与目的"],
                "reading_questions": ["该节解决什么问题？", "证据如何支持结论？"],
                "evidence_span_ids": [span_id],
                "needs_more_context": False,
                "caveats": [],
            },
            ensure_ascii=False,
        )


def _fixture() -> tuple[object, str, str, str, str]:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id, section_id, chunk_id, span_id = (
        str(uuid4()) for _ in range(6)
    )
    with Session(engine) as session, session.begin():
        session.add(
            Project(
                id=project_id,
                name="guide",
                description="test",
                experience_mode="lite",
                created_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            Paper(
                id=paper_id,
                project_id=project_id,
                title="A guide paper",
                created_at="2026-01-01T00:00:00Z",
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
                created_at="2026-01-01T00:00:00Z",
            )
        )
        session.add(
            Chunk(
                id=chunk_id,
                revision_id=revision_id,
                page_index=0,
                page_label="1",
                block_index=0,
                text="The method section explains the experiment.",
                bbox=[0, 0, 1, 1],
            )
        )
        session.add(
            Section(
                id=section_id,
                document_version_id=revision_id,
                title="Methods",
                ordinal=0,
                role="method",
                parser="test",
                parent_id=None,
                level=0,
                start_page=0,
                end_page=0,
                excluded=False,
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
                end_offset=45,
                quote="The method section explains the experiment.",
                text_sha256="b" * 64,
                normalization="identity-v1",
                bbox_list=[[0, 0, 1, 1]],
            )
        )
    return engine, project_id, paper_id, revision_id, section_id


def _job(engine, project_id, paper_id, revision_id, section_id, depth="standard"):
    with Session(engine) as session:
        paper = session.get(Paper, paper_id)
        revision = session.get(AttachmentRevision, revision_id)
        section = session.get(Section, section_id)
        spans = list(session.query(EvidenceSpan).filter_by(section_id=section_id).all())
        context = build_guide_input(session, paper, revision, section, None, spans, depth)
        input_hash = _hash(context)
        key, identity = _identity(
            project_id,
            paper_id,
            revision,
            section_id,
            depth,
            input_hash,
            "test",
            "guide-test",
            _configuration({"base_url": "", "parameters": {}}),
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
                    "section_id": section_id,
                    "depth": depth,
                    "allow_network": True,
                    "input_hash": input_hash,
                    "cache_key": key,
                    "model_snapshot": {
                        "provider": "test",
                        "model": "guide-test",
                        "base_url": "",
                        "parameters": {},
                    },
                },
                status="queued",
                stage="queued",
                attempt=0,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
        )
    return job_id


def test_contract_rejects_unknown_evidence_and_accepts_defaults():
    raw = '{"section_id":"s","overview_zh":"x","key_points":["a"],"reading_questions":["q1","q2"]}'
    guide = validate_response(
        raw, requested_section_id="s", allowed_span_ids=set(), depth="standard"
    )
    assert guide.difficult_terms == []
    assert guide.needs_more_context is False
    assert guide_schema()["required"] == [
        "section_id",
        "overview_zh",
        "key_points",
        "reading_questions",
    ]


def test_section_guide_generation_and_cache_hit(tmp_path: Path):
    engine, project_id, paper_id, revision_id, section_id = _fixture()
    provider = CountingProvider()
    first = _job(engine, project_id, paper_id, revision_id, section_id)
    asyncio.run(execute_section_guide(engine, first, tmp_path, provider=provider))
    second = _job(engine, project_id, paper_id, revision_id, section_id)
    asyncio.run(execute_section_guide(engine, second, tmp_path, provider=provider))
    with Session(engine) as session:
        rows = session.query(SectionGuideResult).order_by(SectionGuideResult.created_at).all()
        assert provider.calls == 1
        assert len(rows) == 2
        assert all(row.status == "COMPLETED" for row in rows)
        assert session.query(LiteCacheEntry).count() == 1
        usage = session.query(LiteTokenUsage).all()
        assert len(usage) == 2
        assert sum(item.cache_hit is False for item in usage) == 1


def test_model_context_projects_only_the_published_input_contract():
    context = {
        "paper_title": "Paper",
        "section_id": "section",
        "section_heading": "Methods",
        "parent_heading": "Parent",
        "depth": "standard",
        "allowed_spans": [{"span_id": "span"}],
        "source_truncated": True,
    }
    assert _model_context(context) == {
        "paper_title": "Paper",
        "section_id": "section",
        "section_heading": "Methods",
        "depth": "standard",
        "allowed_spans": [{"span_id": "span"}],
    }
