import json

import pytest
from pydantic import ValidationError
from researchgraph.keyword_contracts import KeywordGenerate, SearchKeywordsDraft, validate_response


def test_keyword_contract_is_short_unique_and_bounded() -> None:
    result = SearchKeywordsDraft(english_queries=["  Sparse   attention ", "retrieval"])
    assert result.english_queries == ["Sparse attention", "retrieval"]
    with pytest.raises(ValidationError):
        SearchKeywordsDraft(english_queries=["retrieval", " RETRIEVAL "])


def test_keyword_request_requires_local_miss_and_explicit_network_consent() -> None:
    request = KeywordGenerate(question="方法是什么？")
    assert request.local_hit_count == 0
    assert request.allow_network is False
    with pytest.raises(ValidationError):
        KeywordGenerate(question="方法是什么？", local_hit_count=1)


def test_keyword_response_rejects_duplicate_keys_and_unknown_fields() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        validate_response('{"english_queries":["method"],"english_queries":["model"]}')
    with pytest.raises(ValidationError):
        validate_response(json.dumps({"english_queries": ["method"], "answer": "no"}))
