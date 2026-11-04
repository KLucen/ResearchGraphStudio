"""Versioned compact model output, expanded losslessly into the unchanged Store DTO."""

import copy
from typing import Any

from researchgraph.reading_contracts import KnowledgeExtractionBatch

LEGACY_PROMPT = "P02_reading_extract_compact"
PROMPT = "P02_reading_extract_compact_v3"
FORMAT = "reading-compact-1"
SUMMARY_SOURCE = {"Claim": "statement", "Finding": "result", "Experiment": "protocol"}


def output_schema() -> dict[str, Any]:
    schema = KnowledgeExtractionBatch.model_json_schema()
    schema["properties"].update(
        wire_format={"type": "string", "const": FORMAT},
        source_language={"type": "string", "minLength": 2, "maxLength": 35},
    )
    schema["required"] += ["wire_format", "source_language"]
    text = schema["$defs"]["SourceText"]
    text["required"].remove("language")
    text["properties"]["language"]["description"] = "Omit only when equal to source_language."
    schema["$defs"]["SourceText"] = {
        "anyOf": [text, {"type": "string", "minLength": 1}],
        "description": (
            "A string is the exact original text in source_language, without a Chinese translation."
        ),
    }
    for kind, source in SUMMARY_SOURCE.items():
        candidate = schema["$defs"][kind + "Candidate"]
        candidate["required"].remove("summary")
        candidate["properties"]["summary"]["description"] = (
            f"Omit when identical to {source}; include when it adds distinct information."
        )

    def remove_titles(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("title", None)
            for child in value.values():
                remove_titles(child)
        elif isinstance(value, list):
            for child in value:
                remove_titles(child)

    remove_titles(schema)
    schema["title"] = "KnowledgeExtractionBatch"
    return schema


def current_output_schema() -> dict[str, Any]:
    schema = output_schema()
    # Missing arrays are malformed responses, not a successful empty extraction.
    schema["required"] += ["items", "links"]
    return schema


def expand(data: dict[str, Any], changes: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Only specified defaults are filled; unknown fields and null values remain invalid."""
    value = copy.deepcopy(data)
    if value.pop("wire_format", None) != FORMAT:
        raise ValueError("Schema 校验失败：wire_format 必须为 reading-compact-1")
    language = value.pop("source_language", None)
    if not isinstance(language, str) or not 2 <= len(language) <= 35:
        raise ValueError("Schema 校验失败：source_language 必须是有效语言标识")

    def languages(item: Any, path: str = "") -> None:
        if isinstance(item, dict):
            if "original" in item and "language" not in item:
                item["language"] = language
                if changes is not None:
                    changes.append({"path": path + ".language", "rule": "batch-language"})
            for key, child in item.items():
                languages(child, path + "." + key)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                languages(child, path + "." + str(index))

    def source_text(container: dict[str, Any], key: str, path: str) -> None:
        text = container.get(key)
        if isinstance(text, str):
            container[key] = {"original": text, "language": language}
            if changes is not None:
                changes.append({"path": path + "." + key, "rule": "source-text-string"})

    if isinstance(value.get("items"), list):
        definitions = KnowledgeExtractionBatch.model_json_schema()["$defs"]
        for index, item in enumerate(value["items"]):
            if isinstance(item, dict):
                kind = item.get("kind")
                name = "Question" if kind == "ResearchQuestion" else kind
                definition = definitions.get(f"{name}Candidate", {})
                path = f"items.{index}"
                for key, field in definition.get("properties", {}).items():
                    branches = [field, *field.get("anyOf", [])]
                    if any(b.get("$ref") == "#/$defs/SourceText" for b in branches):
                        source_text(item, key, path)
                if kind == "Condition" and isinstance(item.get("alternatives"), list):
                    for alt_index, alternative in enumerate(item["alternatives"]):
                        if isinstance(alternative, dict):
                            source_text(alternative, "value", f"{path}.alternatives.{alt_index}")
                source = SUMMARY_SOURCE.get(kind) if isinstance(kind, str) else None
                if source and "summary" not in item and source in item:
                    item["summary"] = copy.deepcopy(item[source])
                    if changes is not None:
                        changes.append({"path": path + ".summary", "rule": "copy-" + source})
    languages(value)
    return value


def compact_fixture(data: dict[str, Any], language: str = "en") -> dict[str, Any]:
    """Exact-value encoder for offline fixtures/replay; never rewrites scientific text."""
    value = copy.deepcopy(data)
    value.update(wire_format=FORMAT, source_language=language)
    for item in value.get("items", []):
        source = SUMMARY_SOURCE.get(item.get("kind"))
        if source and item.get("summary") == item.get(source):
            item.pop("summary", None)

    def languages(item: Any) -> None:
        if isinstance(item, dict):
            if "original" in item and item.get("language") == language:
                del item["language"]
            for child in item.values():
                languages(child)
        elif isinstance(item, list):
            for child in item:
                languages(child)

    languages(value)
    return value
