"""Frozen, documented output modes; no paid probing or automatic fallback."""

import copy
import hashlib
import json
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION: Literal["structured-output-1"] = "structured-output-1"
OPENAI_ENDPOINT = "https://api.openai.com/v1"
OPENAI_SOURCE = "https://developers.openai.com/api/docs/guides/structured-outputs"
# Exact identifiers explicitly named in the official Structured Outputs guide.
# Do not infer support from a prefix, a larger context, or an unrelated gateway.
OPENAI_STRICT_MODELS = frozenset({"gpt-4o-mini", "gpt-4o-mini-2024-07-18", "gpt-4o-2024-08-06"})


class OutputPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["structured-output-1"] = VERSION
    mode: Literal["native_json_schema", "json_object", "prompt"]
    provider: str = Field(min_length=1, max_length=24)
    endpoint: str = Field(max_length=1000)
    model: str = Field(min_length=1, max_length=150)
    support: Literal["documented", "requested", "disabled"]
    source: str = Field(max_length=300)
    reason: str = Field(max_length=300)


class StructuredOutputError(ValueError):
    """A configuration/schema conflict detected before a model request."""


def _thinking_conflict(base_url: str, model: str, parameters: dict[str, Any]) -> bool:
    from researchgraph.model_adapters import TENCENT_DEEPSEEK, tencent_deepseek

    return bool(
        parameters.get("adapter_policy") == TENCENT_DEEPSEEK
        and tencent_deepseek(base_url, model)
        and parameters.get("reasoning_effort") != "none"
    )


def freeze_output_policy(
    provider_name: str, base_url: str, model: str, parameters: dict[str, Any]
) -> dict[str, Any]:
    """Choose once for a new snapshot; never upgrade an already queued task."""
    endpoint = base_url.rstrip("/")
    official = provider_name == "openai" and endpoint == OPENAI_ENDPOINT
    mode: Literal["native_json_schema", "json_object", "prompt"]
    support: Literal["documented", "requested", "disabled"]
    if official and model in OPENAI_STRICT_MODELS:
        mode, support, source, reason = (
            "native_json_schema",
            "documented",
            OPENAI_SOURCE,
            "exact_official_endpoint_and_documented_model",
        )
    elif _thinking_conflict(endpoint, model, parameters):
        mode, support, source, reason = (
            "prompt",
            "disabled",
            "existing_endpoint_thinking_adapter",
            "thinking_mode_does_not_send_response_format",
        )
    elif parameters.get("json_mode", True):
        mode, support, source, reason = (
            "json_object",
            "requested",
            "configured_compatibility_mode",
            "json_object_requested_schema_adherence_not_guaranteed",
        )
    else:
        mode, support, source, reason = (
            "prompt",
            "disabled",
            "profile_json_mode_disabled",
            "prompt_only_schema_adherence_not_guaranteed",
        )
    return OutputPolicy(
        mode=mode,
        provider=provider_name,
        endpoint=endpoint,
        model=model,
        support=support,
        source=source,
        reason=reason,
    ).model_dump()


def checked_policy(
    raw: Any, provider_name: str, base_url: str, model: str, parameters: dict[str, Any]
) -> OutputPolicy:
    policy = OutputPolicy.model_validate(raw)
    if (policy.provider, policy.endpoint, policy.model) != (
        provider_name,
        base_url.rstrip("/"),
        model,
    ):
        raise StructuredOutputError("冻结的输出策略与当前端点或模型不符，请创建新任务")
    if policy.mode == "native_json_schema":
        if not (
            provider_name == "openai"
            and policy.endpoint == OPENAI_ENDPOINT
            and model in OPENAI_STRICT_MODELS
            and policy.support == "documented"
            and policy.source == OPENAI_SOURCE
        ):
            raise StructuredOutputError("此端点与模型没有已登记的原生严格 Schema 能力")
        if parameters.get("reasoning_effort") not in {None, "none"}:
            raise StructuredOutputError(
                "此严格输出模型不支持配置的思考参数，请调整设置后创建新任务"
            )
    if policy.mode != "prompt" and _thinking_conflict(base_url, model, parameters):
        raise StructuredOutputError("冻结的结构化输出模式与思考适配冲突，请创建新任务")
    return policy


def _hash(schema: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def strict_schema(schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Translate equivalent unions/consts, or narrow presence; never drop constraints.

    Non-nullable optional properties become required, not nullable. Unknown
    validation keywords are refused instead of silently removed for the API.
    """
    original = copy.deepcopy(schema)
    rules: Counter[str] = Counter()
    annotations = {"title", "default", "examples", "deprecated"}
    supported = {
        "$ref",
        "$defs",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "anyOf",
        "enum",
        "description",
        "pattern",
        "format",
        "multipleOf",
        "maximum",
        "exclusiveMaximum",
        "minimum",
        "exclusiveMinimum",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
    }

    def dereference(branch: dict[str, Any]) -> dict[str, Any]:
        if "$ref" not in branch:
            return branch
        reference = branch["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
            raise StructuredOutputError("严格输出仅支持本地 Schema 定义引用")
        definition = original.get("$defs", {}).get(reference[8:])
        if not isinstance(definition, dict):
            raise StructuredOutputError("严格输出 Schema 含未定义引用")
        return definition

    def convert(node: Any, path: str) -> dict[str, Any]:
        if not isinstance(node, dict):
            raise StructuredOutputError(f"严格输出不支持该 Schema 结构：{path}")
        result = copy.deepcopy(node)
        if "oneOf" in result:
            discriminator = result.get("discriminator", {}).get("propertyName")
            branches = result["oneOf"]
            tags = []
            if not isinstance(discriminator, str) or not isinstance(branches, list):
                raise StructuredOutputError("严格输出无法证明 oneOf 分支互斥，未放松约束")
            for branch in branches:
                definition = dereference(branch)
                tag = definition.get("properties", {}).get(discriminator, {}).get("const")
                if not isinstance(tag, str) or discriminator not in definition.get("required", []):
                    raise StructuredOutputError("严格输出无法证明 oneOf 分支互斥，未放松约束")
                tags.append(tag)
            if len(tags) != len(set(tags)) or "anyOf" in result:
                raise StructuredOutputError("严格输出 oneOf 分支标签不互斥，未放松约束")
            result["anyOf"] = result.pop("oneOf")
            result.pop("discriminator", None)
            rules["disjoint_discriminator_oneof_to_anyof"] += 1
        if "const" in result:
            value = result.pop("const")
            if "enum" in result:
                raise StructuredOutputError("严格输出不转换同时包含 const/enum 的字段")
            result["enum"] = [value]
            rules["const_to_single_enum"] += 1
        for annotation in annotations:
            if annotation in result:
                del result[annotation]
                rules["annotation_removed"] += 1
        if set(result) - supported:
            raise StructuredOutputError(f"严格输出不支持该 Schema 关键字：{path}")
        if "$ref" in result:
            dereference(result)
        for container in ("$defs", "properties"):
            if container in result:
                if not isinstance(result[container], dict):
                    raise StructuredOutputError(f"严格输出 Schema 对象格式错误：{path}")
                result[container] = {
                    name: convert(child, path + "." + container + "." + name)
                    for name, child in result[container].items()
                }
        if result.get("type") == "object":
            properties = result.get("properties", {})
            if result.get("additionalProperties") is not False:
                raise StructuredOutputError("严格输出要求对象显式禁止额外字段，未静默改变约束")
            required = result.get("required", [])
            if not isinstance(required, list) or set(required) - properties.keys():
                raise StructuredOutputError("严格输出 Schema 的 required 引用了未定义字段")
            if set(required) != set(properties):
                rules["optional_presence_required_without_adding_null"] += len(
                    set(properties) - set(required)
                )
            result["required"] = list(properties)
        if "anyOf" in result:
            if not isinstance(result["anyOf"], list) or not result["anyOf"]:
                raise StructuredOutputError("严格输出 anyOf 必须包含有效分支")
            result["anyOf"] = [convert(child, path + ".anyOf") for child in result["anyOf"]]
        if "items" in result:
            result["items"] = convert(result["items"], path + ".items")
        return result

    converted = convert(original, "root")
    if converted.get("type") != "object" or "anyOf" in converted:
        raise StructuredOutputError("严格输出 Schema 根必须为单一对象")
    return converted, dict(rules)


def response_format_for(
    schema: dict[str, Any], policy: OutputPolicy
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    audit: dict[str, Any] = {
        **policy.model_dump(),
        "source_schema_sha256": _hash(schema),
        "automatic_fallback": False,
    }
    if policy.mode == "native_json_schema":
        converted, rules = strict_schema(schema)
        audit.update(request_schema_sha256=_hash(converted), schema_transformations=rules)
        return {
            "type": "json_schema",
            "json_schema": {"name": "researchgraph_output", "strict": True, "schema": converted},
        }, audit
    return ({"type": "json_object"} if policy.mode == "json_object" else None), audit
