"""Capacity uses a token estimate while retaining byte size for transport audit."""

import json

import pytest
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.providers import ConfiguredProvider, ProviderError
from researchgraph.token_estimates import estimate_tokens


def provider(*, context: int, output: int | None) -> ConfiguredProvider:
    result = ConfiguredProvider(base_url="https://model.example/v1", model="synthetic")
    result.capabilities = ModelCapabilities(context_window=context, max_output_tokens=output)
    return result


def test_long_ascii_input_is_not_charged_one_token_per_byte():
    active = provider(context=8192, output=2048)
    source = "A scientific statement. " * 650
    body = active._build_body("Return JSON", {"source": source}, {"type": "object"})
    messages = json.dumps(body["messages"], ensure_ascii=False)
    assert len(messages.encode()) > 8192
    assert active.request_metadata["input_token_estimate"] == estimate_tokens(messages)
    assert active.request_metadata["input_token_estimate"] + body["max_tokens"] + 512 <= 8192
    assert body["max_tokens"] >= 2048
    assert source in body["messages"][1]["content"]


def test_unlimited_task_output_keeps_endpoint_ceiling_and_remaining_context():
    active = provider(context=4096, output=8192)
    active.task_output_budget = None
    body = active._build_body("Return JSON", {"source": "论文材料" * 90}, {})
    estimate = active.request_metadata["input_token_estimate"]
    assert body["max_tokens"] == 4096 - estimate - 512
    assert active.request_metadata["input_bytes"] > estimate


@pytest.mark.parametrize("output", [None, 8192])
def test_known_context_still_rejects_oversized_input_without_task_budget(output):
    active = provider(context=2048, output=output)
    with pytest.raises(ProviderError) as caught:
        active._build_body("Return JSON", {"source": "source text " * 1200}, {})
    assert caught.value.category == "context_limit"


def test_unknown_output_capacity_does_not_invent_a_provider_limit():
    active = provider(context=8192, output=None)
    body = active._build_body("Return JSON", {}, {})
    assert "max_tokens" not in body
    assert active.request_metadata["output_limit"] is None
