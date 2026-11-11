import json

import pytest
from pydantic import ValidationError
from researchgraph.qa_contracts import QAAnswerDraft, QAGenerate, validate_response


def test_supported_answer_requires_citation() -> None:
    with pytest.raises(ValidationError):
        QAAnswerDraft(answer_zh="有结论", insufficient_evidence=False)


def test_citations_must_stay_inside_allowed_spans() -> None:
    raw = json.dumps(
        {
            "answer_zh": "原文支持该结论。",
            "evidence_citations": [{"span_id": "ghost", "reason_zh": "支持"}],
            "insufficient_evidence": False,
        }
    )
    with pytest.raises(ValueError, match="outside this request"):
        validate_response(raw, allowed_span_ids={"sp-1"})


def test_question_scope_defaults_and_selection_is_explicit() -> None:
    request = QAGenerate(question="What is the method?")
    assert request.scope == "section"
    with pytest.raises(ValidationError):
        QAGenerate(question="Q", scope="selection")
