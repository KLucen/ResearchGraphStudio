"""Knowledge budget arithmetic: null removes a software cap, not endpoint capacity."""

import json
from typing import Any

from researchgraph.token_estimates import estimate_tokens

MINIMUM_KNOWLEDGE_OUTPUT_TOKENS = 2048


def stricter_limit(first: int | None, second: int | None) -> int | None:
    """Intersect two optional caps while retaining null as unbounded."""
    if first is None:
        return second
    if second is None:
        return first
    return min(first, second)


def estimate_knowledge_input_tokens(
    prompt: str, data: dict[str, Any], schema: dict[str, Any]
) -> int:
    """Include instructions and schema in the same planning estimate as source text."""
    return estimate_tokens(
        json.dumps({"prompt": prompt, "data": data, "schema": schema}, ensure_ascii=False)
    )
