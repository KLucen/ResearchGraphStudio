from pathlib import Path
import importlib.util
import sys
import pytest

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lite_contracts", root / "schemas" / "contracts.py")
contracts = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = contracts
spec.loader.exec_module(contracts)


def supported(text="example", sid="sp-1"):
    return {"text_zh": text, "evidence_span_ids": [sid], "status": "supported"}


def card_data():
    return {
        "research_question": supported("研究问题"),
        "motivation": supported("研究动机"),
        "method": supported("方法"),
        "contributions": [supported("贡献")],
        "results": [supported("结果")],
        "limitations": [{"text_zh": "", "evidence_span_ids": [], "status": "not_found"}],
        "overall_note": "只覆盖部分原文",
    }


def test_valid_card_and_citations():
    obj = contracts.PaperCardDraft.model_validate(card_data())
    contracts.validate_references(obj, {"sp-1"})


def test_unknown_card_reference_rejected():
    obj = contracts.PaperCardDraft.model_validate(card_data())
    with pytest.raises(ValueError, match="outside"):
        contracts.validate_references(obj, {"sp-other"})


def test_supported_without_evidence_rejected():
    data = card_data()
    data["method"]["evidence_span_ids"] = []
    with pytest.raises(Exception):
        contracts.PaperCardDraft.model_validate(data)


def test_not_found_does_not_fake_evidence():
    data = card_data()
    data["limitations"][0]["evidence_span_ids"] = ["sp-1"]
    with pytest.raises(Exception):
        contracts.PaperCardDraft.model_validate(data)


def test_guide_section_scope_validation():
    guide = contracts.ReadingGuideDraft(
        section_id="s-2", overview_zh="本节阐述方法",
        key_points=["表示", "计算"], reading_questions=["输入是什么?", "怎么验证?"],
        evidence_span_ids=["sp-1"],
    )
    with pytest.raises(ValueError, match="section_id"):
        contracts.validate_references(guide, {"sp-1"}, requested_section_id="s-1")
    contracts.validate_references(guide, {"sp-1"}, requested_section_id="s-2")


def test_qa_must_cite_if_confident():
    with pytest.raises(Exception):
        contracts.QAAnswerDraft(answer_zh="确定如此", insufficient_evidence=False)


def test_qa_can_abstain():
    result = contracts.QAAnswerDraft(
        answer_zh="当前片段不足以回答", insufficient_evidence=True,
        suggest_expand_scope=True,
    )
    contracts.validate_references(result, set())


def test_qa_fabricated_citation_rejected():
    result = contracts.QAAnswerDraft(
        answer_zh="原文给出答案", insufficient_evidence=False,
        evidence_citations=[{"span_id": "ghost", "reason_zh": "定义"}],
    )
    with pytest.raises(ValueError, match="outside"):
        contracts.validate_references(result, {"sp-1"})


def test_allowed_span_pages_order():
    with pytest.raises(Exception):
        contracts.AllowedSpan(
            span_id="sp-1", document_version_id="dv-1", section_id="sec-1",
            text_en="source", page_start=3, page_end=1,
        )


def test_token_usage_provider_requires_counts():
    with pytest.raises(Exception):
        contracts.TokenUsage(task_run_id="run-1", model_id="m1", usage_source="provider")


def test_cache_key_is_stable_and_versioned():
    a = {"task": "guide", "document_version_id": "dv1", "prompt_version": "A01.v1"}
    b = {"prompt_version": "A01.v1", "document_version_id": "dv1", "task": "guide"}
    c = {**a, "document_version_id": "dv2"}
    assert contracts.compute_cache_key(a) == contracts.compute_cache_key(b)
    assert contracts.compute_cache_key(a) != contracts.compute_cache_key(c)


def test_extras_disallowed():
    data = card_data()
    data["pretend_truth"] = True
    with pytest.raises(Exception):
        contracts.PaperCardDraft.model_validate(data)
