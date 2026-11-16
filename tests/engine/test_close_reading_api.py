import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.close_reading_api import (
    _budget,
    _complete_validation,
    _configuration,
    _hash,
    _identity,
    _row_is_stale,
    build_reading_input,
    execute_close_reading,
    execute_understanding_check,
    recover_close_reading,
    register_close_reading_api,
)
from researchgraph.close_reading_contracts import (
    CHECK_TASK_KIND,
    SCHEMA_VERSION,
    TASK_KIND,
    UnderstandingCheckGenerate,
    validate_analysis,
)
from researchgraph.close_reading_models import SectionCloseReadingResult, UnderstandingCheckResult
from researchgraph.core import KnowledgeError, text_hash
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
from researchgraph.paper_overview_models import PaperOverviewResult
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


class CountingProvider:
    name = "synthetic"
    model = "fixture-model"
    base_url = "https://provider.test/v1"
    parameters: dict = {}

    def __init__(self, response: str, before_return=None, *, usage=True):
        self.response, self.before_return, self.calls = response, before_return, 0
        self.usage = (
            {"prompt_tokens": 123, "completion_tokens": 234, "total_tokens": 357} if usage else {}
        )
        self.request_metadata = {}
        self.received = []

    async def complete(self, prompt, data, schema):
        self.calls += 1
        self.received.append((prompt, data, schema))
        if self.before_return:
            self.before_return()
        return self.response


def fixture():
    import researchgraph.model_settings  # noqa: F401
    import researchgraph.reading_state_models  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id, section_id = (str(uuid4()) for _ in range(4))
    paragraph_ids = ["z-first-paragraph", "a-second-paragraph"]
    texts = [
        "The method uses shared memory. Shared memory is updated twice.",
        "We measured 12 samples; the result is preliminary.",
    ]
    with Session(engine) as session, session.begin():
        session.add(
            Project(
                id=project_id,
                name="synthetic",
                description="fixture",
                experience_mode="lite",
                created_at=now(),
            )
        )
        session.add(
            Paper(
                id=paper_id, project_id=project_id, title="Fictional local study", created_at=now()
            )
        )
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="a" * 64,
                parser_version="fixture",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        session.add(
            Section(
                id=section_id,
                document_version_id=revision_id,
                title="Method",
                ordinal=0,
                role="method",
                parser="fixture",
                parent_id=None,
                level=0,
                start_page=0,
                end_page=0,
                excluded=False,
            )
        )
        for ordinal, (paragraph_id, text) in enumerate(zip(paragraph_ids, texts, strict=True)):
            session.add(
                Chunk(
                    id=paragraph_id,
                    revision_id=revision_id,
                    page_index=0,
                    page_label="1",
                    block_index=ordinal,
                    text=text,
                    bbox=[0, 0, 1, 1],
                )
            )
            session.add(
                EvidenceSpan(
                    id=f"span-{ordinal}",
                    document_version_id=revision_id,
                    section_id=section_id,
                    paragraph_id=paragraph_id,
                    page_index=0,
                    start_offset=0,
                    end_offset=len(text),
                    quote=text,
                    text_sha256=text_hash(text),
                    normalization="identity-v1",
                    bbox_list=[[0, 0, 1, 1]],
                )
            )
    return engine, project_id, paper_id, revision_id, section_id, paragraph_ids


def paragraph_result(paragraph_id, **changes):
    return {
        "paragraph_id": paragraph_id,
        "translation_zh": "该方法使用共享记忆，并保留原始限定条件。",
        "paragraph_function": "EXPLAIN_METHOD",
        "logic_role_zh": "说明当前方法的步骤。",
        "critical_note_zh": "",
        "reading_question_zh": None,
        "highlights": [],
        "related_graph_node_ids": [],
        **changes,
    }


def response(ids, **changes):
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "paragraphs": [paragraph_result(item) for item in ids],
            "section_argument": {
                "logic_chain_zh": ["介绍方法", "报告有限结果"],
                "core_claim_zh": "当前范围介绍方法。",
                "strong_point_zh": None,
                "question_to_verify_zh": "需要核查更多样本。",
            },
            **changes,
        },
        ensure_ascii=False,
    )


def job_for(values, provider, *, ids=None, is_check=False, options=None, retry_of=None, allow=True):
    engine, project_id, paper_id, revision_id, section_id, all_ids = values
    ids = ids or all_ids
    with Session(engine) as session, session.begin():
        paper, revision, context = build_reading_input(
            session,
            paper_id,
            revision_id,
            section_id,
            ids,
            check_options=options if is_check else None,
        )
        key, _ = _identity(
            project_id,
            paper_id,
            revision,
            section_id,
            _hash(context),
            provider.name,
            provider.model,
            _configuration(
                {"base_url": provider.base_url, "parameters": provider.parameters},
                is_check=is_check,
            ),
            is_check=is_check,
        )
        job_id = str(uuid4())
        session.add(
            Job(
                id=job_id,
                project_id=project_id,
                kind=CHECK_TASK_KIND if is_check else TASK_KIND,
                payload={
                    "paper_id": paper_id,
                    "document_version_id": revision_id,
                    "section_id": section_id,
                    "paragraph_ids": ids,
                    "input_hash": _hash(context),
                    "cache_key": key,
                    "allow_network": allow,
                    "check_options": options,
                    "retry_of": retry_of,
                },
                status="queued",
                stage="queued",
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
        )
    return job_id


def app_for(values):
    app = FastAPI()
    register_close_reading_api(app, lambda: values[0], Path("unused"))
    return TestClient(app)


def test_local_paragraphs_preserve_reading_order_and_never_call_models():
    values = fixture()
    client = app_for(values)
    result = client.get(f"/api/v1/papers/{values[2]}/sections/{values[4]}/paragraphs")
    assert result.status_code == 200
    assert [item["paragraph_id"] for item in result.json()["paragraphs"]] == values[5]
    with Session(values[0]) as session:
        assert session.query(Job).count() == session.query(LiteTokenUsage).count() == 0


def test_a02_single_call_cache_restore_and_actual_usage(tmp_path):
    values = fixture()
    provider = CountingProvider(response(values[5]))
    first = job_for(values, provider)
    second = job_for(values, provider)
    asyncio.run(execute_close_reading(values[0], first, tmp_path, provider=provider))
    asyncio.run(execute_close_reading(values[0], first, tmp_path, provider=provider))
    asyncio.run(execute_close_reading(values[0], second, tmp_path, provider=provider))
    assert provider.calls == 1
    assert "英文全文" in provider.received[0][0]
    assert "text_en" in provider.received[0][1]["paragraphs"][0]
    with Session(values[0]) as session:
        rows = session.scalars(
            select(SectionCloseReadingResult).order_by(SectionCloseReadingResult.created_at)
        ).all()
        assert [row.status for row in rows] == ["COMPLETED", "COMPLETED"]
        assert rows[0].usage_json["total_tokens"] == 357
        assert rows[0].usage_json["cost"] is None
        assert rows[1].cache_hit
        assert session.query(LiteCacheEntry).count() == 1
        ledger = session.scalars(select(LiteTokenUsage)).all()
        assert len(ledger) == 2 and sum(not row.cache_hit for row in ledger) == 1
    client = app_for(values)
    restored = client.get(
        f"/api/v1/papers/{values[2]}/sections/{values[4]}/close-reading",
        params={"paragraph_ids": ",".join(values[5])},
    ).json()
    assert restored["status"] == "COMPLETED" and restored["new_calls"] == 0
    assert len(restored["analysis"]["paragraphs"]) == 2
    assert provider.calls == 1


def test_highlight_invalid_occurrence_and_graph_id_drop_without_losing_translation():
    sources = [{"paragraph_id": "p", "text_en": "memory and memory"}]
    raw = response(
        ["p"],
        paragraphs=[
            paragraph_result(
                "p",
                highlights=[
                    {"type": "CONCEPT", "quote_en": "memory", "occurrence_index": 1},
                    {"type": "THESIS", "quote_en": "invented", "occurrence_index": 0},
                    {"type": "METHOD", "quote_en": "memory", "occurrence_index": True},
                ],
                related_graph_node_ids=["n1", "unknown"],
            )
        ],
    )
    analysis, missing, warnings = validate_analysis(
        raw, paragraphs=sources, allowed_graph_node_ids={"n1"}
    )
    assert not missing and len(analysis.paragraphs[0].highlights) == 1
    assert analysis.paragraphs[0].related_graph_node_ids == ["n1"]
    assert len(warnings) == 2


@pytest.mark.parametrize("bad", [" ", None, 3])
def test_missing_translation_keeps_other_independently_valid_paragraphs(bad):
    raw = response(
        ["p1", "p2"],
        paragraphs=[paragraph_result("p1"), paragraph_result("p2", translation_zh=bad)],
    )
    result, missing, _ = validate_analysis(
        raw,
        paragraphs=[{"paragraph_id": "p1", "text_en": "a"}, {"paragraph_id": "p2", "text_en": "b"}],
        allowed_graph_node_ids=set(),
    )
    assert [item.paragraph_id for item in result.paragraphs] == ["p1"]
    assert missing == ["p2"]


def test_duplicate_paragraph_ids_are_not_arbitrarily_merged():
    raw = response(
        ["p1"],
        paragraphs=[paragraph_result("p1"), paragraph_result("p1", translation_zh="冲突译文")],
    )
    result, missing, _ = validate_analysis(
        raw, paragraphs=[{"paragraph_id": "p1", "text_en": "a"}], allowed_graph_node_ids=set()
    )
    assert not result.paragraphs and missing == ["p1"]


def test_english_source_cannot_be_published_as_chinese_translation():
    raw = response(["p"], paragraphs=[paragraph_result("p", translation_zh=" English  source. ")])
    result, missing, _warnings = validate_analysis(
        raw,
        paragraphs=[{"paragraph_id": "p", "text_en": "English source."}],
        allowed_graph_node_ids=set(),
    )
    assert not result.paragraphs and missing == ["p"]


def test_existing_result_is_revalidated_without_network_or_false_completion(tmp_path):
    values = fixture()
    provider = CountingProvider(response(values[5]))
    job = job_for(values, provider)
    asyncio.run(execute_close_reading(values[0], job, tmp_path, provider=provider))
    with Session(values[0]) as session, session.begin():
        row = session.scalar(select(SectionCloseReadingResult))
        row.analysis_json = {**row.analysis_json, "paragraphs": row.analysis_json["paragraphs"][:1]}
    restored = (
        app_for(values)
        .get(
            f"/api/v1/papers/{values[2]}/sections/{values[4]}/close-reading",
            params={"paragraph_ids": ",".join(values[5])},
        )
        .json()
    )
    assert restored["status"] == "INCOMPLETE"
    assert restored["missing_paragraph_ids"] == values[5][1:]
    assert len(restored["analysis"]["paragraphs"]) == 1
    assert provider.calls == 1


def test_reordered_paragraphs_are_retained_but_result_is_incomplete():
    context = {
        "paragraphs": [
            {"paragraph_id": "p1", "text_en": "a"},
            {"paragraph_id": "p2", "text_en": "b"},
        ],
        "allowed_graph_nodes": [],
    }
    result, missing, warnings, complete = _complete_validation(
        response(["p2", "p1"]), context, is_check=False
    )
    assert not complete and not missing
    assert [item["paragraph_id"] for item in result["paragraphs"]] == ["p1", "p2"]
    assert "PARAGRAPH_ORDER_NORMALIZED_BY_LOCAL_SOURCE" in warnings


def test_truncated_json_recovers_only_complete_paragraph_objects():
    raw = response(["p1", "p2"])
    raw = raw[: raw.index('"paragraph_id": "p2"') + len('"paragraph_id": "p2"')]
    result, missing, warnings = validate_analysis(
        raw,
        paragraphs=[{"paragraph_id": "p1", "text_en": "a"}, {"paragraph_id": "p2", "text_en": "b"}],
        allowed_graph_node_ids=set(),
    )
    assert [item.paragraph_id for item in result.paragraphs] == ["p1"]
    assert missing == ["p2"] and result.section_argument is None
    assert "RESPONSE_JSON_INCOMPLETE" in warnings


@pytest.mark.parametrize(
    "raw",
    [
        '{"schema_version":"section_reading_analysis.v1","paragraphs":[],"paragraphs":[]}',
        '{"schema_version":"section_reading_analysis.v1","paragraphs":[NaN]}',
    ],
)
def test_duplicate_json_keys_and_nonfinite_values_never_salvaged(raw):
    with pytest.raises(ValueError):
        validate_analysis(
            raw, paragraphs=[{"paragraph_id": "p", "text_en": "a"}], allowed_graph_node_ids=set()
        )


def test_missing_retry_persists_and_restores_original_range_without_promoting_child_summary(
    tmp_path,
):
    values = fixture()
    first_provider = CountingProvider(response(values[5][:1]))
    first_job = job_for(values, first_provider)
    asyncio.run(execute_close_reading(values[0], first_job, tmp_path, provider=first_provider))
    with Session(values[0]) as session:
        parent = session.scalar(select(SectionCloseReadingResult))
        parent_id = parent.id
        assert parent.status == "INCOMPLETE" and parent.missing_paragraph_ids == values[5][1:]
        parent_raw = parent.raw_output
        original_claim = parent.analysis_json["section_argument"]["core_claim_zh"]
    child_provider = CountingProvider(
        response(
            values[5][1:],
            section_argument={
                "logic_chain_zh": ["仅缺失段落", "子范围摘要"],
                "core_claim_zh": "不能冒充原范围的摘要",
                "strong_point_zh": None,
                "question_to_verify_zh": None,
            },
        )
    )
    retry = job_for(values, child_provider, ids=values[5][1:], retry_of=parent_id)
    asyncio.run(execute_close_reading(values[0], retry, tmp_path, provider=child_provider))
    restored = (
        app_for(values)
        .get(
            f"/api/v1/papers/{values[2]}/sections/{values[4]}/close-reading",
            params={"result_id": parent_id},
        )
        .json()
    )
    assert restored["status"] == "COMPLETED" and restored["missing_paragraph_ids"] == []
    assert len(restored["analysis"]["paragraphs"]) == 2
    assert restored["analysis"]["section_argument"]["core_claim_zh"] == original_claim
    assert restored["usage"]["calls"] == 2 and restored["usage"]["retry_count"] == 1
    assert restored["usage"]["total_tokens"] == 714
    with Session(values[0]) as session:
        assert session.get(SectionCloseReadingResult, parent_id).raw_output == parent_raw
        assert session.get(SectionCloseReadingResult, parent_id).status == "INCOMPLETE"


def test_range_budget_and_scope_fail_before_provider(tmp_path):
    values = fixture()
    with Session(values[0]) as session:
        with pytest.raises(KnowledgeError, match="本地阅读顺序"):
            build_reading_input(session, values[2], values[3], values[4], list(reversed(values[5])))
        _p, _r, context = build_reading_input(session, values[2], values[3], values[4], values[5])
    context["paragraphs"][0]["text_en"] = "text " * 2000
    with pytest.raises(KnowledgeError) as raised:
        _budget(context)
    assert raised.value.code == "READING_RANGE_TOO_LARGE"
    client = app_for(values)
    result = client.post(
        f"/api/v1/papers/{values[2]}/sections/{values[4]}/close-reading/generate",
        json={"paragraph_ids": values[5]},
    )
    assert result.status_code == 409
    with Session(values[0]) as session:
        assert session.query(Job).count() == session.query(LiteTokenUsage).count() == 0


def test_source_changed_during_request_preserves_raw_and_usage_without_publishing(tmp_path):
    values = fixture()

    def mutate():
        with Session(values[0]) as session, session.begin():
            text = "Changed original."
            session.get(Chunk, values[5][0]).text = text
            span = session.get(EvidenceSpan, "span-0")
            span.quote, span.end_offset, span.text_sha256 = text, len(text), text_hash(text)

    provider = CountingProvider(response(values[5]), mutate)
    job = job_for(values, provider)
    asyncio.run(execute_close_reading(values[0], job, tmp_path, provider=provider))
    with Session(values[0]) as session:
        row = session.scalar(select(SectionCloseReadingResult))
        assert row.status == "FAILED" and row.error_code == "READING_INPUT_CHANGED"
        assert row.raw_output == provider.response and row.analysis_json is None
        assert row.usage_json["total_tokens"] == 357
        assert session.query(LiteCacheEntry).count() == 0


def test_cancellation_retains_actual_usage_and_never_publishes(tmp_path):
    values = fixture()

    def cancel():
        with Session(values[0]) as session, session.begin():
            session.get(Job, job).status = "cancelled"
            row = session.scalar(select(SectionCloseReadingResult))
            row.status, row.error_code = "FAILED", "CANCELLED"

    provider = CountingProvider(response(values[5]), cancel)
    job = job_for(values, provider)
    asyncio.run(execute_close_reading(values[0], job, tmp_path, provider=provider))
    with Session(values[0]) as session:
        row = session.scalar(select(SectionCloseReadingResult))
        usage = session.scalar(select(LiteTokenUsage))
        assert row.analysis_json is None and row.raw_output == provider.response
        assert row.usage_json["total_tokens"] == 357 and usage.status == "cancelled"
        assert session.query(LiteCacheEntry).count() == 0


def test_unknown_provider_usage_stays_unknown_and_restart_never_resends(tmp_path):
    values = fixture()
    provider = CountingProvider(response(values[5]), usage=False)
    completed = job_for(values, provider)
    pending = job_for(values, provider, ids=values[5][:1])
    asyncio.run(execute_close_reading(values[0], completed, tmp_path, provider=provider))
    assert recover_close_reading(values[0]) == 1
    asyncio.run(execute_close_reading(values[0], pending, tmp_path, provider=provider))
    with Session(values[0]) as session:
        row = session.scalar(select(SectionCloseReadingResult))
        assert (
            row.usage_json["usage_source"] == "unknown" and row.usage_json["input_tokens"] is None
        )
        assert session.get(Job, pending).status == "interrupted"
    assert provider.calls == 1


def test_model_parameters_and_prompt_bytes_change_marks_old_record_stale(tmp_path, monkeypatch):
    import researchgraph.close_reading_api as service
    import researchgraph.model_settings as settings

    values = fixture()
    provider = CountingProvider(response(values[5]))
    job = job_for(values, provider)
    asyncio.run(execute_close_reading(values[0], job, tmp_path, provider=provider))
    snapshot = {
        "provider": provider.name,
        "model": provider.model,
        "base_url": provider.base_url,
        "parameters": provider.parameters,
    }
    monkeypatch.setattr(settings, "snapshot_for", lambda *args: snapshot)
    with Session(values[0]) as session:
        row = session.scalar(select(SectionCloseReadingResult))
        assert not _row_is_stale(session, row)
        snapshot["parameters"] = {"temperature": 0.5}
        assert _row_is_stale(session, row)
        snapshot["parameters"] = provider.parameters
        snapshot["model"] = "a-different-model"
        assert _row_is_stale(session, row)
        snapshot["model"] = provider.model
        monkeypatch.setattr(
            service, "A02_SYSTEM_PROMPT", service.A02_SYSTEM_PROMPT + "Changed prompt bytes."
        )
        assert _row_is_stale(session, row)
    assert provider.calls == 1


def test_missing_retry_waits_for_unrelated_pending_then_links_existing_cache(tmp_path, monkeypatch):
    import researchgraph.model_settings as settings
    from fastapi import HTTPException
    from researchgraph.close_reading_api import _generate, _view
    from researchgraph.close_reading_contracts import CloseReadingGenerate

    values = fixture()
    provider = CountingProvider(response(values[5][:1]))
    parent_job = job_for(values, provider)
    asyncio.run(execute_close_reading(values[0], parent_job, tmp_path, provider=provider))
    with Session(values[0]) as session:
        parent_id = session.scalar(select(SectionCloseReadingResult)).id
    snapshot = {
        "provider": provider.name,
        "model": provider.model,
        "base_url": provider.base_url,
        "parameters": provider.parameters,
    }
    monkeypatch.setattr(settings, "snapshot_for", lambda *args: snapshot)
    missing = values[5][1:]
    independent = _generate(
        values[0],
        values[2],
        values[4],
        CloseReadingGenerate(paragraph_ids=missing, allow_network=True),
        is_check=False,
    )
    with pytest.raises(HTTPException) as raised:
        _generate(
            values[0],
            values[2],
            values[4],
            CloseReadingGenerate(
                paragraph_ids=missing, allow_network=True, retry_missing_of=parent_id
            ),
            is_check=False,
        )
    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "READING_RANGE_ALREADY_RUNNING"
    independent_provider = CountingProvider(response(missing))
    asyncio.run(
        execute_close_reading(
            values[0], independent.job_id, tmp_path, provider=independent_provider
        )
    )
    repair = _generate(
        values[0],
        values[2],
        values[4],
        CloseReadingGenerate(paragraph_ids=missing, allow_network=True, retry_missing_of=parent_id),
        is_check=False,
    )
    asyncio.run(
        execute_close_reading(values[0], repair.job_id, tmp_path, provider=independent_provider)
    )
    with Session(values[0]) as session:
        restored = _view(session, session.get(SectionCloseReadingResult, parent_id))
        assert restored.status == "COMPLETED" and len(restored.analysis.paragraphs) == 2
        assert session.get(SectionCloseReadingResult, repair.id).cache_hit
    assert independent_provider.calls == 1


def test_a03_is_explicit_scoped_cached_and_does_not_overwrite_self_assessment(tmp_path):
    values = fixture()
    payload = {
        "check_result": "PARTIAL",
        "correct_points_zh": ["理解了方法"],
        "missing_or_mistaken_zh": ["遗漏限定条件"],
        "feedback_zh": "请保留作者的限定。",
        "follow_up_question_zh": "适用条件是什么？",
    }
    provider = CountingProvider(json.dumps(payload, ensure_ascii=False))
    options = {
        "user_explanation": "方法会更新共享记忆。",
        "self_assessment": "CONFIDENT",
        "key_points": [],
        "graph_node_ids": [],
        "overview_result_id": None,
    }
    first = job_for(values, provider, is_check=True, options=options)
    second = job_for(values, provider, is_check=True, options=options)
    asyncio.run(execute_understanding_check(values[0], first, tmp_path, provider=provider))
    asyncio.run(execute_understanding_check(values[0], second, tmp_path, provider=provider))
    with Session(values[0]) as session:
        rows = session.scalars(
            select(UnderstandingCheckResult).order_by(UnderstandingCheckResult.created_at)
        ).all()
        assert [row.status for row in rows] == ["COMPLETED", "COMPLETED"]
        assert rows[0].check_json == payload and rows[1].cache_hit
    assert provider.calls == 1
    assert provider.received[0][1]["self_assessment"] == "CONFIDENT"
    assert provider.received[0][1]["key_points"] == []


def test_unrelated_current_graph_concept_cannot_be_updated_by_a03():
    from researchgraph.close_reading_api import _check_options

    values = fixture()
    overview_id = str(uuid4())
    with Session(values[0]) as session, session.begin():
        session.add(
            PaperOverviewResult(
                id=overview_id,
                project_id=values[1],
                paper_id=values[2],
                document_version_id=values[3],
                pdf_hash="a" * 64,
                input_hash="b" * 64,
                cache_key="c" * 64,
                schema_version="paper_overview_graph.v1",
                prompt_version="fixture",
                provider_id="synthetic",
                model_id="fixture",
                status="COMPLETED",
                graph_json={
                    "nodes": [
                        {
                            "id": "n1",
                            "type": "METHOD",
                            "label_en": "unrelated concept",
                            "label_zh": "无关概念",
                        }
                    ],
                    "edges": [],
                },
                request_metadata={},
            )
        )
    with Session(values[0]) as session:
        body = UnderstandingCheckGenerate(
            paragraph_ids=values[5],
            user_explanation="一个解释",
            graph_node_ids=["n1"],
            overview_result_id=overview_id,
            allow_network=True,
        )
        with pytest.raises(KnowledgeError) as raised:
            _check_options(session, values[2], values[3], values[4], body)
        assert raised.value.code == "CHECK_CONCEPT_UNRELATED"
        assert session.query(LiteTokenUsage).count() == 0
