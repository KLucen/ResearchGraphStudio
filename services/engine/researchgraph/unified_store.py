"""Versioned v3 DTO -> existing domain store, in the caller's one transaction."""

from typing import Any

from researchgraph.graph_models import KnowledgeDisplay, SourceAssertion
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, KnowledgeOperation
from researchgraph.knowledge_store import (
    DOMAIN_VERSION,
    KnowledgeError,
    KnowledgeStore,
    digest,
    stable_id,
    validate_evidence,
)
from researchgraph.models import Paper
from researchgraph.unified_contracts import KnowledgeExtractionBatch


def evidence_ids(value: Any) -> set[str]:
    result: set[str] = set()
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            result.update(item.get("evidence_ids", []))
            pending.extend(v for k, v in item.items() if k != "evidence_ids")
        elif isinstance(item, list):
            pending.extend(item)
    return result


def apply_unified(
    store: KnowledgeStore,
    candidate: dict[str, Any],
    version_id: str,
    paper_id: str,
    chunk_id: str,
    allowed: set[str],
    run_id: str,
    key: str,
) -> dict[str, Any]:
    batch = KnowledgeExtractionBatch.model_validate(candidate)
    if batch.document_version_id != version_id or batch.chunk_id != chunk_id:
        raise KnowledgeError("SOURCE_MISMATCH", "模型改变了章节或文献版本标识")
    fingerprint = digest(candidate)
    previous = store.session.get(KnowledgeOperation, key)
    if previous:
        if previous.request_hash != fingerprint:
            raise KnowledgeError("IDEMPOTENCY_CONFLICT", "批次标识已用于其他结果")
        return previous.response
    for eid in evidence_ids(candidate):
        span = store.session.get(EvidenceSpan, eid)
        if eid not in allowed or span is None:
            raise KnowledgeError("UNKNOWN_EVIDENCE", "统一抽取引用了本批之外的证据")
        validate_evidence(store.session, span, version_id)
    domain: dict[str, Any] = {
        "paper_id": paper_id,
        "schema_version": DOMAIN_VERSION,
        "concepts": [],
        "methods": [],
        "claims": [],
        "experiments": [],
        "findings": [],
        "research_questions": [],
    }
    used_refs = {x.local_ref for x in batch.items}
    nested_links: list[tuple[str, str, str]] = []

    def local(prefix: str) -> str:
        value = prefix
        while value in used_refs:
            value += "_"
        used_refs.add(value)
        return value

    def conditions(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "dimension": c["dimension"],
                "known_state": c["state"],
                "value": c["value_en"],
                "value_zh": c["value_zh"],
                "unit": c["unit"],
                "evidence_span_ids": c["evidence_ids"],
            }
            for c in values
        ]

    def finding(value: dict[str, Any], owner: str, experiment: str | None = None) -> None:
        ref = local(owner + "_finding")
        domain["findings"].append(
            {
                "local_ref": ref,
                "statement": value["finding_en"],
                "statement_zh": value["finding_zh"] or None,
                "metric_name": value["metric_en"],
                "metric_name_zh": value["metric_zh"],
                "value": value["reported_value"],
                "baseline": value["baseline"],
                "unit": value["unit"],
                "evidence_span_ids": value["evidence_ids"],
                "experiment_local_ref": experiment,
            }
        )
        nested_links.append((owner, ref, "HAS_FINDING"))

    for item in batch.items:
        value = item.model_dump(mode="json")
        origin = "cited_claim" if item.origin == "citation_report" else "author_claim"
        common = {"local_ref": item.local_ref, "evidence_span_ids": item.evidence_ids}
        if item.kind == "Concept":
            domain["concepts"].append(
                {
                    **common,
                    "canonical_name": item.label_en,
                    "canonical_name_zh": item.label_zh or None,
                }
            )
        elif item.kind == "Method":
            detail = value["method_detail"] or {}
            domain["methods"].append(
                {
                    **common,
                    "name": item.label_en,
                    "name_zh": item.label_zh or None,
                    "mechanism": detail.get("mechanism_en") or item.summary_en,
                    "mechanism_zh": detail.get("mechanism_zh") or item.summary_zh or None,
                }
            )
        elif item.kind == "ResearchQuestion":
            domain["research_questions"].append(
                {
                    **common,
                    "statement": item.summary_en,
                    "statement_zh": item.summary_zh or None,
                    "origin": origin,
                }
            )
        else:
            detail = value["claim_detail"]
            methods = [
                link.target_local_ref
                for link in batch.links
                if link.source_local_ref == item.local_ref and link.relation == "USES_METHOD"
            ]
            domain["claims"].append(
                {
                    "local_ref": item.local_ref,
                    "statement": detail["statement_en"],
                    "statement_zh": detail["statement_zh"] or None,
                    "claim_type": "other",
                    "origin": origin,
                    "modality": detail["modality"],
                    "scope": detail["scope_en"],
                    "scope_zh": detail["scope_zh"],
                    "evidence": [
                        {
                            "evidence_span_id": eid,
                            "role": "cited_other" if origin == "cited_claim" else "direct",
                        }
                        for eid in item.evidence_ids
                    ],
                    "conditions": conditions(detail["conditions"]),
                    "method_local_refs": methods,
                }
            )
        detail = value.get("claim_detail") or value.get("method_detail") or {}
        for exp in detail.get("experiments", []):
            ref = local(item.local_ref + "_experiment")
            domain["experiments"].append(
                {
                    "local_ref": ref,
                    "label": exp["label"],
                    "task": exp["task"],
                    "protocol": exp["protocol"],
                    "conditions": conditions(exp["conditions"]),
                    "method_local_refs": [item.local_ref] if item.kind == "Method" else [],
                    "evidence_span_ids": exp["evidence_ids"],
                }
            )
            nested_links.append((item.local_ref, ref, "HAS_EXPERIMENT"))
            for f in exp["findings"]:
                finding(f, item.local_ref, ref)
        for f in detail.get("findings", []):
            finding(f, item.local_ref)
    result = store.apply(domain, version_id, allowed, run_id, key + ":domain")
    refs = result["local_refs"]
    new_ids = set(result["created_ids"])
    changed = False
    for item in batch.items:
        node_id = refs[item.local_ref]
        node = store.session.get(KnowledgeNode, node_id)
        assert node
        if node_id in new_ids:
            node.origin = "cited_claim" if item.origin == "citation_report" else "author_claim"
            node.authorship = "cited_author" if item.origin == "citation_report" else "paper_author"
        if (
            store.session.get(KnowledgeDisplay, node_id) is None
            and node.review_status != "accepted"
        ):
            store.session.add(
                KnowledgeDisplay(
                    node_id=node_id,
                    source_revision=node.revision,
                    model_run_id=run_id,
                    data={
                        "label_en": item.label_en,
                        "label_zh": item.label_zh,
                        "summary_en": item.summary_en,
                        "summary_zh": item.summary_zh,
                        "translation_status": "available"
                        if item.label_zh and item.summary_zh
                        else "missing",
                    },
                )
            )
            changed = True
    for a, b, role in nested_links:
        # Dependencies added to reused nodes would change already-reviewed scientific semantics.
        if refs[a] in new_ids:
            store._dependency(refs[a], refs[b], role)
    for link in batch.links:
        a, b = refs[link.source_local_ref], refs[link.target_local_ref]
        source = store.session.get(KnowledgeNode, a)
        target = store.session.get(KnowledgeNode, b)
        assert source and target
        if source.review_status == "accepted" or target.review_status == "accepted":
            continue
        link_id = stable_id("source-edge", digest([a, b, link.relation, sorted(link.evidence_ids)]))
        if store.session.get(SourceAssertion, link_id) is None:
            paper = store.session.get(Paper, paper_id)
            assert paper
            store.session.add(
                SourceAssertion(
                    id=link_id,
                    project_id=paper.project_id,
                    source_id=a,
                    target_id=b,
                    relation=link.relation,
                    evidence_ids=link.evidence_ids,
                    model_run_id=run_id,
                )
            )
            changed = True
    if changed and not new_ids:
        paper = store.session.get(Paper, paper_id)
        assert paper
        result = {
            **result,
            "new_revision": store.event(
                paper.project_id,
                "GRAPH_DISPLAY_ADDED",
                {"node_ids": result["node_ids"]},
                model_run_id=run_id,
            ),
        }
    store.session.add(KnowledgeOperation(key=key, request_hash=fingerprint, response=result))
    return result
