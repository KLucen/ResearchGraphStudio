"""Single transactional entry for evidence, knowledge and human review mutations."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.knowledge_contracts import (
    ClaimDraft,
    ConceptDraft,
    Condition,
    ExperimentDraft,
    ExtractionBatch,
    FindingDraft,
    KnownState,
    MethodDraft,
    NodeView,
    PaperOutline,
    ResearchQuestionDraft,
    ReviewRequest,
)
from researchgraph.knowledge_models import (
    EvidenceSpan,
    GraphRevision,
    KnowledgeDependency,
    KnowledgeNode,
    KnowledgeOperation,
    ModelRun,
    NodeEvidence,
    ReviewDecision,
    Section,
)
from researchgraph.models import AttachmentRevision, Chunk, Event, Paper, now

DOMAIN_VERSION = "knowledge-v2.1"
NODE_TYPES: dict[str, type[BaseModel]] = {
    "claim": ClaimDraft,
    "concept": ConceptDraft,
    "method": MethodDraft,
    "experiment": ExperimentDraft,
    "condition": Condition,
    "finding": FindingDraft,
    "research_question": ResearchQuestionDraft,
}


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
    return str(uuid5(NAMESPACE_URL, f"researchgraph/{kind}/{value}"))


def validate_evidence(session: Session, evidence: EvidenceSpan, version_id: str) -> None:
    chunk = session.get(Chunk, evidence.paragraph_id)
    if (
        chunk is None
        or evidence.document_version_id != version_id
        or chunk.revision_id != version_id
        or chunk.page_index != evidence.page_index
        or evidence.normalization != "identity-v1"
        or not 0 <= evidence.start_offset < evidence.end_offset <= len(chunk.text)
        or evidence.quote != chunk.text[evidence.start_offset : evidence.end_offset]
        or evidence.text_sha256 != text_hash(chunk.text)
        or evidence.bbox_list != [chunk.bbox]
    ):
        raise KnowledgeError("INVALID_ANCHOR", "证据的版本、页码、文本偏移或原文哈希不匹配")
    section = session.get(Section, evidence.section_id)
    if section is None or section.document_version_id != version_id:
        raise KnowledgeError("INVALID_ANCHOR", "证据章节不属于该文献版本")


class KnowledgeStore:
    """Caller owns a Session.begin transaction; no method commits partial results."""

    def __init__(self, session: Session):
        self.session = session

    def apply_translation(
        self, candidate: dict[str, Any], snapshot: dict[str, Any], run_id: str, key: str
    ) -> dict[str, Any]:
        from researchgraph.translation import apply_translation

        return apply_translation(self, candidate, snapshot, run_id, key)

    def apply_unified(self, **request: Any) -> dict[str, Any]:
        from researchgraph.unified_store import apply_unified

        return apply_unified(self, **request)

    def reading(self) -> Any:
        from researchgraph.reading_store import ReadingMutations

        return ReadingMutations(self)

    def apply_document_structure(
        self, version_id: str, source_hash: str, structure: dict[str, Any]
    ) -> Any:
        from researchgraph.document_structure import apply_structure

        return apply_structure(self, version_id, source_hash, structure)

    def apply_reasoning(self, **request: Any) -> dict[str, Any]:
        from researchgraph.reasoning_store import ReasoningMutations

        return ReasoningMutations(self).apply(**request)

    def review_semantic(self, request: Any, key: str) -> Any:
        from researchgraph.reasoning_store import ReasoningMutations

        return ReasoningMutations(self).review(request, key)

    def import_annotations(
        self,
        version_id: str,
        library: str,
        item_key: str,
        attachment_key: str,
        metadata: dict[str, Any],
        annotations: list[dict[str, Any]],
        path: Path,
    ) -> dict[str, int]:
        from researchgraph.integrations import AnnotationImporter

        return AnnotationImporter(self).apply(
            version_id, library, item_key, attachment_key, metadata, annotations, path
        )

    def scan_notes(self, root_id: str) -> dict[str, int]:
        from researchgraph.integrations import ObsidianReader

        return ObsidianReader(self.session).scan(root_id)

    def source_version_added(self, paper_id: str, version_id: str) -> None:
        paper = self.session.get(Paper, paper_id)
        assert paper
        affected = []
        for node in self.session.scalars(
            select(KnowledgeNode).where(
                KnowledgeNode.paper_id == paper_id, KnowledgeNode.document_version_id != version_id
            )
        ):
            if "new_document_version_available" not in node.issues:
                node.issues = [*node.issues, "new_document_version_available"]
                affected.append(node.id)
        if affected:
            self.event(
                paper.project_id,
                "SOURCE_VERSION_ADDED",
                {"document_version_id": version_id, "affected_node_ids": affected},
                trigger="pdf_import",
            )

    def graph_revision(self, project_id: str) -> int:
        graph = self.session.get(GraphRevision, project_id)
        return graph.revision if graph else 0

    def event(
        self,
        project_id: str,
        event_type: str,
        payload: dict[str, Any],
        actor: str = "system",
        model_run_id: str | None = None,
        trigger: str = "ingest",
    ) -> int:
        graph = self.session.get(GraphRevision, project_id)
        if graph is None:
            graph = GraphRevision(project_id=project_id, revision=0)
            self.session.add(graph)
            self.session.flush()
        before = graph.revision
        graph.revision += 1
        self.session.add(
            Event(
                event_id=str(uuid4()),
                project_id=project_id,
                event_type=event_type,
                payload=payload,
                created_at=now(),
                actor=actor,
                model_run_id=model_run_id,
                before_revision=before,
                after_revision=graph.revision,
                trigger=trigger,
            )
        )
        return graph.revision

    def ensure_document(self, version_id: str) -> None:
        version = self.session.get(AttachmentRevision, version_id)
        if version is None:
            raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
        if self.session.scalar(select(Section).where(Section.document_version_id == version_id)):
            return
        from researchgraph.document_structure import current_structure, index_structure

        artifact = current_structure(self.session, version_id)
        if artifact:
            index_structure(self, artifact)
            paper = self.session.get(Paper, version.paper_id)
            assert paper
            self.event(paper.project_id, "EVIDENCE_INDEXED", {"document_version_id": version_id})
            return
        paper = self.session.get(Paper, version.paper_id)
        assert paper
        chunks = self.session.scalars(
            select(Chunk)
            .where(Chunk.revision_id == version_id)
            .order_by(Chunk.page_index, Chunk.block_index)
        ).all()
        section: Section | None = None
        page = -1
        ordinal = 0
        for chunk in chunks:
            first = chunk.text.strip().splitlines()[0]
            heading = (
                bool(
                    re.fullmatch(
                        r"(?:\d+[.\s]*)?(?:abstract|introduction|background|related work|methods?|"
                        r"experiments?|results?|discussion|conclusions?|limitations?)(?:\s*[:.])?",
                        first,
                        re.I,
                    )
                )
                and len(chunk.text.strip()) < 100
            )
            if section is None or heading or chunk.page_index != page:
                section = Section(
                    id=stable_id("section", chunk.id),
                    document_version_id=version_id,
                    title=first if heading else f"PDF 第 {chunk.page_index + 1} 页",
                    ordinal=ordinal,
                    role="other",
                    parser="blocks-sections-v1",
                )
                ordinal += 1
                self.session.add(section)
                self.session.flush()
            page = chunk.page_index
            # Bound model input without truncating the document; retain exact source intervals.
            for start in range(0, len(chunk.text), 6000):
                end = min(start + 6000, len(chunk.text))
                self.session.add(
                    EvidenceSpan(
                        id=stable_id("evidence", f"{chunk.id}:{start}:{end}"),
                        document_version_id=version_id,
                        section_id=section.id,
                        paragraph_id=chunk.id,
                        page_index=chunk.page_index,
                        start_offset=start,
                        end_offset=end,
                        quote=chunk.text[start:end],
                        text_sha256=text_hash(chunk.text),
                        normalization="identity-v1",
                        bbox_list=[chunk.bbox],
                    )
                )
        if chunks:
            self.event(paper.project_id, "EVIDENCE_INDEXED", {"document_version_id": version_id})

    def apply_outline(
        self,
        version_id: str,
        outline: PaperOutline,
        allowed_sections: set[str],
        allowed_paragraphs: set[str],
        model_run_id: str,
    ) -> None:
        seen: set[str] = set()
        for item in outline.sections:
            if item.section_id not in allowed_sections or item.section_id in seen:
                raise KnowledgeError("INVALID_SECTION", "模型返回了不存在或重复的章节")
            seen.add(item.section_id)
            actual = set(
                self.session.scalars(
                    select(EvidenceSpan.paragraph_id).where(
                        EvidenceSpan.section_id == item.section_id
                    )
                ).all()
            )
            if not set(item.paragraph_ids) <= (allowed_paragraphs & actual):
                raise KnowledgeError("INVALID_PARAGRAPH", "模型段落不属于所提供章节")
        if not set(outline.unresolved_sections) <= allowed_sections:
            raise KnowledgeError("INVALID_SECTION", "无法识别的章节 ID 不在本次输入中")
        version = self.session.get(AttachmentRevision, version_id)
        assert version
        paper = self.session.get(Paper, version.paper_id)
        assert paper
        changed = []
        for item in outline.sections:
            section = self.session.get(Section, item.section_id)
            assert section
            if section.role != item.role:
                changed.append({"id": section.id, "before": section.role, "after": item.role})
                section.role = item.role
        if changed:
            self.event(
                paper.project_id,
                "OUTLINE_CLASSIFIED",
                {"changes": changed},
                model_run_id=model_run_id,
            )

    def apply(
        self,
        candidate_batch: dict[str, Any],
        version_id: str,
        allowed_evidence_ids: set[str],
        model_run_id: str,
        idempotency_key: str,
        expected_graph_revision: int | None = None,
    ) -> dict[str, Any]:
        batch = ExtractionBatch.model_validate(candidate_batch)
        version = self.session.get(AttachmentRevision, version_id)
        if (
            version is None
            or version.paper_id != batch.paper_id
            or batch.schema_version != DOMAIN_VERSION
        ):
            raise KnowledgeError("SOURCE_MISMATCH", "论文、文献版本或领域 Schema 不匹配")
        paper = self.session.get(Paper, batch.paper_id)
        run = self.session.get(ModelRun, model_run_id)
        if paper is None or run is None or run.document_version_id != version_id:
            raise KnowledgeError("MODEL_RUN_MISMATCH", "模型运行来源不匹配")
        request_hash = digest(
            {
                "version": version_id,
                "batch": batch.model_dump(
                    mode="json",
                    exclude={"research_questions"} if not batch.research_questions else set(),
                ),
            }
        )
        previous = self.session.get(KnowledgeOperation, idempotency_key)
        if previous:
            if previous.request_hash != request_hash:
                raise KnowledgeError("IDEMPOTENCY_CONFLICT", "操作标识已用于其他抽取结果")
            return previous.response
        if (
            expected_graph_revision is not None
            and self.graph_revision(paper.project_id) != expected_graph_revision
        ):
            raise KnowledgeError("REVISION_CONFLICT", "知识图谱已更新，请刷新后重试")
        drafts: list[tuple[str, BaseModel]] = []
        draft_groups: list[tuple[str, list[Any]]] = [
            ("concept", batch.concepts),
            ("method", batch.methods),
            ("experiment", batch.experiments),
            ("claim", batch.claims),
            ("finding", batch.findings),
            ("research_question", batch.research_questions),
        ]
        for kind, items in draft_groups:
            drafts.extend((kind, item) for item in items)
        if len(drafts) > 250:
            raise KnowledgeError("BATCH_TOO_LARGE", "单批知识对象超过 250 项限制")
        ref_kinds: dict[str, str] = {}
        evidence: dict[str, EvidenceSpan] = {}
        for kind, draft in drafts:
            data = draft.model_dump(mode="json")
            ref = str(data["local_ref"])
            if not ref or ref in ref_kinds:
                raise KnowledgeError("DUPLICATE_LOCAL_REF", "模型局部引用为空或重复")
            ref_kinds[ref] = kind
            for evidence_id in self.evidence_ids(data):
                if evidence_id not in allowed_evidence_ids:
                    raise KnowledgeError("UNKNOWN_EVIDENCE", "模型引用了本次输入之外的证据")
                span = self.session.get(EvidenceSpan, evidence_id)
                if span is None:
                    raise KnowledgeError("UNKNOWN_EVIDENCE", "模型证据 ID 不存在")
                validate_evidence(self.session, span, version_id)
                evidence[evidence_id] = span
        for _, draft in drafts:
            data = draft.model_dump(mode="json")
            for ref in data.get("method_local_refs", []):
                if ref_kinds.get(ref) != "method":
                    raise KnowledgeError("INVALID_LOCAL_REF", "方法引用不存在或类型错误")
            exp = data.get("experiment_local_ref")
            if exp and ref_kinds.get(exp) != "experiment":
                raise KnowledgeError("INVALID_LOCAL_REF", "实验引用不存在或类型错误")
        refs: dict[str, str] = {}
        saved: list[str] = []
        created: list[str] = []
        for kind, draft in drafts:
            data = draft.model_dump(mode="json")
            if kind in {"claim", "experiment"}:
                present = {condition["dimension"] for condition in data["conditions"]}
                for dimension in ("task_type", "dataset", "metric"):
                    if dimension not in present:
                        data["conditions"].append(
                            Condition(
                                dimension=dimension, value=None, known_state=KnownState.UNKNOWN
                            ).model_dump(mode="json")
                        )
            # Exact local resolution only; no semantic entity merge in P2.
            identity = {
                key: value
                for key, value in data.items()
                if key != "local_ref" and not key.endswith("_zh")
            }
            if "method_local_refs" in identity:
                identity["method_local_refs"] = [refs[r] for r in identity["method_local_refs"]]
            if identity.get("experiment_local_ref"):
                identity["experiment_local_ref"] = refs[identity["experiment_local_ref"]]
            node, is_new = self._node(kind, data, identity, paper, version, model_run_id, evidence)
            refs[data["local_ref"]] = node.id
            saved.append(node.id)
            if is_new:
                created.append(node.id)
                for method_ref in data.get("method_local_refs", []):
                    self._dependency(node.id, refs[method_ref], "USES_METHOD")
                if data.get("experiment_local_ref"):
                    self._dependency(node.id, refs[data["experiment_local_ref"]], "IN_EXPERIMENT")
                for condition in data.get("conditions", []):
                    cond, new = self._node(
                        "condition", condition, condition, paper, version, model_run_id, evidence
                    )
                    self._dependency(node.id, cond.id, "HAS_CONDITION")
                    if new:
                        created.append(cond.id)
                if kind == "finding" and data.get("metric_name"):
                    metric_data = {
                        "name": data["metric_name"],
                        "unit": data.get("unit"),
                        "direction": "unknown",
                        "evidence_span_ids": data["evidence_span_ids"],
                    }
                    metric, new = self._node(
                        "metric", metric_data, metric_data, paper, version, model_run_id, evidence
                    )
                    self._dependency(node.id, metric.id, "MEASURES")
                    if new:
                        created.append(metric.id)
        revision = self.graph_revision(paper.project_id)
        if created:
            revision = self.event(
                paper.project_id,
                "KNOWLEDGE_EXTRACTED",
                {"document_version_id": version_id, "created_ids": created},
                model_run_id=model_run_id,
            )
        response = {
            "node_ids": saved,
            "created_ids": created,
            "new_revision": revision,
            "local_refs": refs,
        }
        self.session.add(
            KnowledgeOperation(key=idempotency_key, request_hash=request_hash, response=response)
        )
        return response

    @staticmethod
    def evidence_ids(data: dict[str, Any]) -> set[str]:
        ids = set(data.get("evidence_span_ids", []))
        ids.update(e["evidence_span_id"] for e in data.get("evidence", []))
        for condition in data.get("conditions", []):
            ids.update(condition.get("evidence_span_ids", []))
        return ids

    def _node(
        self,
        kind: str,
        data: dict[str, Any],
        identity: dict[str, Any],
        paper: Paper,
        version: AttachmentRevision,
        run_id: str,
        evidence: dict[str, EvidenceSpan],
    ) -> tuple[KnowledgeNode, bool]:
        fingerprint = digest({"kind": kind, "data": identity})
        existing = self.session.scalar(
            select(KnowledgeNode).where(
                KnowledgeNode.document_version_id == version.id,
                KnowledgeNode.fingerprint == fingerprint,
            )
        )
        if existing:
            return existing, False
        ids = self.evidence_ids(data)
        source = "\n".join(evidence[i].quote for i in sorted(ids))
        text = str(
            data.get("statement")
            or data.get("canonical_name")
            or data.get("name")
            or data.get("label")
            or data.get("dimension")
            or ""
        )
        issues = self.issues(kind, data, source)
        origin = str(data.get("origin", "author_claim"))
        node = KnowledgeNode(
            id=str(uuid4()),
            paper_id=paper.id,
            document_version_id=version.id,
            kind=kind,
            text=text,
            payload=data,
            origin=origin,
            authorship="paper_author",
            source_status="source_verified" if ids else "unverified",
            review_status="needs_review" if issues else "unreviewed",
            issues=issues,
            dimension=data.get("dimension"),
            known_state=data.get("known_state"),
            value=data.get("value"),
            unit=data.get("unit"),
            fingerprint=fingerprint,
            model_run_id=run_id,
            revision=1,
            created_at=now(),
            updated_at=now(),
        )
        self.session.add(node)
        self.session.flush()
        roles = {e["evidence_span_id"]: e["role"] for e in data.get("evidence", [])}
        for eid in ids:
            self.session.add(
                NodeEvidence(node_id=node.id, evidence_id=eid, role=roles.get(eid, "direct"))
            )
        return node, True

    @staticmethod
    def issues(kind: str, data: dict[str, Any], source: str) -> list[str]:
        issues: list[str] = []
        if data.get("origin") in {"unknown", "cited_claim", "background"}:
            issues.append("attribution_review_required")
        if data.get("origin") == "authors_experimental_result" and re.search(
            r"\b(?:et al\.?|previous work|prior work|according to)\b", source, re.I
        ):
            issues.append("possible_cited_claim")
        if (
            kind == "finding"
            or data.get("value") is not None
            or re.search(r"\d", str(data.get("statement", "")))
        ):
            issues.append("numerical_review_required")
            for key in ("value", "unit"):
                value = data.get(key)
                if value is not None and str(value) not in source:
                    issues.append(f"{key}_not_in_evidence")
        if data.get("known_state") in {"unknown", "conflicting"}:
            issues.append("condition_" + str(data["known_state"]))
        if any(c["known_state"] in {"unknown", "conflicting"} for c in data.get("conditions", [])):
            issues.append("incomplete_conditions")
        return issues

    def _dependency(self, node_id: str, dependee_id: str, role: str) -> None:
        if self.session.get(KnowledgeDependency, (node_id, dependee_id, role)) is None:
            self.session.add(
                KnowledgeDependency(node_id=node_id, dependee_id=dependee_id, role=role)
            )

    def review(self, request: ReviewRequest, key: str) -> NodeView:
        request_hash = digest(request.model_dump(mode="json"))
        previous = self.session.get(KnowledgeOperation, key)
        if previous:
            if previous.request_hash != request_hash:
                raise KnowledgeError("IDEMPOTENCY_CONFLICT", "审核标识已用于不同请求")
            return NodeView.model_validate(previous.response)
        node = self.session.get(KnowledgeNode, request.node_id)
        if node is None:
            raise KnowledgeError("NODE_NOT_FOUND", "知识对象不存在")
        paper = self.session.get(Paper, node.paper_id)
        assert paper
        if (
            node.revision != request.expected_revision
            or self.graph_revision(paper.project_id) != request.expected_graph_revision
        ):
            raise KnowledgeError("REVISION_CONFLICT", "知识已更新，请刷新后再审核")
        before = NodeView.model_validate(node).model_dump(mode="json")
        if request.action == "revise":
            schema = NODE_TYPES.get(node.kind)
            if schema is None or request.payload is None:
                raise KnowledgeError("INVALID_REVISION", "该类型或修订内容不受支持")
            data = schema.model_validate(request.payload).model_dump(mode="json")
            # Structural links stay fixed in P2; editing semantic fields is explicit review.
            protected = {
                "local_ref",
                "evidence",
                "evidence_span_ids",
                "conditions",
                "method_local_refs",
                "experiment_local_ref",
            }
            if any(data.get(k) != node.payload.get(k) for k in protected):
                raise KnowledgeError(
                    "LINK_CHANGE_REQUIRES_REEXTRACTION",
                    "本阶段修订保留证据和依赖，请通过重新抽取增加候选",
                )
            node.payload = data
            node.text = str(
                data.get("statement")
                or data.get("canonical_name")
                or data.get("name")
                or data.get("label")
                or data.get("dimension")
                or ""
            )
            node.origin = str(data.get("origin", node.origin))
            node.value, node.unit = data.get("value"), data.get("unit")
            node.dimension = data.get("dimension")
            node.known_state = data.get("known_state")
            node.review_status = "needs_review"
            spans = self.session.scalars(
                select(EvidenceSpan)
                .join(NodeEvidence, NodeEvidence.evidence_id == EvidenceSpan.id)
                .where(NodeEvidence.node_id == node.id)
            ).all()
            node.issues = self.issues(node.kind, data, "\n".join(s.quote for s in spans))
        else:
            if request.payload is not None:
                raise KnowledgeError("INVALID_REVISION", "接受或驳回不能同时改写内容")
            node.review_status = "accepted" if request.action == "accept" else "rejected"
        # Reject remains possible for invalid evidence; accepting never bypasses anchor validation.
        if request.action != "reject":
            for span in self.session.scalars(
                select(EvidenceSpan)
                .join(NodeEvidence, NodeEvidence.evidence_id == EvidenceSpan.id)
                .where(NodeEvidence.node_id == node.id)
            ):
                validate_evidence(self.session, span, node.document_version_id)
        node.revision += 1
        node.updated_at = now()
        after = NodeView.model_validate(node).model_dump(mode="json")
        self.session.add(
            ReviewDecision(
                id=str(uuid4()),
                node_id=node.id,
                action=request.action,
                actor="user",
                reason=request.reason,
                before=before,
                after=after,
                created_at=now(),
            )
        )
        self.event(
            paper.project_id,
            "KNOWLEDGE_REVIEWED",
            {"node_id": node.id, "before": before, "after": after, "reason": request.reason},
            actor="user",
            trigger="human_review",
        )
        self.session.add(KnowledgeOperation(key=key, request_hash=request_hash, response=after))
        return NodeView.model_validate(node)
