"""Read-only Query graph expansion over source-validated knowledge, never a canvas."""

from collections import defaultdict
from itertools import combinations
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_contracts import EvidenceView, NodeView
from researchgraph.knowledge_models import (
    EvidenceSpan,
    KnowledgeNode,
    ModelRun,
    NodeEvidence,
    Section,
)
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, validate_evidence
from researchgraph.models import AttachmentRevision, Chunk, Job, Paper, Project
from researchgraph.reading_models import CandidateMetadata, ReadingMember, ReadingUnit
from researchgraph.reading_scope import current_candidate
from researchgraph.reading_support import reachable_supports, support_paths, validate_member_paths
from researchgraph.reading_transport import loads
from researchgraph.reasoning import resolve_ids
from researchgraph.reasoning_context import model_context
from researchgraph.reasoning_contracts import ComparabilityReport, RelationInference
from researchgraph.reasoning_models import ReasoningAttempt, RelationAssertion
from researchgraph.reasoning_store import validate_comparison, validate_inference
from researchgraph.unified_store import evidence_ids


def _papers(session: Session, project_id: str, paper_ids: list[str]) -> list[Paper]:
    if session.get(Project, project_id) is None:
        raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
    rows = list(session.scalars(select(Paper).where(Paper.project_id == project_id)))
    wanted = set(paper_ids)
    if wanted - {p.id for p in rows}:
        raise KnowledgeError("QUERY_SCOPE_MISMATCH", "论文不属于本次查询项目")
    return sorted((p for p in rows if not wanted or p.id in wanted), key=lambda p: p.id)


def eligible_nodes(session: Session, project_id: str, paper_ids: list[str]) -> list[KnowledgeNode]:
    """Return all eligible candidates, independently of selection, layout or pagination."""
    papers = {p.id for p in _papers(session, project_id, paper_ids)}
    versions: dict[str, str] = {}
    for version in session.scalars(
        select(AttachmentRevision)
        .where(AttachmentRevision.paper_id.in_(papers))
        .order_by(AttachmentRevision.created_at.desc(), AttachmentRevision.id.desc())
    ):
        versions.setdefault(version.paper_id, version.id)
    rows = list(
        session.scalars(
            select(KnowledgeNode)
            .join(ModelRun, ModelRun.id == KnowledgeNode.model_run_id)
            .join(CandidateMetadata, CandidateMetadata.node_id == KnowledgeNode.id)
            .join(Job, Job.id == ModelRun.job_id)
            .where(
                KnowledgeNode.paper_id.in_(papers),
                KnowledgeNode.document_version_id.in_(versions.values()),
                KnowledgeNode.review_status.not_in(["rejected", "superseded"]),
                KnowledgeNode.source_status == "source_verified",
                CandidateMetadata.validation_status == "valid",
                ModelRun.provider != "mock",
                Job.project_id == project_id,
            )
            .order_by(KnowledgeNode.id)
        )
    )
    # Keep the same eligibility JOINs, but load each model result once. Selecting
    # complete ModelRun/metadata ORM rows for every candidate repeatedly decoded
    # the same raw-run parameters and constructed rows discarded by validation.
    # These maps belong only to this invocation; the next call rereads sources.
    run_ids = sorted({n.model_run_id for n in rows if n.model_run_id})
    runs: dict[str, ModelRun] = {}
    for start in range(0, len(run_ids), 900):
        runs.update(
            (run.id, run)
            for run in session.scalars(
                select(ModelRun).where(ModelRun.id.in_(run_ids[start : start + 900]))
            )
        )
    linked: dict[str, set[str]] = defaultdict(set)
    for link in session.scalars(
        select(NodeEvidence).where(NodeEvidence.node_id.in_([n.id for n in rows]))
    ):
        linked[link.node_id].add(link.evidence_id)
    spans = {
        e.id: e
        for e in session.scalars(
            select(EvidenceSpan).where(EvidenceSpan.id.in_(set().union(*linked.values())))
        )
    }
    # Retain these maps during validation so Session.get reuses batched identity rows.
    chunks = {
        c.id: c
        for c in session.scalars(
            select(Chunk).where(Chunk.id.in_([e.paragraph_id for e in spans.values()]))
        )
    }
    sections = {
        s.id: s
        for s in session.scalars(
            select(Section).where(Section.id.in_([e.section_id for e in spans.values()]))
        )
    }
    from researchgraph.document_structure import current_structure
    from researchgraph.query_retrieval import chunk_metadata

    parse_metadata = {
        version_id: chunk_metadata(session, version_id)
        for version_id in {span.document_version_id for span in spans.values()}
        if current_structure(session, version_id) is not None
    }
    good_spans = set()
    for eid, span in spans.items():
        if span.paragraph_id not in chunks or span.section_id not in sections:
            continue
        role = sections[span.section_id].role
        if (
            role in {"references", "header", "footer"}
            or role.startswith("page_")
            or parse_metadata.get(span.document_version_id, {})
            .get(span.paragraph_id, {})
            .get("excluded")
        ):
            continue
        try:
            validate_evidence(session, span, span.document_version_id)
        except KnowledgeError:
            continue
        good_spans.add(eid)
    result = []
    for node in rows:
        run = runs.get(node.model_run_id or "")
        refs = linked[node.id]
        if (
            not run
            or node.document_version_id != versions.get(node.paper_id)
            or run.document_version_id != node.document_version_id
            or "new_document_version_available" in node.issues
            or node.payload.get("kind")
            != ("ResearchQuestion" if node.kind == "research_question" else node.kind.title())
            or not current_candidate(node, run)
            or not refs
            or not refs <= good_spans
            or evidence_ids(node.payload) - refs
            or any(spans[e].document_version_id != node.document_version_id for e in refs)
        ):
            continue
        result.append(node)
    return result


def _condition(node: KnowledgeNode, refs: list[str]) -> dict[str, Any]:
    return {
        "node_id": node.id,
        "paper_id": node.paper_id,
        "document_version_id": node.document_version_id,
        "dimension": node.payload["dimension"],
        "state": node.payload["state"],
        "value": node.payload.get("value"),
        "unit": node.payload.get("unit"),
        "alternatives": node.payload.get("alternatives", []),
        "evidence_ids": refs,
        "authorship": node.authorship,
    }


def _compare(
    roots: list[str], nodes: dict[str, KnowledgeNode], closures: dict[str, dict[str, list[str]]]
) -> list[dict[str, Any]]:
    reports = []
    by_paper: dict[str, list[str]] = defaultdict(list)
    for root in sorted(roots):
        by_paper[nodes[root].paper_id].append(root)
    pairs = (
        (left, right)
        for a, b in combinations(sorted(by_paper), 2)
        for left in by_paper[a]
        for right in by_paper[b]
    )
    for left, right in pairs:
        sides = []
        for root in (left, right):
            values: dict[str, list[KnowledgeNode]] = defaultdict(list)
            for nid in closures[root]:
                if nodes[nid].kind == "condition":
                    values[nodes[nid].payload["dimension"].casefold()].append(nodes[nid])
            sides.append(values)
        dimensions = []
        for dimension in sorted(sides[0].keys() | sides[1].keys()):
            groups = [side.get(dimension, []) for side in sides]
            state = "unknown"
            reason = "missing_or_uncertain_condition"
            if all(len(v) == 1 for v in groups):
                a, b = groups[0][0].payload, groups[1][0].payload
                if a["state"] == b["state"] == "not_applicable":
                    state, reason = "not_applicable", "explicit_on_both_sides"
                elif a["state"] == b["state"] == "known":
                    if a.get("unit") != b.get("unit"):
                        reason = "unit_mismatch_no_conversion"
                    elif groups[0][0].authorship != groups[1][0].authorship:
                        reason = "different_attribution"
                    else:
                        state = (
                            "same"
                            if a["value"]["original"].strip().casefold()
                            == b["value"]["original"].strip().casefold()
                            else "different"
                        )
                        reason = "lexical_values_only_not_scientific_comparability"
            dimensions.append(
                {
                    "dimension": dimension,
                    "source_condition_ids": [n.id for n in groups[0]],
                    "target_condition_ids": [n.id for n in groups[1]],
                    "comparison": state,
                    "reason": reason,
                }
            )
        reports.append(
            {
                "source_id": left,
                "target_id": right,
                "authorship_match": nodes[left].authorship == nodes[right].authorship,
                "overall": "unknown",
                "dimensions": dimensions,
                "caveat": "条件词面比较不证明研究问题、实验或结论科学可比",
            }
        )
    return reports


def _dimensions(nodes: list[KnowledgeNode]) -> dict[str, dict[str, Any]]:
    dimensions = {}
    conditions = [n for n in nodes if n.kind == "condition"]
    for name in sorted({n.dimension for n in conditions if n.dimension}):
        signatures = {
            (n.known_state, n.value, n.unit)
            for n in conditions
            if n.dimension == name and n.known_state != "unknown"
        }
        state, value, unit = (
            next(iter(signatures))
            if len(signatures) == 1
            else ("conflicting" if signatures else "unknown", None, None)
        )
        dimensions[name] = {"known_state": state, "value": value, "unit": unit}
    return dimensions


def _valid_relation(
    session: Session,
    relation: RelationAssertion,
    project_id: str,
    nodes: dict[str, KnowledgeNode],
    closures: dict[str, dict[str, list[str]]],
    paths: dict[str, list[tuple[str, str, str]]],
) -> bool:
    """Recheck complete frozen sources without using Comparator's bounded reader."""
    if (
        relation.project_id != project_id
        or relation.review_status not in {"proposed", "accepted"}
        or relation.relation_type
        not in {"SUPPORTS", "CONTRADICTS", "QUALIFIES", "EXTENDS", "RELATED"}
        or relation.source_id not in closures
        or relation.target_id not in closures
        or nodes[relation.source_id].paper_id == nodes[relation.target_id].paper_id
    ):
        return False
    attempt = session.get(ReasoningAttempt, relation.attempt_id)
    if (
        not attempt
        or attempt.project_id != project_id
        or attempt.mode != "relation"
        or (attempt.source_id, attempt.target_id) != (relation.source_id, relation.target_id)
        or digest(attempt.snapshot) != attempt.snapshot_hash
        or len(attempt.model_run_ids) != 2
    ):
        return False
    try:
        output = RelationInference.model_validate(attempt.output)
        report = ComparabilityReport.model_validate(attempt.comparison)
        if (
            output.decision != "PROPOSE_RELATION"
            or output.relation_type != relation.relation_type
            or (output.source_claim_id, output.target_claim_id)
            != (relation.source_id, relation.target_id)
            or set(output.evidence_ids) != set(relation.evidence_ids)
            or (report.source_claim_id, report.target_claim_id)
            != (relation.source_id, relation.target_id)
            or attempt.snapshot["project_id"] != project_id
        ):
            return False
        all_evidence: set[str] = set()
        direct: list[set[str]] = []
        for side, root in (("source", relation.source_id), ("target", relation.target_id)):
            frozen = attempt.snapshot[side]
            if frozen["root_id"] != root:
                return False
            expected_nodes = {n["id"]: n for n in frozen["nodes"]}
            if len(expected_nodes) != len(frozen["nodes"]) or set(expected_nodes) != set(
                closures[root]
            ):
                return False
            for nid, before in expected_nodes.items():
                if NodeView.model_validate(nodes[nid]).model_dump(mode="json") != before:
                    return False
            if frozen["dimensions"] != _dimensions([nodes[nid] for nid in expected_nodes]):
                return False
            expected_links = sorted(
                [a, b, _relation_type(session, aid)]
                for a, b, aid in paths[nodes[root].document_version_id]
                if a in expected_nodes and b in expected_nodes
            )
            if sorted(frozen["dependencies"]) != expected_links:
                return False
            evidence = {
                link.evidence_id
                for link in session.scalars(
                    select(NodeEvidence).where(NodeEvidence.node_id.in_(expected_nodes))
                )
            }
            frozen_evidence = {e["id"]: e for e in frozen["evidence"]}
            if len(frozen_evidence) != len(frozen["evidence"]) or set(frozen_evidence) != evidence:
                return False
            for eid in evidence:
                span = session.get(EvidenceSpan, eid)
                if not span:
                    return False
                validate_evidence(session, span, nodes[root].document_version_id)
                if (
                    EvidenceView.model_validate(span).model_dump(mode="json")
                    != frozen_evidence[eid]
                ):
                    return False
            root_refs = set(
                session.scalars(
                    select(NodeEvidence.evidence_id).where(NodeEvidence.node_id == root)
                )
            )
            if set(frozen["root_evidence_ids"]) != root_refs:
                return False
            direct.append(root_refs)
            all_evidence.update(evidence)
        if not set(relation.evidence_ids) <= all_evidence or not all(
            set(relation.evidence_ids) & refs for refs in direct
        ):
            return False
        if any(not set(d.evidence_ids) <= all_evidence for d in report.dimensions):
            return False
        validate_comparison(report, attempt.snapshot)
        validate_inference(output, report, attempt.snapshot)
        wire, aliases = model_context(attempt.snapshot)
        wire["required_dimensions"] = sorted(
            attempt.snapshot["source"]["dimensions"].keys()
            | attempt.snapshot["target"]["dimensions"].keys()
        )
        for rid, prompt in zip(
            attempt.model_run_ids, ["P04_compare_conditions", "P05_infer_relation"], strict=True
        ):
            run = session.get(ModelRun, rid)
            job = session.get(Job, run.job_id) if run else None
            if (
                not run
                or not job
                or job.project_id != project_id
                or run.provider == "mock"
                or run.document_version_id != nodes[relation.source_id].document_version_id
                or run.prompt_name != prompt
                or run.status != "succeeded"
                or run.input_hash != digest(wire)
                or run.parameters.get("input_manifest")
                != {"evidence_aliases": aliases, "snapshot_hash": attempt.snapshot_hash}
            ):
                return False
            raw = loads(run.raw_output or "")
            if prompt == "P04_compare_conditions":
                original = ComparabilityReport.model_validate(raw).model_dump(mode="json")
                if resolve_ids(original, aliases) != report.model_dump(mode="json"):
                    return False
                wire["comparability_report"] = original
            elif resolve_ids(
                RelationInference.model_validate(raw).model_dump(mode="json"), aliases
            ) != output.model_dump(mode="json"):
                return False
    except (KnowledgeError, ValidationError, KeyError, TypeError, ValueError):
        return False
    return True


def _relation_type(session: Session, aid: str) -> str:
    if aid.startswith("dependency:"):
        return aid.rsplit(":", 1)[-1]
    edge = session.get(SourceAssertion, aid)
    return edge.relation if edge else ""


def relation_snapshot_hash(session: Session, attempt_id: str) -> str:
    attempt = session.get(ReasoningAttempt, attempt_id)
    assert attempt
    return attempt.snapshot_hash


def expand_graph(
    session: Session,
    project_id: str,
    paper_ids: list[str],
    seed_node_ids: list[str],
    seed_chunk_ids: list[str],
) -> dict[str, Any]:
    """Expand related complete source paths; never create units, evidence or knowledge."""
    return _expand_graph(session, project_id, paper_ids, seed_node_ids, seed_chunk_ids)


def _expand_graph(
    session: Session,
    project_id: str,
    paper_ids: list[str],
    seed_node_ids: list[str],
    seed_chunk_ids: list[str],
    *,
    validated_nodes: list[KnowledgeNode] | None = None,
    include_comparison: bool = True,
) -> dict[str, Any]:
    """Internal same-call reuse; callers must not cache validated_nodes on Session.

    Retrieval validates all project candidates once before indexing, then passes
    that local list here synchronously in the same operation. Scope/current
    version, seed, support-edge and relation checks remain independent below.
    Public expand_graph always performs its own current-source validation.
    """
    scope_papers = {p.id for p in _papers(session, project_id, paper_ids)}
    latest: dict[str, str] = {}
    for version in session.scalars(
        select(AttachmentRevision)
        .where(AttachmentRevision.paper_id.in_(scope_papers))
        .order_by(AttachmentRevision.created_at.desc(), AttachmentRevision.id.desc())
    ):
        latest.setdefault(version.paper_id, version.id)
    valid_chunks = set(
        session.scalars(
            select(Chunk.id).where(
                Chunk.id.in_(seed_chunk_ids), Chunk.revision_id.in_(latest.values())
            )
        )
    )
    if set(seed_chunk_ids) - valid_chunks:
        raise KnowledgeError("QUERY_SEED_INVALID", "查询原文种子不存在或超出授权范围")
    if not seed_node_ids and not session.scalar(
        select(NodeEvidence.node_id)
        .join(EvidenceSpan, EvidenceSpan.id == NodeEvidence.evidence_id)
        .where(EvidenceSpan.paragraph_id.in_(seed_chunk_ids))
        .limit(1)
    ):
        return {
            "policy": "query-source-graph-1",
            "relation_expansion_policy": "seed-incident-scientific-1",
            "seed_node_ids": [],
            "seed_chunk_ids": sorted(set(seed_chunk_ids)),
            "effective_seed_node_ids": [],
            "nodes": [],
            "paths": [],
            "associations": [],
            "relations": [],
            "conditions": [],
            "comparison": [],
        }
    nodes = {
        n.id: n
        for n in (
            eligible_nodes(session, project_id, paper_ids)
            if validated_nodes is None
            else validated_nodes
        )
        if n.paper_id in scope_papers and n.document_version_id == latest.get(n.paper_id)
    }
    store = KnowledgeStore(session).reading()
    by_version: dict[str, dict[str, KnowledgeNode]] = defaultdict(dict)
    for node in nodes.values():
        by_version[node.document_version_id][node.id] = node
    paths = {
        v: support_paths(store, v, group, prevalidated=True) for v, group in by_version.items()
    }
    closures = {
        n.id: reachable_supports(
            n.id, by_version[n.document_version_id], paths[n.document_version_id]
        )
        for n in nodes.values()
        if n.kind == "claim"
    }
    if set(seed_node_ids) - nodes.keys():
        raise KnowledgeError("QUERY_SEED_INVALID", "查询种子来源已失效或超出授权范围")
    seeds = set(seed_node_ids)
    if seed_chunk_ids:
        seeds.update(
            session.scalars(
                select(NodeEvidence.node_id)
                .join(EvidenceSpan, EvidenceSpan.id == NodeEvidence.evidence_id)
                .where(
                    EvidenceSpan.paragraph_id.in_(seed_chunk_ids),
                    NodeEvidence.node_id.in_(nodes),
                )
            )
        )
    roots = {root for root, closure in closures.items() if seeds & closure.keys()}
    original_roots = set(roots)
    relations = []
    for relation in session.scalars(
        select(RelationAssertion)
        .where(RelationAssertion.project_id == project_id)
        .order_by(RelationAssertion.id)
    ):
        if not ({relation.source_id, relation.target_id} & original_roots):
            continue
        if _valid_relation(session, relation, project_id, nodes, closures, paths):
            roots.update([relation.source_id, relation.target_id])
            relations.append(
                {
                    "id": relation.id,
                    "source_id": relation.source_id,
                    "target_id": relation.target_id,
                    "type": relation.relation_type,
                    "evidence_ids": sorted(relation.evidence_ids),
                    "revision": relation.revision,
                    "attempt_id": relation.attempt_id,
                    "snapshot_hash": relation_snapshot_hash(session, relation.attempt_id),
                    "epistemic_status": "model_inferred",
                }
            )
    selected = set(seeds)
    expanded_paths = []
    used_associations = set()
    units_by_root: dict[str, list[ReadingUnit]] = defaultdict(list)
    for unit in session.scalars(select(ReadingUnit).where(ReadingUnit.root_claim_id.in_(roots))):
        if unit.document_version_id == nodes[unit.root_claim_id].document_version_id:
            units_by_root[unit.root_claim_id].append(unit)
    members_by_unit: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    unit_ids_all = [u.id for group in units_by_root.values() for u in group]
    for member in session.scalars(
        select(ReadingMember).where(ReadingMember.unit_id.in_(unit_ids_all))
    ):
        members_by_unit[member.unit_id].append((member.node_id, member.association_ids))
    for root in sorted(roots):
        reached = closures[root]
        selected.update(reached)
        unit_ids = []
        for unit in units_by_root[root]:
            members = members_by_unit[unit.id]
            try:
                validate_member_paths(
                    store,
                    unit.document_version_id,
                    root,
                    members,
                    by_version[unit.document_version_id],
                    paths[unit.document_version_id],
                )
            except (KnowledgeError, KeyError):
                continue
            if {n for n, _ in members} == set(reached) - {root}:
                unit_ids.append(unit.id)
        for nid, aids in sorted(reached.items()):
            expanded_paths.append(
                {
                    "root_id": root,
                    "node_id": nid,
                    "association_ids": aids,
                    "unit_ids": sorted(unit_ids),
                    **({"unit_id": min(unit_ids)} if unit_ids else {}),
                }
            )
            used_associations.update(aids)
        # Retain every validated path edge among these members, not just BFS parents.
        used_associations.update(
            aid
            for a, b, aid in paths[nodes[root].document_version_id]
            if a in reached and b in reached and b != root
        )
    refs: dict[str, list[str]] = defaultdict(list)
    for link in session.scalars(select(NodeEvidence).where(NodeEvidence.node_id.in_(selected))):
        refs[link.node_id].append(link.evidence_id)
    associations = []
    for aid in sorted(used_associations):
        if aid.startswith("dependency:"):
            matched = next((a, b) for vp in paths.values() for a, b, key in vp if key == aid)
            associations.append(
                {
                    "id": aid,
                    "source_id": matched[0],
                    "target_id": matched[1],
                    "type": _relation_type(session, aid),
                    "evidence_ids": sorted(set(refs[matched[0]]) | set(refs[matched[1]])),
                    "dependency": True,
                }
            )
        else:
            assertion = session.get(SourceAssertion, aid)
            assert assertion
            associations.append(
                {
                    "id": aid,
                    "source_id": assertion.source_id,
                    "target_id": assertion.target_id,
                    "type": assertion.relation,
                    "evidence_ids": sorted(assertion.evidence_ids),
                    "dependency": False,
                }
            )
    return {
        "policy": "query-source-graph-1",
        "relation_expansion_policy": "seed-incident-scientific-1",
        "seed_node_ids": sorted(set(seed_node_ids)),
        "seed_chunk_ids": sorted(set(seed_chunk_ids)),
        "effective_seed_node_ids": sorted(seeds),
        "nodes": [
            {
                "id": nid,
                "kind": nodes[nid].kind,
                "text": nodes[nid].text,
                "payload": nodes[nid].payload,
                "revision": nodes[nid].revision,
                "document_version_id": nodes[nid].document_version_id,
                "paper_id": nodes[nid].paper_id,
                "origin": nodes[nid].origin,
                "authorship": nodes[nid].authorship,
                "evidence_ids": sorted(refs[nid]),
                "issues": nodes[nid].issues,
            }
            for nid in sorted(selected)
        ],
        "paths": expanded_paths,
        "associations": associations,
        "relations": relations,
        "conditions": [
            _condition(nodes[nid], sorted(refs[nid]))
            for nid in sorted(selected)
            if nodes[nid].kind == "condition"
        ],
        "comparison": _compare(sorted(roots), nodes, closures) if include_comparison else [],
    }
