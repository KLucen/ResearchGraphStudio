"""Require numeric literals in new comparisons to occur in their selected quotes."""

import re
import unicodedata
from collections.abc import Iterable

from researchgraph.core import KnowledgeError

# Dataset labels such as GPT4 and citation ref IDs are not numeric claims. Keep
# adjacent signed values, exponent notation and % units distinct. CJK text may
# sit immediately next to a number.
_NUMBER = re.compile(
    r"(?<![A-Za-z0-9_.])[-+]?"
    r"(?:[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
    r"(?:[eE][-+]?[0-9]+)?(?![0-9])(?:[ \t]*(?:%|‰|个百分点))?"
)


def number_literals(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).replace("−", "-")
    return {re.sub(r"[ \t,]", "", match.group()).lower() for match in _NUMBER.finditer(normalized)}


def require_numbers_in_quotes(texts: Iterable[str | None], quotes: set[str]) -> None:
    if any(number_literals(text) - quotes for text in texts if text):
        raise KnowledgeError(
            "KNOWLEDGE_CONNECTION_NUMBER_UNSUPPORTED",
            "联系中的数字在所选引文中没有对应，无法保存该批分析；原始响应保留在本机",
        )
