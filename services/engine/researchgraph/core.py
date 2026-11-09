"""Small shared contracts and deterministic identities for the Lite engine."""

import hashlib
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def stable_id(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"researchgraph-lite/{kind}/{value}"))
