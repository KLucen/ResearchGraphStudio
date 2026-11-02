"""Documented endpoint/model adapters, never alias-only capability guesses."""

from typing import Any
from urllib.parse import urlsplit

from researchgraph.model_capabilities import ModelCapabilities

TENCENT_DEEPSEEK = "tencent-deepseek-v41-structured-v1"


def tencent_deepseek(base_url: str, model: str) -> bool:
    parsed = urlsplit(base_url)
    return (
        parsed.scheme == "https"
        and parsed.hostname
        in {
            "tokenhub.tencentmaas.com",
            "tokenhub-intl.tencentmaas.com",
            "tokenhub.tencentcloudmaas.com",
            "tokenhub-intl.tencentcloudmaas.com",
        }
        and parsed.path.rstrip("/") in {"/plan/v3", "/v1"}
        and model in {"deepseek-v4.1-flash", "deepseek-v4.1-flash-1017"}
    )


def documented_capabilities(base_url: str, model: str) -> ModelCapabilities:
    if tencent_deepseek(base_url, model):
        # Tencent 78934: context/input 1M, output 384K. Reserve using a conservative
        # decimal million; DeepSeek's API explicitly defines 384K as 393216.
        return ModelCapabilities(
            context_window=1_000_000,
            max_output_tokens=393216,
            source="tencent_documentation_2026-11-02",
        )
    return ModelCapabilities()


def new_task_parameters(
    base_url: str, model: str, parameters: dict[str, Any], role: str
) -> dict[str, Any]:
    if not tencent_deepseek(base_url, model):
        return parameters
    result = {**parameters, "adapter_policy": TENCENT_DEEPSEEK}
    if result.get("reasoning_effort") is None:
        result["reasoning_effort"] = "none" if role == "extraction" else "high"
    return result


def with_documented_limits(
    base_url: str, model: str, capabilities: ModelCapabilities
) -> ModelCapabilities:
    documented = documented_capabilities(base_url, model)
    if documented.source == "provider_default" or (
        capabilities.max_output_tokens and capabilities.context_window
    ):
        return capabilities
    return ModelCapabilities(
        max_output_tokens=capabilities.max_output_tokens or documented.max_output_tokens,
        context_window=capabilities.context_window or documented.context_window,
        source=documented.source
        if capabilities.source == "provider_default"
        else f"{capabilities.source}+{documented.source}",
    )


def adapt_request(
    base_url: str, model: str, parameters: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    if parameters.get("adapter_policy") != TENCENT_DEEPSEEK or not tencent_deepseek(
        base_url, model
    ):
        return {}
    effort = parameters.get("reasoning_effort")
    thinking = effort != "none"
    effective = "max" if effort in {"max", "xhigh"} else "high"
    body.pop("reasoning_effort", None)
    body["thinking"] = (
        {"type": "enabled", "reasoning_effort": effective} if thinking else {"type": "disabled"}
    )
    if thinking:
        body.pop("response_format", None)
    # The provider has already reserved input context and applied the endpoint's
    # actual output ceiling. Do not introduce a second, smaller arbitrary cap.
    return {
        "adapter_policy": TENCENT_DEEPSEEK,
        "effective_thinking": body["thinking"],
        "request_output_budget": body.get("max_tokens", body.get("max_completion_tokens")),
        "json_mode_sent": "response_format" in body,
    }
