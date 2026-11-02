"""One recorded repair of missing local endpoints, never a rewrite of knowledge."""

import copy
import json
from typing import Any

from pydantic import Field, ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.extraction import call_model, mark_run, reusable_model_run
from researchgraph.extraction_normalization import normalize_empty_placeholders
from researchgraph.knowledge_contracts import StrictModel
from researchgraph.knowledge_models import ModelRun
from researchgraph.providers import Provider, ProviderError
from researchgraph.unified_contracts import KnowledgeExtractionBatch, UnifiedLink
from researchgraph.unified_store import evidence_ids

REPAIR_PROMPT = "P02_local_link_repair"


class LinkEndpointRepair(StrictModel):
    link_index: int = Field(ge=0, lt=200)
    source_local_ref: str = Field(min_length=1, max_length=80)
    target_local_ref: str = Field(min_length=1, max_length=80)


class LocalLinkRepair(StrictModel):
    repairs: list[LinkEndpointRepair] = Field(max_length=200)


def validation_message(error: Exception) -> str:
    """Never dump the full Pydantic input (private source text) into job errors."""
    if isinstance(error, ValidationError):
        parts = []
        for issue in error.errors(include_input=False, include_url=False)[:4]:
            if issue["type"] == "local_ref_missing":
                ctx = issue["ctx"]
                parts.append(
                    f"links[{ctx['index']}].{ctx['field']} 引用了不存在的 local_ref：{ctx['ref']}"
                )
            elif issue["type"] == "value_error" and issue["msg"] in {
                "Value error, duplicate references",
                "Value error, unknown local reference",
                "Value error, association endpoint types do not match",
            }:
                parts.append(
                    {
                        "Value error, duplicate references": "模型重复使用了引用编号",
                        "Value error, unknown local reference": "模型关系引用了不存在的候选编号",
                        "Value error, association endpoint types do not match": (
                            "关系两端的知识类型不符合规则"
                        ),
                    }[issue["msg"]]
                )
            else:
                parts.append(f"{'.'.join(map(str, issue['loc'])) or 'batch'} ({issue['type']})")
        return "Schema 校验失败：" + "；".join(parts)
    return str(error)


async def validate_or_repair(
    engine: Engine,
    job_id: str,
    provider: Provider,
    original_run: str,
    raw: str,
    data: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[str, KnowledgeExtractionBatch]:
    normalized, paths = normalize_empty_placeholders(raw)
    if paths:
        with Session(engine) as session, session.begin():
            run = session.get(ModelRun, original_run)
            assert run
            run.parameters = {
                **run.parameters,
                "normalization": {
                    "rule": "null-findings-placeholder-v1",
                    "removed_paths": paths,
                    "original_validation_error": "extra_forbidden",
                },
            }
    try:
        return original_run, KnowledgeExtractionBatch.model_validate_json(normalized)
    except ValidationError as error:
        message = validation_message(error)
        mark_run(engine, original_run, "validation_failed", message)
        if any(e["type"] != "local_ref_missing" for e in error.errors()):
            raise ValueError(message) from None

    original = json.loads(normalized)
    # Only structurally valid, source-consistent items can enter endpoint repair.
    KnowledgeExtractionBatch.model_validate({**original, "links": []})
    for link in original["links"]:
        UnifiedLink.model_validate(link)
    if any(original[k] != data[k] for k in ("document_version_id", "chunk_id")):
        raise ValueError("SOURCE_MISMATCH：模型改变了文献版本或批次标识；未修复")
    if not evidence_ids(original) <= manifest["evidence_aliases"].keys():
        raise ValueError("UNKNOWN_EVIDENCE：本批之外的证据编号；未修复")
    refs = {item["local_ref"] for item in original["items"]}
    broken = {
        i: link
        for i, link in enumerate(original["links"])
        if link["source_local_ref"] not in refs or link["target_local_ref"] not in refs
    }
    repair_data = {
        "items": [
            {k: item[k] for k in ("local_ref", "kind", "summary_en")} for item in original["items"]
        ],
        "broken_links": [{"link_index": i, **link} for i, link in broken.items()],
    }
    repair_manifest = {**manifest, "repair_of_run_id": original_run}
    cached = reusable_model_run(
        engine, job_id, provider, REPAIR_PROMPT, repair_data, repair_manifest
    )
    if cached:
        repair_id, repair_raw = cached
    else:
        with Session(engine) as session:
            previous = session.scalars(
                select(ModelRun).where(
                    ModelRun.job_id == job_id, ModelRun.prompt_name == REPAIR_PROMPT
                )
            ).all()
            if any(
                r.parameters.get("input_manifest", {}).get("repair_of_run_id") == original_run
                for r in previous
            ):
                raise ProviderError(
                    "schema_repair_exhausted",
                    message + "；本批的一次引用修复已用完，未重复调用，请查看模型记录",
                )
        repair_id, repair_raw = await call_model(
            engine,
            job_id,
            data["document_version_id"],
            provider,
            REPAIR_PROMPT,
            repair_data,
            LocalLinkRepair.model_json_schema(),
            repair_manifest,
        )
    try:
        patch = LocalLinkRepair.model_validate_json(repair_raw)
        if (
            len(patch.repairs) != len(broken)
            or {p.link_index for p in patch.repairs} != broken.keys()
        ):
            raise ValueError("修复未唯一覆盖所有缺失引用；本批未写入")
        candidate = copy.deepcopy(original)
        for entry in patch.repairs:
            for field in ("source_local_ref", "target_local_ref"):
                old = broken[entry.link_index][field]
                new = getattr(entry, field)
                if new not in refs or (old in refs and new != old):
                    raise ValueError("修复越界或改写了已有合法引用；本批未写入")
                candidate["links"][entry.link_index][field] = new
        validated = KnowledgeExtractionBatch.model_validate(candidate)
    except (ValueError, ValidationError) as error:
        detail = message + "；一次引用修复失败：" + validation_message(error)
        mark_run(engine, repair_id, "validation_failed", detail)
        raise ProviderError("schema_repair_failed", detail) from None
    return repair_id, validated
