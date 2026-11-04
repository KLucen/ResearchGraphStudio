"""Shared generated Prompt rules for the three versioned semantic transports."""

from typing import Any

from researchgraph.knowledge_store import digest
from researchgraph.reading_contracts import KnowledgeExtractionBatch, check_relation

BEGIN = "<!-- BEGIN GENERATED OUTPUT CONTRACT -->"
END = "<!-- END GENERATED OUTPUT CONTRACT -->"


def _enums(value: Any, path: str = "") -> list[str]:
    result = []
    if isinstance(value, dict):
        if "enum" in value:
            result.append(path + ": " + ", ".join(str(v) for v in value["enum"]) + ".")
        for key, child in value.items():
            if key != "enum":
                result.extend(_enums(child, path + "." + key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(_enums(child, path + "." + str(index)))
    return result


def generated_rules(schema: dict[str, Any], policy: str) -> str:
    definitions = schema.get("$defs", {})
    lines = [
        f"protocol: {policy}",
        f"output_schema_sha256: {digest(schema)}",
        "Top-level allowed keys: " + ", ".join(schema["properties"]) + ".",
        "Top-level required keys: " + ", ".join(schema.get("required", [])) + ".",
        "Do not output source/version/batch/protocol envelope fields or formal database IDs.",
        "Use exactly the declared fields. Required fields are marked * below:",
    ]
    relations = []
    for name, definition in definitions.items():
        properties = definition.get("properties", {})
        if not properties:
            continue
        kind = properties.get("kind", {}).get("const")
        required = set(definition.get("required", []))
        fields = ", ".join(f"{field}{'*' if field in required else ''}" for field in properties)
        lines.append(f"- {kind or name}: {fields}.")
        relations += properties.get("relation", {}).get("enum", [])
    lines.extend(_enums(schema, "output_schema"))
    if relations:
        kinds = [
            definition["properties"]["kind"]["const"]
            for definition in KnowledgeExtractionBatch.model_json_schema()["$defs"].values()
            if "const" in definition.get("properties", {}).get("kind", {})
        ]
        lines.append("Allowed relation directions:")
        for relation in dict.fromkeys(relations):
            endpoints = []
            for left in kinds:
                for right in kinds:
                    try:
                        check_relation(left, right, relation)
                    except ValueError:
                        continue
                    endpoints.append(f"{left}→{right}")
            lines.append(f"- {relation}: {', '.join(endpoints)}.")
    return "\n".join(lines)


def assert_generated_rules(prompt: str, expected: str) -> None:
    if prompt.count(BEGIN) != 1 or prompt.count(END) != 1:
        raise ValueError("Prompt 缺少唯一生成契约块")
    actual = prompt.split(BEGIN, 1)[1].split(END, 1)[0].strip()
    if actual != expected:
        raise ValueError("Prompt 与运行输出 Schema 不一致，请更新生成契约块")
