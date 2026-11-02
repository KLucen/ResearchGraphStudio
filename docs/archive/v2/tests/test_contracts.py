import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'schemas'))
from contracts import Condition, ExtractionBatch, RelationInference  # noqa: E402


def test_reference_extraction_fixture():
    payload = json.loads((ROOT / 'examples/extraction_batch.example.json').read_text(encoding='utf-8'))
    assert len(ExtractionBatch.model_validate(payload).claims) == 1


def test_reference_no_decision_fixture():
    payload = json.loads((ROOT / 'examples/relation_inference.example.json').read_text(encoding='utf-8'))
    assert RelationInference.model_validate(payload).relation_type is None


def test_invalid_relation_decision_rejected():
    with pytest.raises(ValidationError):
        RelationInference(source_claim_id='a', target_claim_id='b', decision='NO_DECISION',
                          relation_type='CONTRADICTS', reason='test')


def test_known_condition_requires_evidence():
    with pytest.raises(ValidationError):
        Condition(dimension='agent_count', value='3', known_state='known', evidence_span_ids=[])


def test_unknown_cannot_claim_value():
    with pytest.raises(ValidationError):
        Condition(dimension='agent_count', value='3', known_state='unknown', evidence_span_ids=[])
