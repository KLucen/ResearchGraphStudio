"""Model-specific limits from the configured endpoint, never inferred from an alias."""

from typing import Any

from pydantic import Field

from researchgraph.core import StrictModel


class ModelCapabilities(StrictModel):
    max_output_tokens: int | None = Field(default=None, ge=128, le=2_000_000)
    context_window: int | None = Field(default=None, ge=1024, le=10_000_000)
    source: str = "provider_default"


def parse_capabilities(value: dict[str, Any]) -> ModelCapabilities:
    containers = [value]
    for key in ("capabilities", "limits", "top_provider"):
        if isinstance(value.get(key), dict):
            containers.append(value[key])

    def number(names: tuple[str, ...], low: int, high: int) -> int | None:
        for container in containers:
            for name in names:
                result = container.get(name)
                if type(result) is int and low <= result <= high:
                    return result
        return None

    output = number(
        ("max_output_tokens", "max_completion_tokens", "output_token_limit"), 128, 2_000_000
    )
    context = number(("context_window", "context_length", "max_context_tokens"), 1024, 10_000_000)
    return ModelCapabilities(
        max_output_tokens=output,
        context_window=context,
        source="endpoint_metadata" if output or context else "provider_default",
    )
