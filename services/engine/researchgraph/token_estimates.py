"""Conservative local token estimates for capacity planning, never billed usage."""


def estimate_tokens(serialized: str) -> int:
    """Estimate mixed scientific text without treating UTF-8 bytes as tokens.

    This deliberately reserves about one token per three ASCII characters and
    two per non-ASCII character. It is not a model-specific tokenizer; endpoint
    token usage remains authoritative after an actual request.
    """
    return max(1, (sum(1 if ord(char) < 128 else 6 for char in serialized) + 2) // 3)
