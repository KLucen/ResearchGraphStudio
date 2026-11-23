"""Safe knowledge failure explanations; local raw revalidation never publishes or retries."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError
from researchgraph.knowledge_connection_models import (
    KnowledgeConnectionRequest,
    KnowledgeConnectionRun,
)
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.models import Job
from researchgraph.paper_knowledge import PREVIOUS_PROMPT_VERSION, knowledge_relation_issues
from researchgraph.paper_overview_contracts import strict_json
from researchgraph.providers import ProviderError, safe_retry_after
from researchgraph.task_runtime import ModelWaitCancelled

VERSION = "knowledge-diagnostic-1"
MAX_ISSUES = 8
_RETRY = "检查设置和任务记录后显式重试；不会自动再次发送模型请求。"
_SOURCE_ACTION = "检查所选解析内容及来源是否仍有效，必要时重新构建知识；不会自动重发。"
_FORMAT_ACTION = "检查列出的格式问题；原始响应保留在本机，显式重试前不会再次发送。"
_UNKNOWN_ACTION = "先检查模型服务与任务记录；缺少完整响应时无法本地修复格式，重试需要显式操作。"

# Only application-owned codes enter the public result. Exception text is never used.
_SPECS: dict[str, tuple[str, str, str]] = {
    "KNOWLEDGE_LOCAL_RECOVERY_UNAVAILABLE": (
        "schema",
        "当前响应不满足本机部分恢复的条件。",
        "检查具体结构、引文和来源问题。",
    ),
    "KNOWLEDGE_LOCAL_RECOVERY_STALE": (
        "source",
        "本机恢复预览的响应、来源或规则已改变。",
        "重新预览后再确认恢复；不会复用已经变化的审核结果。",
    ),
    "KNOWLEDGE_PROVIDER_TIMEOUT": ("transport", "等待模型服务超时，未取得完整可校验响应。", _RETRY),
    "KNOWLEDGE_PROVIDER_NETWORK": ("transport", "连接模型服务失败，未取得完整可校验响应。", _RETRY),
    "KNOWLEDGE_PROVIDER_INCOMPLETE_STREAM": (
        "transport",
        "模型响应中途断开，保留的片段不等于完整响应。",
        _RETRY,
    ),
    "KNOWLEDGE_PROVIDER_RATE_LIMIT": ("transport", "模型服务限制了本次请求频率或额度。", _RETRY),
    "KNOWLEDGE_PROVIDER_SERVER": ("transport", "模型服务暂时不可用。", _RETRY),
    "KNOWLEDGE_PROVIDER_CLIENT": (
        "configuration",
        "模型服务拒绝了本次请求，请检查端点、模型、凭据和额度。",
        _RETRY,
    ),
    "KNOWLEDGE_PROVIDER_OUTPUT_LIMIT": (
        "budget",
        "模型服务因输出额度结束生成，未取得完整可校验响应。",
        "检查单次输出预算和模型实际输出上限，再显式重试；不会自动重发。",
    ),
    "KNOWLEDGE_PROVIDER_EMPTY_RESPONSE": (
        "protocol",
        "模型服务未返回可校验的正文，不能据此判定知识 JSON 格式。",
        _RETRY,
    ),
    "KNOWLEDGE_PROVIDER_RESPONSE_INVALID": (
        "protocol",
        "模型服务的响应外壳或文本结果不符合文本协议，尚未完成知识格式校验。",
        _RETRY,
    ),
    "KNOWLEDGE_PROVIDER_STRUCTURED_OUTPUT_REFUSED": (
        "protocol",
        "模型服务拒绝返回本次结构化结果。",
        _RETRY,
    ),
    "KNOWLEDGE_RESPONSE_JSON_INVALID": (
        "protocol",
        "已保留的完整响应未通过严格 JSON 校验。",
        _FORMAT_ACTION,
    ),
    "KNOWLEDGE_RESPONSE_SCHEMA_INVALID": (
        "schema",
        "已保留的完整响应未通过知识内容结构校验。",
        _FORMAT_ACTION,
    ),
    "KNOWLEDGE_CONNECTION_NUMBER_UNSUPPORTED": (
        "source",
        "联系汇报含有所选双方引文未提供的数字，该批结果未发布。",
        "检查保存的原始响应和引文，按需要显式重试。",
    ),
    "KNOWLEDGE_FAILURE_UNRESOLVED": (
        "unknown",
        "本次失败缺少可判定的详细原因，不能确定为格式错误或超时。",
        _UNKNOWN_ACTION,
    ),
    "KNOWLEDGE_CAPACITY_INSUFFICIENT": (
        "budget",
        "完整输入与所需输出超出当前预算或模型容量，未截断正文。",
        "检查知识库输入、输出预算及模型真实容量；调高预算或选择无上限后显式重试。",
    ),
    "KNOWLEDGE_INPUT_BUDGET_EXCEEDED": (
        "budget",
        "完整输入超出知识库单次输入预算，未截断正文。",
        "调高知识库单次输入预算或选择无上限，保存设置后显式重试。",
    ),
    "KNOWLEDGE_TOTAL_BUDGET_EXHAUSTED": (
        "budget",
        "知识库累计请求预算已用尽或已预留。",
        "检查累计请求预算后显式重试。",
    ),
    "KNOWLEDGE_BUDGET_EXHAUSTED": (
        "budget",
        "当前知识库请求预算不足或已收紧。",
        "检查每次分析和累计请求预算后显式重试。",
    ),
    "KNOWLEDGE_RETRY_EXHAUSTED": (
        "budget",
        "相同解析输入已达到显式请求上限。",
        "检查已有任务和响应；不会再次自动发送相同输入。",
    ),
    "KNOWLEDGE_BUDGET_INVALID": ("configuration", "知识请求预算配置无效。", _RETRY),
    "KNOWLEDGE_CONFIGURATION_INVALID": ("configuration", "本次模型或知识任务配置无效。", _RETRY),
    "KNOWLEDGE_REAL_MODEL_REQUIRED": (
        "configuration",
        "知识构建需要已配置的真实全局模型。",
        _RETRY,
    ),
    "MODEL_NOT_CONFIGURED": ("configuration", "尚未配置可用的全局模型。", _RETRY),
    "NETWORK_CONSENT_REQUIRED": (
        "configuration",
        "本任务未取得发送所选材料的网络授权。",
        "确认知识库网络设置后显式操作。",
    ),
    "KNOWLEDGE_POLICY_REVOKED": (
        "configuration",
        "自动知识任务的网络授权已撤销。",
        "检查知识库授权设置后显式操作。",
    ),
    "KNOWLEDGE_CANCELLED": (
        "unknown",
        "本次知识任务已取消。",
        "检查已保留的任务记录后决定是否显式重试。",
    ),
    "KNOWLEDGE_REQUEST_INTERRUPTED": (
        "unknown",
        "任务曾中断，已有发送标记不代表已取得完整响应或已计费。",
        _UNKNOWN_ACTION,
    ),
    "KNOWLEDGE_DISPATCH_INTERRUPTED": (
        "unknown",
        "请求曾中断，已有发送标记不代表已取得完整响应或已计费。",
        _UNKNOWN_ACTION,
    ),
}
_SOURCE_CODES = {
    "KNOWLEDGE_SOURCE_MISSING",
    "KNOWLEDGE_SOURCE_MISMATCH",
    "KNOWLEDGE_SOURCE_KIND_INVALID",
    "KNOWLEDGE_SOURCE_EMPTY",
    "KNOWLEDGE_SOURCE_CHANGED",
    "KNOWLEDGE_SOURCE_REF_INVALID",
    "KNOWLEDGE_SOURCE_REF_DUPLICATE",
    "KNOWLEDGE_QUOTE_MISMATCH",
    "KNOWLEDGE_PAPER_UNAVAILABLE",
    "KNOWLEDGE_VERSION_MISSING",
    "KNOWLEDGE_VERSION_STALE",
    "KNOWLEDGE_EVIDENCE_REQUIRED",
    "KNOWLEDGE_SNAPSHOT_CHANGED",
    "KNOWLEDGE_CONTEXT_CHANGED",
    "KNOWLEDGE_CHECKPOINT_INVALID",
    "KNOWLEDGE_CACHE_INVALID",
    "KNOWLEDGE_OUTPUT_CHANGED",
    "KNOWLEDGE_CONNECTION_REF_INVALID",
    "KNOWLEDGE_CONNECTION_EVIDENCE_INVALID",
    "KNOWLEDGE_RUN_MISSING",
}
for _source_code in _SOURCE_CODES:
    _SPECS[_source_code] = ("source", "知识内容、引用或当前来源未通过完整性校验。", _SOURCE_ACTION)
for _source_code, _summary in {
    "KNOWLEDGE_QUOTE_MISMATCH": "知识引文与所选解析原文不匹配或为空白。",
    "KNOWLEDGE_SOURCE_REF_INVALID": "知识引用的来源编号不在本次冻结的来源范围内。",
    "KNOWLEDGE_SOURCE_REF_DUPLICATE": "同一知识对象包含重复的来源引文。",
    "KNOWLEDGE_SOURCE_CHANGED": "所选解析正文或来源指纹已改变，原任务不能继续发布。",
    "KNOWLEDGE_SOURCE_MISSING": "原论文或解析来源已不存在。",
    "KNOWLEDGE_SOURCE_MISMATCH": "所选解析版本尚未成功或不属于当前论文。",
    "KNOWLEDGE_SOURCE_EMPTY": "所选解析没有可引用的完整正文材料。",
    "KNOWLEDGE_SOURCE_KIND_INVALID": "所选来源类型不属于本地解析或模型解析。",
    "KNOWLEDGE_PAPER_UNAVAILABLE": "知识库论文已归档或移除。",
    "KNOWLEDGE_VERSION_MISSING": "用于联系分析的知识版本已不存在。",
    "KNOWLEDGE_VERSION_STALE": "知识版本已归档或不再是当前版本。",
    "KNOWLEDGE_EVIDENCE_REQUIRED": "知识缺少逐项可核验的来源依据。",
    "KNOWLEDGE_CONTEXT_CHANGED": "联系分析的冻结范围或来源已改变。",
    "KNOWLEDGE_CONNECTION_REF_INVALID": "联系引用了冻结范围之外的知识对象或论文归属根。",
    "KNOWLEDGE_CONNECTION_EVIDENCE_INVALID": "联系依据不属于双方所选的知识对象。",
    "KNOWLEDGE_SNAPSHOT_CHANGED": "已保存知识快照的完整性指纹不匹配。",
    "KNOWLEDGE_CHECKPOINT_INVALID": "联系报告检查点与原始响应、依赖或冻结来源不一致。",
    "KNOWLEDGE_CACHE_INVALID": "知识缓存与原始响应或冻结来源不一致。",
    "KNOWLEDGE_OUTPUT_CHANGED": "分析检查点与已保留原始响应不一致。",
    "KNOWLEDGE_RUN_MISSING": "原分析任务记录已不存在。",
}.items():
    _SPECS[_source_code] = ("source", _summary, _SOURCE_ACTION)
_SPECS["KNOWLEDGE_QUOTE_MISMATCH"] = (
    "source",
    "至少一条知识引文无法在本次指定的解析原文位置核验。",
    "如果此条任务显示“预览本机恢复”，可先核对能保留的节点和关系。本机恢复使用已保存的响应。",
)
for _schema_code in (
    "KNOWLEDGE_CONNECTION_DUPLICATE",
    "KNOWLEDGE_SUMMARY_REF_INVALID",
    "KNOWLEDGE_NO_RELATION_REASON_REQUIRED",
):
    _SPECS[_schema_code] = (
        "schema",
        "完整响应中的联系或汇报引用不符合知识结构要求。",
        _FORMAT_ACTION,
    )

_PROVIDER_CODES = {
    "timeout": "KNOWLEDGE_PROVIDER_TIMEOUT",
    "network": "KNOWLEDGE_PROVIDER_NETWORK",
    "incomplete_stream": "KNOWLEDGE_PROVIDER_INCOMPLETE_STREAM",
    "rate_limit": "KNOWLEDGE_PROVIDER_RATE_LIMIT",
    "server": "KNOWLEDGE_PROVIDER_SERVER",
    "client": "KNOWLEDGE_PROVIDER_CLIENT",
    "output_limit": "KNOWLEDGE_PROVIDER_OUTPUT_LIMIT",
    "empty_response": "KNOWLEDGE_PROVIDER_EMPTY_RESPONSE",
    "response": "KNOWLEDGE_PROVIDER_RESPONSE_INVALID",
    "structured_output_refused": "KNOWLEDGE_PROVIDER_STRUCTURED_OUTPUT_REFUSED",
    "context_limit": "KNOWLEDGE_CAPACITY_INSUFFICIENT",
    "output_budget_invalid": "KNOWLEDGE_BUDGET_INVALID",
    "structured_output_unsupported": "KNOWLEDGE_CONFIGURATION_INVALID",
}
_FIELDS = {
    "schema_version",
    "paper_card",
    "graph",
    "nodes",
    "edges",
    "id",
    "type",
    "label_zh",
    "label_en",
    "description_zh",
    "basis",
    "source_refs",
    "source_id",
    "quote",
    "occurrence_index",
    "excerpt_id",
    "source",
    "target",
    "research_question",
    "motivation",
    "method_summary",
    "contributions",
    "main_findings",
    "limitations",
    "relations",
    "summary",
    "ref",
    "target_ref",
    "source_node_id",
    "target_node_id",
    "explanation_zh",
    "limitations_zh",
    "detail",
    "source_zh",
    "target_zh",
    "comparison_zh",
    "conditions_zh",
    "follow_up_zh",
    "source_ref_ids",
    "target_ref_ids",
    "text_zh",
    "relation_refs",
    "no_relation_reason_zh",
    "_extra_field",
}
_ISSUE_MESSAGES = {
    "missing": "缺少必需字段。",
    "extra_forbidden": "包含协议未允许的额外字段。",
    "string_type": "字段必须为文本。",
    "string_too_short": "文本或列表长度不足。",
    "string_too_long": "文本超过允许长度。",
    "string_pattern_mismatch": "文本编号格式不符合协议。",
    "list_type": "字段必须为列表。",
    "dict_type": "字段必须为对象。",
    "model_type": "字段必须为协议对象。",
    "int_type": "字段必须为整数。",
    "int_parsing": "字段必须为整数。",
    "greater_than_equal": "数字小于允许范围。",
    "less_than_equal": "数字超过允许范围。",
    "literal_error": "字段值不在协议允许范围内。",
    "too_short": "文本或列表长度不足。",
    "too_long": "文本或列表超过允许长度。",
    "value_error": "字段或对象关系不符合知识结构要求。",
    "invalid": "字段不符合知识结构要求。",
    "json_invalid": "响应不是合法的严格 JSON。",
}
_TIMEOUT_LABELS = {
    "total": "等待模型生成达到总时限",
    "connection": "建立连接超时",
    "connection_pool": "等待连接超时",
    "request_write": "发送请求超时",
    "response_headers": "等待模型响应超时",
    "response_body": "读取模型响应超时",
    "first_generation": "等待首段正文或公开推理增量超时",
    "generation_idle": "正文及公开推理增量持续停滞",
    "first_response_data": "等待非流式响应数据超时",
    "response_data_idle": "非流式响应数据持续停滞",
}


def _path(loc: Any) -> str:
    result = ""
    for piece in tuple(loc)[:12]:
        if type(piece) is int and 0 <= piece <= 1_000_000:
            result += f"[{piece}]"
        else:
            safe = piece if isinstance(piece, str) and piece in _FIELDS else "_extra_field"
            result += ("." if result else "") + safe
    return result or "$"


def _base(code: str, sent: bool, raw: bool) -> dict[str, Any]:
    code = code if code in _SPECS else "KNOWLEDGE_FAILURE_UNRESOLVED"
    category, summary, action = _SPECS[code]
    return {
        "version": VERSION,
        "code": code,
        "category": category,
        "summary": summary,
        "issues": [],
        "request_sent": sent,
        "raw_available": raw,
        "action": action,
    }


def _provider_details(result: dict[str, Any], metadata: Any) -> None:
    if not isinstance(metadata, dict):
        return
    if result["code"] == "KNOWLEDGE_PROVIDER_TIMEOUT":
        phase = metadata.get("timeout_phase")
        label = _TIMEOUT_LABELS.get(phase) if isinstance(phase, str) else None
        if label:
            result["summary"] = label + "，未取得完整可校验响应。"
            settings_by_phase = {
                "total": "total_timeout_seconds",
                "first_generation": "first_generation_timeout_seconds",
                "generation_idle": "generation_idle_timeout_seconds",
                "first_response_data": "first_generation_timeout_seconds",
                "response_data_idle": "generation_idle_timeout_seconds",
            }
            setting = settings_by_phase.get(phase) if isinstance(phase, str) else None
            seconds = metadata.get(setting) if setting else None
            if (
                isinstance(seconds, (int, float))
                and not isinstance(seconds, bool)
                and math.isfinite(seconds)
                and 0 < seconds <= 86400
            ):
                result["summary"] = f"{label}（{seconds:g} 秒），未取得完整可校验响应。"
            if phase in {"first_generation", "generation_idle"}:
                result["summary"] += "正文与公开推理增量均计为活动，连接心跳不计为生成。"
    status = metadata.get("http_status")
    if (
        type(status) is int
        and 300 <= status <= 599
        and result["code"]
        in {
            "KNOWLEDGE_PROVIDER_CLIENT",
            "KNOWLEDGE_PROVIDER_RATE_LIMIT",
            "KNOWLEDGE_PROVIDER_SERVER",
        }
    ):
        result["summary"] += f"（HTTP {status}）"
    retry_after = safe_retry_after(metadata.get("retry_after_seconds"))
    if result["code"] == "KNOWLEDGE_PROVIDER_RATE_LIMIT" and retry_after is not None:
        result["retry_after_seconds"] = retry_after
        result["action"] = (
            f"服务当时建议等待 {retry_after} 秒，再检查额度后手动重试。不会自动发送。"
        )


def knowledge_diagnostic(
    error: BaseException,
    *,
    request_sent: bool,
    raw_available: bool,
    provider_metadata: Any = None,
) -> dict[str, Any]:
    """Classify from exception types and fixed codes, never exception strings or input."""
    if isinstance(error, ProviderError):
        result = _base(_PROVIDER_CODES.get(error.category, ""), request_sent, raw_available)
        metadata = dict(provider_metadata) if isinstance(provider_metadata, dict) else {}
        if error.timeout_phase in _TIMEOUT_LABELS:
            metadata["timeout_phase"] = error.timeout_phase
        if error.retry_after is not None:
            metadata["retry_after_seconds"] = error.retry_after
        _provider_details(result, metadata)
        return result
    if isinstance(error, ModelWaitCancelled):
        return _base("KNOWLEDGE_CANCELLED", request_sent, raw_available)
    if isinstance(error, TimeoutError):
        result = _base("KNOWLEDGE_PROVIDER_TIMEOUT", request_sent, raw_available)
        _provider_details(result, provider_metadata)
        return result
    if isinstance(error, KnowledgeError):
        return _base(error.code, request_sent, raw_available)
    if isinstance(error, ValidationError):
        if not raw_available:
            return _base("KNOWLEDGE_CONFIGURATION_INVALID", request_sent, raw_available)
        result = _base("KNOWLEDGE_RESPONSE_SCHEMA_INVALID", request_sent, raw_available)
        errors = error.errors(include_url=False, include_context=False, include_input=False)
        result["issues"] = [
            {
                "path": _path(issue["loc"]),
                "code": issue["type"] if issue["type"] in _ISSUE_MESSAGES else "invalid",
                "message": _ISSUE_MESSAGES.get(issue["type"], _ISSUE_MESSAGES["invalid"]),
            }
            for issue in errors[:MAX_ISSUES]
        ]
        result["issue_count"] = len(errors)
        return result
    if isinstance(error, json.JSONDecodeError):
        result = _base("KNOWLEDGE_RESPONSE_JSON_INVALID", request_sent, raw_available)
        result["issues"] = [
            {
                "path": "$",
                "code": "json_invalid",
                "message": f"响应不是合法的严格 JSON（行 {error.lineno}，列 {error.colno}）。",
            }
        ]
        return result
    return _base("KNOWLEDGE_FAILURE_UNRESOLVED", request_sent, raw_available)


def diagnostic_for_raw(
    error: BaseException,
    raw: str | None,
    *,
    request_sent: bool,
    provider_metadata: Any = None,
    prompt_version: str = PREVIOUS_PROMPT_VERSION,
) -> dict[str, Any]:
    """Plain validators can reject duplicate keys/NaN or graph relationships safely."""
    if isinstance(error, ValidationError) and raw is not None:
        detail = _relation_diagnostic(raw, request_sent, prompt_version)
        if detail is not None:
            return detail
    if (
        isinstance(error, ValueError)
        and not isinstance(
            error, (ProviderError, KnowledgeError, ValidationError, json.JSONDecodeError)
        )
        and raw is not None
    ):
        try:
            strict_json(raw)
        except ValueError as json_error:
            if isinstance(json_error, json.JSONDecodeError):
                return knowledge_diagnostic(
                    json_error, request_sent=request_sent, raw_available=True
                )
            return _base("KNOWLEDGE_RESPONSE_JSON_INVALID", request_sent, True)
        return _base("KNOWLEDGE_RESPONSE_SCHEMA_INVALID", request_sent, True)
    return knowledge_diagnostic(
        error,
        request_sent=request_sent,
        raw_available=raw is not None,
        provider_metadata=provider_metadata,
    )


def _relation_diagnostic(raw: str, sent: bool, prompt_version: str) -> dict[str, Any] | None:
    try:
        issues = knowledge_relation_issues(raw, prompt_version=prompt_version)
    except (ValueError, KeyError, TypeError):
        return None
    if not issues:
        return None
    result = _base("KNOWLEDGE_RESPONSE_SCHEMA_INVALID", sent, True)
    result["issues"] = [
        {key: issue[key] for key in ("path", "code", "message")} for issue in issues[:MAX_ISSUES]
    ]
    result["issue_count"] = len(issues)
    return result


def _saved_diagnostic(
    saved: Any,
    sent: bool,
    raw: bool,
    metadata: Any,
    raw_text: str | None = None,
    *,
    prompt_version: str = PREVIOUS_PROMPT_VERSION,
) -> dict[str, Any] | None:
    if not isinstance(saved, dict) or saved.get("version") != VERSION:
        return None
    code = saved.get("code")
    result = _base(code if isinstance(code, str) else "", sent, raw)
    if result["code"] == "KNOWLEDGE_RESPONSE_SCHEMA_INVALID" and raw_text is not None:
        detail = _relation_diagnostic(raw_text, sent, prompt_version)
        if detail is not None:
            return detail
    if result["code"] == "KNOWLEDGE_RESPONSE_JSON_INVALID" and raw_text is not None:
        try:
            strict_json(raw_text)
        except json.JSONDecodeError as error:
            return knowledge_diagnostic(error, request_sent=sent, raw_available=raw)
        except ValueError:
            pass
    issues = saved.get("issues")
    if isinstance(issues, list):
        safe = []
        for issue in issues[:MAX_ISSUES]:
            if not isinstance(issue, dict):
                continue
            kind = issue.get("code")
            kind = kind if isinstance(kind, str) and kind in _ISSUE_MESSAGES else "invalid"
            path = issue.get("path")
            # Re-tokenize stored paths; never trust saved messages, paths or unknown keys.
            parts = re.findall(r"\[[0-9]{1,7}\]|[a-z_]+", path) if isinstance(path, str) else []
            loc = [int(p[1:-1]) if p.startswith("[") else p for p in parts]
            safe.append({"path": _path(loc), "code": kind, "message": _ISSUE_MESSAGES[kind]})
        result["issues"] = safe
    count = saved.get("issue_count")
    if type(count) is int and count >= len(result["issues"]):
        result["issue_count"] = count
    details = dict(metadata) if isinstance(metadata, dict) else {}
    if "retry_after_seconds" not in details:
        details["retry_after_seconds"] = saved.get("retry_after_seconds")
    _provider_details(result, details)
    return result


def _legacy(
    code: str | None,
    raw: str | None,
    sent: bool,
    validate: Any,
    *,
    prompt_version: str = PREVIOUS_PROMPT_VERSION,
) -> dict[str, Any]:
    if code in _SPECS and code != "KNOWLEDGE_RESPONSE_SCHEMA_INVALID":
        return _base(code, sent, raw is not None)
    if raw is not None:
        try:
            validate()
        except (ValueError, KeyError, TypeError, IndexError) as error:
            return diagnostic_for_raw(error, raw, request_sent=sent, prompt_version=prompt_version)
        result = _base("KNOWLEDGE_FAILURE_UNRESOLVED", sent, True)
        result["summary"] = (
            "本机保留的响应当前可通过校验，但原任务未保留足够细因，无法判定当时为何失败。"
        )
        return result
    result = _base("KNOWLEDGE_FAILURE_UNRESOLVED", sent, False)
    result["summary"] = (
        "原任务未保留完整响应和足够的失败细因，无法判定是格式、网络、超时或其他原因；费用未知。"
    )
    return result


def stored_extraction_prompt_version(metadata: dict[str, Any]) -> str:
    contract = metadata.get("request_contract")
    value = contract.get("prompt_version") if isinstance(contract, dict) else None
    return value if isinstance(value, str) else PREVIOUS_PROMPT_VERSION


def project_knowledge_diagnostic(
    db: Session,
    job: Job,
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Attach a safe read-only view after existing batch projection; never edit history."""
    if job.kind not in {"knowledge_extract", "knowledge_connect"} or job.status not in {
        "failed",
        "interrupted",
        "cancelled",
    }:
        return result
    diagnostic: dict[str, Any]
    if job.kind == "knowledge_extract":
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job.id)
        )
        if run is None:
            return result
        sent, raw = run.request_sent, run.raw_response
        metadata = run.request_metadata or {}
        prompt_version = stored_extraction_prompt_version(metadata)
        diagnostic = (
            _saved_diagnostic(
                metadata.get("knowledge_diagnostic"),
                sent,
                raw is not None,
                metadata.get("provider"),
                raw,
                prompt_version=prompt_version,
            )
            or {}
        )
        if not diagnostic:

            def validate_extract() -> None:
                from researchgraph.knowledge_sources import revalidate_knowledge_sources
                from researchgraph.knowledge_tasks import validate_extraction_response

                validate_extraction_response(run)
                revalidate_knowledge_sources(db, run.source_manifest)

            diagnostic = _legacy(
                run.error_code, raw, sent, validate_extract, prompt_version=prompt_version
            )
    else:
        connection = db.scalar(
            select(KnowledgeConnectionRun).where(KnowledgeConnectionRun.job_id == job.id)
        )
        if connection is None:
            return result
        requests = list(
            db.scalars(
                select(KnowledgeConnectionRequest)
                .where(KnowledgeConnectionRequest.run_id == connection.id)
                .order_by(KnowledgeConnectionRequest.ordinal.desc())
            )
        )
        sent = any(row.sent_at is not None for row in requests)
        selected = next((row for row in requests if row.status == "failed"), None)
        selected = selected or next((row for row in requests if row.status != "validated"), None)
        raw = (
            selected.raw_response
            if selected
            and selected.status in {"received", "failed"}
            and selected.usage_json.get("response_complete") is not False
            else None
        )
        metadata = selected.usage_json if selected else {}
        diagnostic = (
            _saved_diagnostic(
                metadata.get("knowledge_diagnostic"),
                sent,
                raw is not None,
                metadata.get("request_metadata"),
                raw,
            )
            or _saved_diagnostic(
                (job.result or {}).get("knowledge_diagnostic"), sent, raw is not None, {}
            )
            or {}
        )
        if not diagnostic:

            def validate_connection() -> None:
                from researchgraph.knowledge_connections import (
                    _check_frozen,
                    _require_request_contract,
                    connection_contract_version,
                    validate_connections,
                )

                assert selected is not None and raw is not None
                _require_request_contract(
                    selected.input_json, connection_contract_version(connection.input_json)
                )
                validate_connections(raw, selected.input_json)
                _check_frozen(db, selected.input_json)

            diagnostic = _legacy(connection.error_code, raw, sent, validate_connection)
    return {**(result or {}), "knowledge_diagnostic": diagnostic}
