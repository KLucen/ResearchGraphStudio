"""Transactional reading mutations behind KnowledgeStore; immutable source content."""

from typing import Any

from sqlalchemy import select

from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun, NodeEvidence
from researchgraph.knowledge_store import (
    KnowledgeError,
    KnowledgeStore,
    digest,
    stable_id,
    validate_evidence,
)
from researchgraph.models import AttachmentRevision, Paper, now
from researchgraph.reading_models import (
    CandidateMetadata,
    ReadingCheckpoint,
    ReadingHead,
    ReadingSelection,
)

POLICY = "reading-rules-1.0"


class ReadingMutations:
    def __init__(self, store: KnowledgeStore):
        self.store, self.session = store, store.session

    def integrate(self, **request: Any) -> dict[str, Any]:
        from researchgraph.reading_selection import integrate

        return integrate(self, **request)

    def publish(self, **request: Any) -> dict[str, Any]:
        from researchgraph.reading_selection import publish

        return publish(self, **request)

    def set_preference(self, node_id: str, action: str, reason: str) -> None:
        from researchgraph.reading_models import ReadingPreference

        if action not in {"include_core", "exclude_core", "reset_automatic"}:
            raise KnowledgeError("INVALID_PREFERENCE", "未知显示偏好")
        if not self.session.get(KnowledgeNode, node_id):
            raise KnowledgeError("NODE_NOT_FOUND", "候选不存在")
        stored = self.session.get(ReadingPreference, node_id)
        if stored:
            stored.action, stored.reason = action, reason
        else:
            self.session.add(ReadingPreference(node_id=node_id, action=action, reason=reason))
        self.session.flush()

    def source(self, version_id: str) -> tuple[AttachmentRevision, Paper]:
        version = self.session.get(AttachmentRevision, version_id)
        paper = self.session.get(Paper, version.paper_id) if version else None
        if not version or not paper:
            raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
        return version, paper

    def checkpoint(self, key: str, fingerprint: str) -> dict[str, Any] | None:
        row = self.session.get(ReadingCheckpoint, key)
        if row and row.input_hash != fingerprint:
            raise KnowledgeError("READING_INPUT_CHANGED", "阶段输入已变化，请创建新构建")
        return row.response if row else None

    def save_checkpoint(
        self, key: str, version_id: str, stage: str, fingerprint: str, response: dict[str, Any]
    ) -> dict[str, Any]:
        cached = self.checkpoint(key, fingerprint)
        if cached is not None:
            return cached
        self.source(version_id)
        self.session.add(
            ReadingCheckpoint(
                key=key,
                document_version_id=version_id,
                stage=stage,
                input_hash=fingerprint,
                response=response,
            )
        )
        return response

    def nodes(self, version_id: str) -> list[KnowledgeNode]:
        self.source(version_id)
        return list(
            self.session.scalars(
                select(KnowledgeNode)
                .where(KnowledgeNode.document_version_id == version_id)
                .order_by(KnowledgeNode.id)
            )
        )

    def snapshot(self, version_id: str) -> str:
        version, _ = self.source(version_id)
        return digest(
            {
                "source": version.sha256,
                "evidence": [
                    [
                        e.id,
                        e.paragraph_id,
                        e.page_index,
                        e.start_offset,
                        e.end_offset,
                        e.quote,
                        e.text_sha256,
                        e.bbox_list,
                    ]
                    for e in self.session.scalars(
                        select(EvidenceSpan)
                        .where(EvidenceSpan.document_version_id == version_id)
                        .order_by(EvidenceSpan.id)
                    )
                ],
                "nodes": [
                    [
                        n.id,
                        n.revision,
                        n.payload,
                        n.source_status,
                        n.review_status,
                        sorted(
                            self.session.scalars(
                                select(NodeEvidence.evidence_id).where(NodeEvidence.node_id == n.id)
                            )
                        ),
                    ]
                    for n in self.nodes(version_id)
                ],
            }
        )

    def source_valid(self, node: KnowledgeNode) -> bool:
        if node.review_status in {"rejected", "superseded"}:
            return False
        if "new_document_version_available" in node.issues:
            return False
        if node.source_status != "source_verified":
            return False
        spans = list(
            self.session.scalars(
                select(EvidenceSpan)
                .join(NodeEvidence, NodeEvidence.evidence_id == EvidenceSpan.id)
                .where(NodeEvidence.node_id == node.id)
            )
        )
        if not spans:
            return False
        try:
            for span in spans:
                validate_evidence(self.session, span, node.document_version_id)
        except KnowledgeError:
            return False
        return True

    def adapt(self, version_id: str) -> int:
        """Legacy IDs/content/review/output stay byte-for-byte unchanged."""
        count = 0
        for node in self.nodes(version_id):
            if self.session.get(CandidateMetadata, node.id):
                continue
            valid = self.source_valid(node)
            self.session.add(
                CandidateMetadata(
                    node_id=node.id,
                    canonical_id=None,
                    policy_version=POLICY,
                    validation_status="valid" if valid else "quarantined",
                    quality={
                        "relevance": "unresolved",
                        "duplicate_status": "unresolved",
                        "evidence_completeness": "limited" if valid else "insufficient",
                        "blocking_issues": [] if valid else ["source_or_history_excluded"],
                        "caveats": ["legacy_candidate_requires_integration"],
                        "rationale": "保留旧候选，未自动重抽或改写",
                        "assessed_by": "rules",
                        "policy_version": POLICY,
                    },
                )
            )
            count += 1
        self.session.flush()
        return count

    def current(self, paper_id: str) -> ReadingSelection | None:
        head = self.session.get(ReadingHead, paper_id)
        return self.session.get(ReadingSelection, head.selection_id) if head else None

    def require_run(self, run_id: str, version_id: str) -> ModelRun:
        run = self.session.get(ModelRun, run_id)
        if not run or run.document_version_id != version_id:
            raise KnowledgeError("MODEL_RUN_INVALID", "模型运行与文献不匹配")
        return run

    def apply_candidates(
        self,
        candidate: dict[str, Any],
        version_id: str,
        paper_id: str,
        chunk_id: str,
        allowed: set[str],
        run_id: str,
        key: str,
    ) -> dict[str, Any]:
        from researchgraph.graph_models import KnowledgeDisplay, SourceAssertion
        from researchgraph.knowledge_models import KnowledgeOperation
        from researchgraph.reading_contracts import KnowledgeExtractionBatch
        from researchgraph.unified_store import evidence_ids

        batch = KnowledgeExtractionBatch.model_validate(candidate)
        _, paper = self.source(version_id)
        self.require_run(run_id, version_id)
        if (batch.document_version_id, batch.chunk_id, paper.id) != (
            version_id,
            chunk_id,
            paper_id,
        ):
            raise KnowledgeError("SOURCE_MISMATCH", "模型改变了输入版本或批次")
        fingerprint = digest(candidate)
        previous = self.session.get(KnowledgeOperation, key)
        if previous:
            if previous.request_hash != fingerprint:
                raise KnowledgeError("IDEMPOTENCY_CONFLICT", "批次内容已变化")
            return previous.response
        for eid in evidence_ids(candidate):
            span = self.session.get(EvidenceSpan, eid)
            if eid not in allowed or span is None:
                raise KnowledgeError("EVIDENCE_REF_INVALID", "引用了本批之外的证据")
            validate_evidence(self.session, span, version_id)
        ids: dict[str, str] = {}
        for item in batch.items:
            content = item.model_dump(mode="json")
            identity = {k: v for k, v in content.items() if k != "local_ref"}
            # Keep evidence and condition scope in identity; never dedup on label alone.
            identity["evidence_ids"] = sorted(item.evidence_ids)
            fp = digest({"contract": batch.contract_version, "content": identity})
            node_id = stable_id("reading-candidate", version_id + fp)
            ids[item.local_ref] = node_id
            if self.session.get(KnowledgeNode, node_id):
                continue
            primary = content.get("statement") or content.get("result") or content["summary"]
            self.session.add(
                KnowledgeNode(
                    id=node_id,
                    paper_id=paper_id,
                    document_version_id=version_id,
                    kind="research_question"
                    if item.kind == "ResearchQuestion"
                    else item.kind.lower(),
                    text=primary["original"],
                    payload=content,
                    origin="model_extraction",
                    authorship="paper_author" if item.origin == "paper_author" else "cited_other",
                    source_status="source_verified",
                    review_status="unreviewed",
                    issues=item.uncertainties,
                    dimension=content.get("dimension"),
                    known_state=content.get("state"),
                    value=(content.get("value") or {}).get("original"),
                    unit=content.get("unit"),
                    fingerprint=fp,
                    model_run_id=run_id,
                    revision=1,
                    created_at=now(),
                    updated_at=now(),
                )
            )
            self.session.flush()
            for eid in set(item.evidence_ids):
                self.session.add(NodeEvidence(node_id=node_id, evidence_id=eid, role="direct"))
            self.session.add(
                KnowledgeDisplay(
                    node_id=node_id,
                    model_run_id=run_id,
                    source_revision=1,
                    data={
                        "label_en": item.label.original,
                        "label_zh": item.label.zh or "",
                        "summary_en": item.summary.original,
                        "summary_zh": item.summary.zh or "",
                        "translation_status": "available" if item.label.zh else "missing",
                    },
                )
            )
        self.session.flush()
        for edge in batch.links:
            source, target = ids[edge.source_local_ref], ids[edge.target_local_ref]
            aid = stable_id(
                "reading-association",
                digest([source, target, edge.relation, sorted(edge.evidence_ids)]),
            )
            if not self.session.get(SourceAssertion, aid):
                self.session.add(
                    SourceAssertion(
                        id=aid,
                        project_id=paper.project_id,
                        source_id=source,
                        target_id=target,
                        relation=edge.relation,
                        evidence_ids=edge.evidence_ids,
                        model_run_id=run_id,
                    )
                )
        self.session.flush()
        self.adapt(version_id)
        response = {"node_ids": sorted(set(ids.values())), "warnings": batch.warnings}
        self.session.add(KnowledgeOperation(key=key, request_hash=fingerprint, response=response))
        self.store.event(
            paper.project_id, "candidate.batch_committed", response, model_run_id=run_id
        )
        return response
