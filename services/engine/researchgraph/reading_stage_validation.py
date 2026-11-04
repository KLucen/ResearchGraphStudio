"""Read-only terminal validation shared by live responses and cached reading runs."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun, NodeEvidence
from researchgraph.knowledge_store import (
    KnowledgeError,
    KnowledgeStore,
    text_hash,
    validate_evidence,
)
from researchgraph.models import now
from researchgraph.reading_scope import current_nodes
from researchgraph.reading_support import (
    reachable_supports,
    support_context,
    support_paths,
    validate_member_paths,
)
from researchgraph.reading_validation import (
    isolate_integration_proposals,
    validate_integration,
    validate_selection,
)
from researchgraph.unified_store import evidence_ids

Stage = Literal["P02", "P12", "P13"]
Category = Literal["protocol", "schema", "context", "evidence"]
VALIDATION_POLICY = "reading-stage-terminal-v1"
_CONDITION_DIAGNOSTICS = {
    "Value error, known condition requires one supported value": (
        "known 条件必须提供一个有证据的 value，且 alternatives 必须为空"
    ),
    "Value error, unknown/not_applicable cannot assert values": (
        "unknown/not_applicable 条件不能声明 value、unit 或 alternatives"
    ),
    "Value error, conflicting requires evidenced alternatives": (
        "conflicting 条件必须提供至少两个有证据的 alternatives，且不能声明单一 value"
    ),
    "Value error, duplicate references": "模型重复使用了引用编号",
}
_ERROR_TYPES = frozenset(
    {
        "missing",
        "extra_forbidden",
        "value_error",
        "literal_error",
        "string_type",
        "string_too_short",
        "string_too_long",
        "list_type",
        "too_short",
        "too_long",
        "dict_type",
        "int_type",
        "int_parsing",
        "float_type",
        "float_parsing",
        "bool_type",
        "bool_parsing",
        "union_tag_invalid",
        "union_tag_not_found",
        "model_type",
        "none_required",
        "greater_than",
        "greater_than_equal",
        "less_than",
        "less_than_equal",
        "finite_number",
    }
)


@lru_cache(maxsize=3)
def _diagnostic_tokens(stage: Stage) -> frozenset[str]:
    """Only application-owned Schema names may appear in a diagnostic path."""
    from researchgraph.reading_contracts import (
        CoreSelectionProposal,
        KnowledgeExtractionBatch,
        PaperIntegrationProposal,
    )

    models: dict[str, type[BaseModel]] = {
        "P02": KnowledgeExtractionBatch,
        "P12": PaperIntegrationProposal,
        "P13": CoreSelectionProposal,
    }
    schemas = [models[stage].model_json_schema()]
    if stage != "P02":
        from researchgraph.reading_finish_wire import schema_for

        schemas.append(schema_for(stage))
    tokens: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for field in ("properties", "$defs"):
                tokens.update(value.get(field, {}))
            discriminator = value.get("discriminator", {})
            tokens.update(discriminator.get("mapping", {}))
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for schema in schemas:
        collect(schema)
    return frozenset(tokens)


def _dto_message(stage: Stage, error: ValidationError) -> str:
    """Bounded locations/types, with no model input, ctx or arbitrary error text."""
    tokens = _diagnostic_tokens(stage)
    diagnostics = []
    issues = error.errors(include_input=False, include_context=False, include_url=False)
    for issue in issues[:4]:
        parts = []
        for token in issue["loc"][:8]:
            if type(token) is int and 0 <= token <= 999_999:
                parts.append(str(token))
            elif isinstance(token, str) and token in tokens:
                parts.append(token)
            else:
                parts.append("<未允许字段>")
                break
        path = ".".join(parts) or "$"
        if len(path) > 120:
            path = path[:119] + "…"
        error_type = issue["type"] if issue["type"] in _ERROR_TYPES else "invalid"
        detail = _CONDITION_DIAGNOSTICS.get(issue["msg"])
        diagnostics.append(f"{path} ({error_type})" + (f"：{detail}" if detail else ""))
    if len(issues) > 4:
        diagnostics.append(f"另有 {len(issues) - 4} 项错误")
    return "模型响应未通过阶段 Schema 校验：" + "；".join(diagnostics)


class StageValidationError(ValueError):
    """Safe diagnostics distinguish a bad response from stale trusted inputs."""

    def __init__(
        self,
        category: Category,
        code: str,
        message: str,
        *,
        response_invalid: bool = True,
    ) -> None:
        super().__init__(message)
        self.category, self.code = category, code
        self.response_invalid = response_invalid

    def audit(self, raw: str, input_hash: str) -> dict[str, Any]:
        return {
            "policy": VALIDATION_POLICY,
            "category": self.category,
            "code": self.code,
            "response_invalid": self.response_invalid,
            "input_hash": input_hash,
            "raw_sha256": text_hash(raw),
        }


@dataclass
class StageValidation:
    value: dict[str, Any]
    normalization: list[dict[str, str]] = field(default_factory=list)
    quarantined: list[dict[str, Any]] = field(default_factory=list)
    removed_duplicates: list[dict[str, int]] = field(default_factory=list)


def record_validation_failure(
    engine: Engine,
    run_id: str,
    error: StageValidationError,
    data: dict[str, Any],
    raw: str,
) -> None:
    """Record terminal invalidity separately from immutable provider output."""
    from researchgraph.knowledge_store import digest

    with Session(engine) as session, session.begin():
        run = session.get(ModelRun, run_id)
        if run is None or run.raw_output != raw:
            raise StageValidationError(
                "context",
                "RUN_RESPONSE_CHANGED",
                "模型记录已变化，无法保存校验诊断",
                response_invalid=False,
            )
        if error.response_invalid:
            run.status, run.error, run.finished_at = "validation_failed", str(error), now()
        run.parameters = {**run.parameters, "stage_validation": error.audit(raw, digest(data))}


def validate_stage(
    session: Session,
    stage: Stage,
    raw: str,
    data: dict[str, Any],
    *,
    input_manifest: dict[str, Any] | None = None,
    snapshot: str | None = None,
    wire_validator: Callable[[str], str] | None = None,
) -> StageValidation:
    """Validate without materializing knowledge; Store must validate again at commit.

    The optional trusted wire binder returns canonical JSON and must reject all
    unexpected protocol fields. The caller preserves the original response/audit.
    A changed source or snapshot is not repaired by paying for another response.
    """
    if stage not in {"P02", "P12", "P13"}:
        raise StageValidationError("protocol", "UNKNOWN_STAGE", "未知阅读阶段")
    manifest = input_manifest or {}
    with session.no_autoflush:
        version_id = data.get("document_version_id")
        if not isinstance(version_id, str):
            raise StageValidationError(
                "context", "INPUT_VERSION_MISSING", "可信输入缺少文献版本", response_invalid=False
            )
        reading = KnowledgeStore(session).reading()
        try:
            reading.source(version_id)
            if snapshot is not None and reading.snapshot(version_id) != snapshot:
                raise StageValidationError(
                    "context",
                    "SNAPSHOT_CHANGED",
                    "候选快照已变化，请创建新构建",
                    response_invalid=False,
                )
        except KnowledgeError:
            raise StageValidationError(
                "context",
                "SOURCE_UNAVAILABLE",
                "可信输入的文献版本不可用",
                response_invalid=False,
            ) from None
        try:
            canonical = wire_validator(raw) if wire_validator else raw
            if not isinstance(canonical, str):
                raise StageValidationError(
                    "protocol", "WIRE_NOT_JSON_TEXT", "响应适配器未返回 JSON 文本"
                )
            result = _decode(stage, canonical, data, manifest)
        except StageValidationError:
            raise
        except json.JSONDecodeError:
            raise StageValidationError(
                "protocol", "INVALID_JSON", "模型响应不是完整有效的 JSON"
            ) from None
        except ValidationError as error:
            raise StageValidationError(
                "schema", "INVALID_DTO", _dto_message(stage, error)
            ) from None
        except (ValueError, TypeError) as error:
            # Existing batch validation rejects evidence before returning its DTO.
            message = str(error).lower()
            category: Category = (
                "protocol"
                if "duplicate json key" in message or "non-json constant" in message
                else "evidence"
                if "evidence" in message
                else "schema"
            )
            raise StageValidationError(
                category, "INVALID_STAGE_RESPONSE", "模型响应未通过阶段协议或证据校验"
            ) from None
        if result.value["document_version_id"] != version_id:
            raise StageValidationError(
                "context", "RESPONSE_VERSION_MISMATCH", "模型响应改变了文献版本"
            )
        if stage == "P02":
            _extraction_context(session, result.value, data, manifest, version_id)
        else:
            if result.value["input_revision"] != data.get("input_revision"):
                raise StageValidationError(
                    "context", "RESPONSE_REVISION_MISMATCH", "模型响应改变了输入修订版本"
                )
            if snapshot is not None and data.get("input_revision") != int(snapshot[:12], 16):
                raise StageValidationError(
                    "context",
                    "INPUT_REVISION_STALE",
                    "阶段输入与冻结快照不符",
                    response_invalid=False,
                )
            nodes = {node.id: node for node in current_nodes(session, version_id)}
            if stage == "P12":
                _integration_context(session, result, data, nodes, version_id)
            else:
                _selection_context(session, result.value, data, nodes, version_id)
        return result


def _decode(
    stage: Stage, raw: str, data: dict[str, Any], manifest: dict[str, Any]
) -> StageValidation:
    if stage == "P02":
        from researchgraph.reading_validation import validate_batch

        normalization: list[dict[str, str]] = []
        duplicates: list[dict[str, int]] = []
        parsed = json.loads(raw)
        aliases = manifest.get("evidence_aliases", {})
        allowed = set(aliases) if aliases else {e["id"] for e in data["allowed_evidence"]}
        compact = (
            data.get("wire_format") == "reading-compact-1"
            or manifest.get("wire_format") == "reading-compact-1"
            or isinstance(parsed, dict)
            and parsed.get("wire_format") == "reading-compact-1"
        )
        batch, quarantined = validate_batch(
            raw,
            allowed,
            compact=compact,
            removed_duplicates=duplicates,
            wire_changes=normalization,
        )
        return StageValidation(
            batch.model_dump(mode="json"), normalization, quarantined, duplicates
        )
    value, normalization = validate_integration(raw) if stage == "P12" else validate_selection(raw)
    return StageValidation(value, normalization)


def _anchor(session: Session, eid: str, version_id: str, *, trusted: bool) -> EvidenceSpan:
    span = session.get(EvidenceSpan, eid)
    try:
        if span is None:
            raise ValueError("missing evidence")
        validate_evidence(session, span, version_id)
    except (KnowledgeError, ValueError):
        raise StageValidationError(
            "evidence",
            "SOURCE_ANCHOR_INVALID",
            "原文证据定位已失效或不存在",
            response_invalid=not trusted,
        ) from None
    return span


def _input_evidence(
    session: Session, data: dict[str, Any], aliases: dict[str, str], version_id: str
) -> set[str]:
    entries = data.get("allowed_evidence", [])
    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)) or (
        aliases and (set(ids) != set(aliases) or len(set(aliases.values())) != len(aliases))
    ):
        raise StageValidationError(
            "context",
            "INPUT_EVIDENCE_MANIFEST_INVALID",
            "可信证据清单不唯一或已变化",
            response_invalid=False,
        )
    for entry in entries:
        span = _anchor(session, aliases.get(entry["id"], entry["id"]), version_id, trusted=True)
        text = entry.get("quote", entry.get("text"))
        if text is not None and text != span.quote:
            raise StageValidationError(
                "evidence",
                "INPUT_EVIDENCE_CHANGED",
                "可信输入原文与持久证据不一致",
                response_invalid=False,
            )
    return set(ids)


def _extraction_context(
    session: Session,
    value: dict[str, Any],
    data: dict[str, Any],
    manifest: dict[str, Any],
    version_id: str,
) -> None:
    if value["chunk_id"] != data.get("chunk_id"):
        raise StageValidationError("context", "RESPONSE_CHUNK_MISMATCH", "模型响应改变了抽取批次")
    aliases = manifest.get("evidence_aliases", {})
    allowed = _input_evidence(session, data, aliases, version_id)
    if evidence_ids(value) - allowed:
        raise StageValidationError("evidence", "EVIDENCE_NOT_ALLOWED", "模型引用了批次外证据")


def _candidate(
    session: Session,
    entry: dict[str, Any],
    nid: str,
    nodes: dict[str, KnowledgeNode],
    version_id: str,
    *,
    content_field: str,
) -> None:
    node = nodes.get(nid)
    if node is None or entry.get(content_field) != node.payload:
        raise StageValidationError(
            "context",
            "INPUT_CANDIDATE_CHANGED",
            "可信输入候选已变化或不属于当前文献",
            response_invalid=False,
        )
    spans = list(
        session.scalars(
            select(EvidenceSpan)
            .join(NodeEvidence, NodeEvidence.evidence_id == EvidenceSpan.id)
            .where(NodeEvidence.node_id == nid)
        )
    )
    if (
        not spans
        or node.source_status != "source_verified"
        or node.review_status in {"rejected", "superseded"}
        or "new_document_version_available" in node.issues
        or evidence_ids(node.payload) - {span.id for span in spans}
    ):
        raise StageValidationError(
            "evidence",
            "INPUT_CANDIDATE_UNANCHORED",
            "可信输入候选没有有效来源",
            response_invalid=False,
        )
    for span in spans:
        _anchor(session, span.id, version_id, trusted=True)


def _integration_context(
    session: Session,
    result: StageValidation,
    data: dict[str, Any],
    nodes: dict[str, KnowledgeNode],
    version_id: str,
) -> None:
    allowed_evidence = _input_evidence(session, data, {}, version_id)
    for entry in data["candidates"]:
        _candidate(session, entry, entry["id"], nodes, version_id, content_field="content")
        linked = set(
            session.scalars(
                select(NodeEvidence.evidence_id).where(NodeEvidence.node_id == entry["id"])
            )
        )
        if (
            set(entry.get("evidence_ids", [])) != linked
            or linked - allowed_evidence
            or evidence_ids(entry["content"]) - allowed_evidence
        ):
            raise StageValidationError(
                "evidence",
                "INPUT_CANDIDATE_EVIDENCE_MISSING",
                "整合输入缺少候选引用的完整证据",
                response_invalid=False,
            )
    roots = set(data["root_claim_ids"])
    if roots - {entry["id"] for entry in data["candidates"]} or any(
        nodes[root].kind != "claim" for root in roots if root in nodes
    ):
        raise StageValidationError(
            "context", "INPUT_ROOTS_INVALID", "可信整合根集合不合法", response_invalid=False
        )
    # Wrong candidate suggestions keep the established quarantine policy; evidence
    # violations fail the response, rather than disappearing during quarantine.
    if any(set(edge["evidence_ids"]) - allowed_evidence for edge in result.value["associations"]):
        raise StageValidationError("evidence", "EVIDENCE_NOT_ALLOWED", "整合响应引用了窗口外证据")
    result.quarantined.extend(isolate_integration_proposals(result.value, data))


def _selection_context(
    session: Session,
    value: dict[str, Any],
    data: dict[str, Any],
    nodes: dict[str, KnowledgeNode],
    version_id: str,
) -> None:
    validate_ranking_input(session, data, nodes=nodes)
    if {item["root_claim_id"] for item in value["recommendations"]} != {
        unit["root_claim_id"] for unit in data["units"]
    }:
        raise StageValidationError(
            "context", "RESPONSE_ROOTS_MISMATCH", "选择响应未完整对应输入根集合"
        )


def validate_ranking_input(
    session: Session,
    data: dict[str, Any],
    *,
    nodes: dict[str, KnowledgeNode] | None = None,
    snapshot: str | None = None,
) -> None:
    """Check trusted ranking inputs before a new paid call and at final validation."""
    version_id = data["document_version_id"]
    reading = KnowledgeStore(session).reading()
    if snapshot is not None and reading.snapshot(version_id) != snapshot:
        raise StageValidationError(
            "context", "SNAPSHOT_CHANGED", "候选快照已变化，请创建新构建", response_invalid=False
        )
    if nodes is None:
        nodes = {node.id: node for node in current_nodes(session, version_id)}
    if "support_context" in data and data["support_context"] != support_context(
        reading, version_id, nodes
    ):
        raise StageValidationError(
            "context",
            "SUPPORT_CONTEXT_CHANGED",
            "结论关联已变化，请创建新构建",
            response_invalid=False,
        )
    paths = support_paths(reading, version_id, nodes)
    units = data["units"]
    roots = [unit["root_claim_id"] for unit in units]
    if len(roots) != len(set(roots)):
        raise StageValidationError(
            "context", "INPUT_ROOTS_DUPLICATED", "可信选择根集合重复", response_invalid=False
        )
    for unit in units:
        root = unit["root_claim_id"]
        _candidate(session, unit, root, nodes, version_id, content_field="root")
        if nodes[root].kind != "claim":
            raise StageValidationError(
                "context",
                "INPUT_ROOT_KIND_INVALID",
                "可信选择根不是 Claim",
                response_invalid=False,
            )
        for member in unit["members"]:
            _candidate(session, member, member["id"], nodes, version_id, content_field="content")
        reached = reachable_supports(root, nodes, paths)
        if any(member["id"] not in reached or member["id"] == root for member in unit["members"]):
            raise StageValidationError(
                "context",
                "SUPPORT_CONTEXT_CHANGED",
                "结论成员已没有合法支撑路径",
                response_invalid=False,
            )
        try:
            validate_member_paths(
                reading,
                version_id,
                root,
                [(m["id"], m.get("association_ids", reached[m["id"]])) for m in unit["members"]],
                nodes,
                paths,
            )
        except KnowledgeError:
            raise StageValidationError(
                "context",
                "SUPPORT_CONTEXT_CHANGED",
                "结论支撑路径已变化，请创建新构建",
                response_invalid=False,
            ) from None
