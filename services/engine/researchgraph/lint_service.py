"""Deterministic, resumable diagnostics over authoritative sources, not canvas pages.

Only derived indexes/reports and non-scientific audit events are written here.
Each bounded advance is one transaction. A restart resumes the persisted ordinal;
changing any frozen input stops the run rather than mixing two different inputs.
"""

import hashlib
import re
from collections import deque
from time import perf_counter
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import (
    Annotation,
    AuthorizedRoot,
    EvidenceSpan,
    KnowledgeDependency,
    KnowledgeNode,
    NodeEvidence,
    NoteSnapshot,
    Section,
    ZoteroLink,
)
from researchgraph.knowledge_store import (
    KnowledgeError,
    KnowledgeStore,
    digest,
    text_hash,
    validate_evidence,
)
from researchgraph.lint_contracts import LintRequest
from researchgraph.lint_models import (
    DependencyCursor,
    DependencyIndex,
    LintIssue,
    LintOperation,
    LintRun,
)
from researchgraph.models import AttachmentRevision, Chunk, Event, Paper, PaperSource, Project, now
from researchgraph.query_documents import (
    file_state,
    note_allowed,
    read_authorized_file,
    validate_dependencies,
)
from researchgraph.query_models import (
    NoteUseGrant,
    QueryDocument,
    QueryDocumentVersion,
    QueryFileBinding,
    QueryPassage,
)
from researchgraph.reading_models import ReadingHead, ReadingMember, ReadingSelection, ReadingUnit
from researchgraph.reading_support import support_paths, validate_member_paths
from researchgraph.reasoning_models import RelationAssertion
from researchgraph.wiki_models import WikiFileBinding, WikiPage, WikiSection, WikiVersion

RULE_VERSION = "lint-rules-1"
# Codes, wording and severities are program-owned; model suggestions cannot add rules.
RULES: dict[str, tuple[str, str, str, str]] = {
    "SOURCE_UNAVAILABLE": (
        "warning",
        "evidence",
        "原始文件上次检查不可用",
        "重新定位原始来源；保留内部证据与历史",
    ),
    "SOURCE_UNCHECKED": (
        "info",
        "unverifiable",
        "原始文件尚无可用性检查记录",
        "在文献页显式检查来源，不能据此判断科学结论错误",
    ),
    "SOURCE_VERSION_STALE": (
        "warning",
        "dependency",
        "存在更新的文献版本",
        "按新版本重新构建；旧版本与原始证据保留",
    ),
    "EVIDENCE_INVALID": (
        "error",
        "evidence",
        "证据位置、哈希或来源归属不匹配",
        "检查原文定位后创建新构建，勿修改旧证据冒充有效",
    ),
    "NODE_EVIDENCE_MISSING": (
        "error",
        "evidence",
        "知识缺少完整的有效根证据",
        "重新核验来源及证据关联",
    ),
    "RELATION_BROKEN": (
        "error",
        "support",
        "关系端点、归属或证据无效",
        "检查关系与两端来源，不自动修改科学关系",
    ),
    "SUPPORT_PATH_INVALID": (
        "error",
        "support",
        "结论单元存在孤立成员或断开的合法支撑路径",
        "重新构建受影响结论单元",
    ),
    "SELECTION_INVALID": (
        "warning",
        "support",
        "默认图谱选择引用了缺失或不匹配的单元",
        "重新构建论文的阅读选择",
    ),
    "DEPENDENCY_INVALID": (
        "error",
        "dependency",
        "文档依赖无法通过当前来源校验",
        "检查逐段依赖与根证据，不静默重写原段落",
    ),
    "DEPENDENCY_STALE": (
        "warning",
        "dependency",
        "文档依赖的语义或文献版本已变化",
        "显式更新受影响段落并保留旧版本",
    ),
    "DEPENDENCY_UNVERIFIED": (
        "info",
        "unverifiable",
        "段落缺少可核验的来源追踪",
        "该段不能冒充已验证的论文事实",
    ),
    "ORGANIZATION_CHANGED": (
        "info",
        "dependency",
        "来源的核心选择或组织结构发生变化",
        "可显式重新整理；此提示不代表段落科学内容失效",
    ),
    "SUPPORT_CONTEXT_CHANGED": (
        "warning",
        "dependency",
        "引用知识的支撑路径发生变化",
        "回查受影响结论单元与段落；不自动改写原文或重发模型",
    ),
    "FILE_MODIFIED": (
        "warning",
        "file",
        "受管 Markdown 与登记字节不一致",
        "保留外部文本并显式登记编辑；不覆盖文件",
    ),
    "FILE_MISSING": (
        "warning",
        "file",
        "受管 Markdown 文件缺失",
        "检查导出目录；内部有效版本仍可按原依赖使用",
    ),
    "FILE_UNAVAILABLE": (
        "warning",
        "file",
        "受管 Markdown 未获当前读取授权或不可读",
        "检查目录授权与文件权限",
    ),
    "FILE_CONFLICT": (
        "warning",
        "file",
        "受管 Markdown 绑定存在版本冲突",
        "显式解决文件冲突，不覆盖私人文件",
    ),
    "MANAGED_IDENTITY_INVALID": (
        "error",
        "file",
        "受管 Markdown 身份或段落映射不匹配",
        "重新核对文件身份与段落 manifest",
    ),
    "PUBLICATION_PENDING": (
        "warning",
        "file",
        "受管 Markdown 发布尚未完成",
        "查看原发布操作并显式恢复；不重发模型或覆盖外部文件",
    ),
    "LINK_BROKEN": (
        "warning",
        "link",
        "已授权范围内的 Markdown 链接目标不存在",
        "检查或修正链接；Lint 不写文件",
    ),
    "LINK_UNVERIFIABLE": (
        "info",
        "unverifiable",
        "链接超出本次已授权登记范围，无法核验",
        "授权并登记所需文件后重新检查",
    ),
    "NOTE_CHANGED": (
        "info",
        "file",
        "私人笔记与登记快照不同或不可用",
        "显式刷新只读快照；个人观点不据此判科学错误",
    ),
    "NOTE_UNTRACKED": (
        "info",
        "unverifiable",
        "私人 Markdown 缺少逐段论文依赖信息",
        "仅确认可核验链接，不判定个人观点的科学正确性",
    ),
    "CONDITION_UNKNOWN": (
        "info",
        "condition",
        "实验条件为未知，属于信息缺口",
        "保留 unknown，不据此推断矛盾或补造条件",
    ),
    "CONDITION_CONFLICTING": (
        "warning",
        "condition",
        "条件显式记录为 conflicting",
        "回查原文中的备选值，不自动选择其中一个",
    ),
    "CONDITION_STATE_INVALID": (
        "error",
        "condition",
        "条件缺少合法状态",
        "明确区分 known、unknown、not_applicable、conflicting",
    ),
}


def _project(session: Session, project_id: str) -> None:
    if session.get(Project, project_id) is None:
        raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")


def _hash_row(row: Any) -> str:
    return digest(
        {
            c.key: getattr(row, c.key)
            for c in row.__table__.columns
            if c.key not in {"created_at", "updated_at"}
        }
    )


def _sequence(session: Session, project_id: str) -> int:
    return int(
        session.scalar(
            select(func.max(Event.sequence)).where(
                Event.project_id == project_id,
                Event.event_type.not_in(
                    {"LINT_STARTED", "LINT_FINISHED", "LINT_CANCELLED", "DEPENDENCY_INDEX_REBUILT"}
                ),
            )
        )
        or 0
    )


def _catalog(session: Session, project_id: str, scope: dict[str, Any]) -> list[dict[str, Any]]:
    """Hash authoritative current inputs, including file observations; no raw text retained."""
    _project(session, project_id)
    papers = list(session.scalars(select(Paper).where(Paper.project_id == project_id)))
    all_papers = {p.id for p in papers}
    chosen = set(scope.get("paper_ids", []))
    if chosen - all_papers:
        raise KnowledgeError("LINT_SCOPE_INVALID", "所选论文不属于当前项目")
    documents = list(
        session.scalars(select(QueryDocument).where(QueryDocument.project_id == project_id))
    )
    chosen_docs = set(scope.get("document_ids", []))
    if chosen_docs - {d.id for d in documents}:
        raise KnowledgeError("LINT_SCOPE_INVALID", "所选文档不属于当前项目")
    paper_ids = chosen or (set() if chosen_docs else all_papers)
    # Explicit paper-only scope does not silently claim all unrelated documents were scanned.
    docs = [d for d in documents if d.id in chosen_docs or (not chosen and not chosen_docs)]
    result: list[dict[str, Any]] = []

    def add(kind: str, row: Any, paper_id: str | None = None, extra: Any = None) -> None:
        result.append(
            {
                "type": kind,
                "id": row.id,
                "paper_id": paper_id,
                "fingerprint": digest([_hash_row(row), extra]),
            }
        )

    versions = list(
        session.scalars(
            select(AttachmentRevision).where(AttachmentRevision.paper_id.in_(paper_ids))
        )
    )
    version_papers = {v.id: v.paper_id for v in versions}
    version_ids = set(version_papers)
    observations_by_version: dict[str, list[list[Any]]] = {}
    for source_id, revision_id, mode, last_check in session.execute(
        select(
            PaperSource.id, PaperSource.revision_id, PaperSource.mode, PaperSource.last_check
        ).where(PaperSource.revision_id.in_(version_ids))
    ):
        observations_by_version.setdefault(revision_id, []).append(
            [source_id, mode, (last_check or {}).get("original"), (last_check or {}).get("managed")]
        )
    for version in versions:
        # Timestamps and path relocations do not change the scientific source identity.
        observations = sorted(observations_by_version.get(version.id, []))
        add("version", version, version.paper_id, observations)
    # Column projections preserve every hashed value, without allocating/retaining ORM
    # instances for the two largest input sets. This is freshly read on every call.
    for values in session.execute(
        select(Chunk.__table__)
        .where(Chunk.revision_id.in_(version_ids))
        .execution_options(yield_per=400)
    ).mappings():
        result.append(
            {
                "type": "chunk",
                "id": values["id"],
                "paper_id": version_papers[values["revision_id"]],
                "fingerprint": digest([digest(dict(values)), None]),
            }
        )
    section_hashes = {
        section.id: _hash_row(section)
        for section in session.scalars(
            select(Section).where(Section.document_version_id.in_(version_ids))
        )
    }
    for span in session.scalars(
        select(EvidenceSpan).where(EvidenceSpan.document_version_id.in_(version_ids))
    ):
        add(
            "evidence",
            span,
            version_papers[span.document_version_id],
            section_hashes.get(span.section_id),
        )
    node_links: dict[str, list[list[str]]] = {}
    for node_id, evidence_id, role in session.execute(
        select(NodeEvidence.node_id, NodeEvidence.evidence_id, NodeEvidence.role)
        .join(KnowledgeNode, KnowledgeNode.id == NodeEvidence.node_id)
        .where(KnowledgeNode.paper_id.in_(paper_ids))
    ):
        node_links.setdefault(node_id, []).append([evidence_id, role])
    node_dependencies: dict[str, list[list[str]]] = {}
    for node_id, dependee_id, role in session.execute(
        select(
            KnowledgeDependency.node_id, KnowledgeDependency.dependee_id, KnowledgeDependency.role
        )
        .join(KnowledgeNode, KnowledgeNode.id == KnowledgeDependency.node_id)
        .where(KnowledgeNode.paper_id.in_(paper_ids))
    ):
        node_dependencies.setdefault(node_id, []).append([dependee_id, role])
    node_papers: dict[str, str] = {}
    for values in session.execute(
        select(KnowledgeNode.__table__)
        .where(KnowledgeNode.paper_id.in_(paper_ids))
        .execution_options(yield_per=400)
    ).mappings():
        node_id = values["id"]
        node_papers[node_id] = values["paper_id"]
        hashed = {
            key: value for key, value in values.items() if key not in {"created_at", "updated_at"}
        }
        result.append(
            {
                "type": "node",
                "id": node_id,
                "paper_id": values["paper_id"],
                "fingerprint": digest(
                    [
                        digest(hashed),
                        [
                            sorted(node_links.get(node_id, [])),
                            sorted(node_dependencies.get(node_id, [])),
                        ],
                    ]
                ),
            }
        )
    for assertion in session.scalars(
        select(SourceAssertion).where(SourceAssertion.project_id == project_id)
    ):
        left = node_papers.get(assertion.source_id)
        right = node_papers.get(assertion.target_id)
        if (not chosen and not chosen_docs) or left or right:
            add(
                "assertion",
                assertion,
                left,
            )
    for relation in session.scalars(
        select(RelationAssertion).where(RelationAssertion.project_id == project_id)
    ):
        left = node_papers.get(relation.source_id)
        right = node_papers.get(relation.target_id)
        if (not chosen and not chosen_docs) or left or right:
            add("relation", relation, left)
    members_by_unit: dict[str, list[list[Any]]] = {}
    for unit_id, node_id, association_ids in session.execute(
        select(ReadingMember.unit_id, ReadingMember.node_id, ReadingMember.association_ids)
        .join(ReadingUnit, ReadingUnit.id == ReadingMember.unit_id)
        .where(ReadingUnit.document_version_id.in_(version_ids))
    ):
        members_by_unit.setdefault(unit_id, []).append([node_id, association_ids])
    for unit in session.scalars(
        select(ReadingUnit).where(ReadingUnit.document_version_id.in_(version_ids))
    ):
        members = sorted(members_by_unit.get(unit.id, []))
        add("unit", unit, version_papers[unit.document_version_id], members)
    for head in session.scalars(select(ReadingHead).where(ReadingHead.paper_id.in_(paper_ids))):
        selection = session.get(ReadingSelection, head.selection_id)
        if selection:
            add("selection", selection, head.paper_id, head.revision)
    for document in docs:
        from researchgraph.wiki_publish import file_status

        if document.kind == "external":
            if not scope.get("include_personal", False):
                continue
            from researchgraph.external_documents import validate_external_version

            accessible = []
            for external_version in session.scalars(
                select(QueryDocumentVersion).where(QueryDocumentVersion.document_id == document.id)
            ):
                try:
                    external = validate_external_version(
                        session, project_id, external_version.id, include_personal=True
                    )
                except KnowledgeError:
                    from researchgraph.external_document_models import ExternalDocumentVersion

                    origin = session.get(ExternalDocumentVersion, external_version.id)
                    external_root = session.get(AuthorizedRoot, origin.root_id) if origin else None
                    if not external_root or not note_allowed(
                        session, external_root, project_id, "local"
                    ):
                        continue
                    add("external", external_version, extra=[_hash_row(origin), "invalid"])
                    accessible.append(external_version.id)
                    continue
                add("external", external_version, extra=external)
                accessible.append(external_version.id)
            if accessible:
                add("document", document, extra=sorted(accessible))
            continue
        binding = session.get(QueryFileBinding, document.id)
        wiki_binding = session.get(WikiFileBinding, document.id)
        wiki_page = session.get(WikiPage, document.id)
        add(
            "document",
            document,
            extra=[
                file_state(session, document),
                _hash_row(binding) if binding else None,
                file_status(session, project_id, document.id) if wiki_binding else None,
                _hash_row(wiki_binding) if wiki_binding else None,
                _hash_row(wiki_page) if wiki_page else None,
            ],
        )
        for document_version in session.scalars(
            select(QueryDocumentVersion).where(QueryDocumentVersion.document_id == document.id)
        ):
            wiki_version = session.get(WikiVersion, document_version.id)
            add(
                "document_version",
                document_version,
                extra=_hash_row(wiki_version) if wiki_version else None,
            )
            for passage in session.scalars(
                select(QueryPassage).where(QueryPassage.version_id == document_version.id)
            ):
                section_metadata = session.get(WikiSection, passage.id)
                add(
                    "passage",
                    passage,
                    extra=_hash_row(section_metadata) if section_metadata else None,
                )
    if scope.get("include_personal", False):
        from researchgraph.p5_personal_models import AnnotationHead, AnnotationUseGrant

        for annotation in session.scalars(
            select(Annotation)
            .join(ZoteroLink, Annotation.link_id == ZoteroLink.id)
            .join(Paper, ZoteroLink.paper_id == Paper.id)
            .where(Paper.project_id == project_id)
        ):
            if chosen and annotation.document_version_id not in version_ids:
                continue
            annotation_head = session.get(
                AnnotationHead, (annotation.link_id, annotation.annotation_key)
            )
            annotation_grant = session.get(AnnotationUseGrant, annotation.id)
            if annotation_grant and not annotation_grant.allow_local:
                continue
            link = session.get(ZoteroLink, annotation.link_id)
            add(
                "annotation",
                annotation,
                extra=[
                    _hash_row(annotation_head) if annotation_head else None,
                    _hash_row(annotation_grant) if annotation_grant else None,
                    _hash_row(link) if link else None,
                ],
            )
        for root in session.scalars(
            select(AuthorizedRoot).where(AuthorizedRoot.project_id == project_id)
        ):
            if not note_allowed(session, root, project_id, "local"):
                continue
            grant = session.get(NoteUseGrant, root.id)
            # A snapshot catalog is explicit; scanning does not silently snapshot new private files.
            seen: set[str] = set()
            notes = session.scalars(
                select(NoteSnapshot)
                .where(NoteSnapshot.root_id == root.id)
                .order_by(NoteSnapshot.created_at.desc(), NoteSnapshot.id.desc())
            )
            for note in notes:
                if note.relative_path in seen:
                    continue
                seen.add(note.relative_path)
                data, state = read_authorized_file(root, note.relative_path)
                add(
                    "note",
                    note,
                    extra=[
                        root.active,
                        grant.revision if grant else 0,
                        state,
                        hashlib.sha256(data).hexdigest() if data is not None else None,
                    ],
                )
    return sorted(result, key=lambda item: (item["type"], item["id"]))


def _run(session: Session, project_id: str, run_id: str) -> LintRun:
    row = session.get(LintRun, run_id)
    if row is None or row.project_id != project_id:
        raise KnowledgeError("LINT_RUN_NOT_FOUND", "检查报告不存在或不属于当前项目")
    return row


def get_run(session: Session, project_id: str, run_id: str) -> dict[str, Any]:
    row = _run(session, project_id, run_id)
    total = len(row.targets)
    return {
        "id": row.id,
        "project_id": row.project_id,
        "status": row.status,
        "phase": row.phase,
        "timings": row.timings,
        "scope": row.scope,
        "rule_version": row.rule_version,
        "event_sequence": row.event_sequence,
        "input_hash": row.input_hash,
        "total": total,
        "processed": row.processed,
        "progress": round(row.processed / total, 6) if total else (1.0 if row.finished_at else 0.0),
        "counts": row.counts,
        "diff": row.diff,
        "previous_run_id": row.previous_run_id,
        "errors": row.errors,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "finished_at": row.finished_at,
    }


def validate_run_input(session: Session, project_id: str, run_id: str) -> bool:
    row = _run(session, project_id, run_id)
    try:
        return digest(_catalog(session, project_id, row.scope)) == row.input_hash
    except KnowledgeError:
        return False


def _repair_step(
    step_id: str,
    title: str,
    description: str,
    action: str,
    *,
    automated: bool = False,
    requires_model: bool | None = False,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "description": description,
        "action": action,
        "automated": automated,
        "requires_model": requires_model,
    }


def _repair_plan(
    code: str,
    severity: str,
    category: str,
    suggestion: str,
    *,
    lifecycle: str = "new",
    object_type: str | None = None,
) -> dict[str, Any]:
    """Return a program-owned repair outline; it never mutates data or invokes a model."""
    if lifecycle in {"resolved", "input_stale"}:
        stale = lifecycle == "input_stale"
        return {
            "status": "blocked" if stale else "informational",
            "summary": "输入已变化，请以新扫描结果决定处理方案。"
            if stale
            else "本次扫描中该问题已消失，无需按历史提示继续修复。",
            "steps": [
                _repair_step(
                    "refresh-report" if stale else "inspect-report",
                    "重新扫描当前范围" if stale else "查看报告差异",
                    "重新运行 Lint，确认当前来源、权限和版本。"
                    if stale
                    else "保留原报告，查看本次已消失的问题及检查范围。",
                    "recheck_lint" if stale else "inspect_report",
                )
            ],
            "safeguards": ["历史诊断不作为当前科学知识或文件的修改指令。"],
        }
    if object_type == "external" and code in {
        "FILE_MODIFIED",
        "FILE_MISSING",
        "FILE_UNAVAILABLE",
    }:
        external_guidance = {
            "FILE_MODIFIED": (
                "外部文件已变化，旧快照仍独立保留；需要采用新文本时显式登记新版本。",
                "在个人来源中只读预览当前文件，核对当前读取授权、内容及归属后显式登记新版本；"
                "不丢弃旧快照，也不给新文本继承旧 Wiki 证据或写入权限。",
                "register_external_version",
            ),
            "FILE_MISSING": (
                "外部原文件缺失，先检查原目录和路径；已登记快照保留。",
                "通过原文件管理器定位或恢复外部原文件，恢复后只读复查；"
                "若采用其他文件，须在当前读取授权内显式登记新版本，不将其冒充原文件或旧快照。",
                "inspect_external_source",
            ),
            "FILE_UNAVAILABLE": (
                "外部文件当前不可读，先核对读取授权及文件状态。",
                "检查当前只读目录授权、文件路径和系统权限；恢复访问后只读预览。"
                "如需采用不同内容，显式登记新版本；不可读时不推断内容变化，也不删除旧快照。",
                "inspect_authorization",
            ),
        }
        summary, description, action = external_guidance[code]
        return {
            "status": "actionable",
            "summary": summary,
            "steps": [
                _repair_step(
                    "inspect-external-source",
                    "核对外部来源",
                    "在个人来源中查看已登记版本、原文件路径和当前读取授权。",
                    "inspect_external_source",
                ),
                _repair_step(
                    "prepare-external-action",
                    "处理外部文件状态",
                    description,
                    action,
                ),
                _repair_step(
                    "rerun-external-lint",
                    "重新检查外部来源",
                    "完成显式处理后重新运行相同授权范围的 Lint，保留旧报告与快照。",
                    "recheck_lint",
                ),
            ],
            "safeguards": [
                "外部来源仅只读检查和显式登记，不走受管 Wiki 导出或发布。",
                "登记新版本不修改原文件，不覆盖旧快照，也不继承论文证据。",
                "这些处理步骤不调用模型；后续模型用途需要独立授权。",
            ],
        }
    status = "informational" if severity == "info" else "actionable"
    if code == "SOURCE_UNCHECKED":
        return {
            "status": "informational",
            "summary": "先确认原始来源是否可访问，再决定是否重新构建；此提示不表示科学结论错误。",
            "steps": [
                _repair_step(
                    "inspect-source",
                    "检查来源文件",
                    "打开文献页的“来源文件”区域，核对文件路径、访问权限、文献版本和来源身份；"
                    "需要时先点击“重新定位…”选择正确的原文件。",
                    "inspect_source",
                ),
                _repair_step(
                    "record-source-check",
                    "记录可用性检查",
                    "点击“检查文件”记录当前可用性；这里只更新检查记录，不修改原文或知识内容。",
                    "refresh_check",
                ),
                _repair_step(
                    "rerun-lint",
                    "重新检查受影响范围",
                    "来源可用后重新运行对应范围的 Lint；仍没有检查记录时继续保留此 info。",
                    "recheck_lint",
                ),
            ],
            "safeguards": [
                "不把未检查解释为文件丢失或科学错误。",
                "不修改原始文件、EvidenceSpan、知识节点或历史报告。",
                "此方案不调用模型。",
            ],
        }
    if code == "CONDITION_UNKNOWN":
        return {
            "status": "informational",
            "summary": "回看原文和表格中的实验条件；若论文没有提供，保持 unknown 并记录信息缺口。",
            "steps": [
                _repair_step(
                    "inspect-condition-evidence",
                    "回看条件证据",
                    "打开关联原文、表格和证据定位，确认是否存在明确的条件描述。",
                    "inspect_source",
                ),
                _repair_step(
                    "record-condition",
                    "准备受控新构建",
                    "只有在原文或新核验来源明确支持时，才通过现有受控构建流程"
                    "记录 known 或 conflicting；"
                    "不要直接编辑旧知识节点。没有明确证据时继续保留 unknown。",
                    "prepare_rebuild",
                    requires_model=None,
                ),
                _repair_step(
                    "rerun-condition-lint",
                    "重新检查条件状态",
                    "保存新的证据或版本后重新运行 Lint，确认信息缺口是否仍存在。",
                    "recheck_lint",
                ),
            ],
            "safeguards": [
                "不把 unknown 推断为 conflicting，也不补造实验条件。",
                "不因信息缺口改写论文 Claim、原文或历史 raw。",
                "Lint 诊断本身不调用模型；后续受控新构建是否需要模型，"
                "按该任务的冻结协议、授权和预算决定。",
            ],
        }

    # Dispatch by rule identity: NOTE_CHANGED also belongs to the file category,
    # but private notes must never be sent through managed Wiki publication.
    guidance: dict[str, tuple[str, str, str, bool | None]] = {
        "SOURCE_UNAVAILABLE": (
            "先恢复原始来源的可访问性，再确认检查结果。",
            "在文献页重新定位原来源或恢复访问权限，再显式检查可用性；"
            "检查失败不删除内部证据，也不自动替换来源身份。",
            "refresh_check",
            False,
        ),
        "SOURCE_VERSION_STALE": (
            "新旧文献版本分开处理，需要时为新版本准备独立构建。",
            "核对新版本身份及差异；需要采用新版本时通过现有受控构建流程创建新知识，"
            "保留旧版本、原始证据和旧任务，不给旧证据更换版本标签。",
            "prepare_rebuild",
            None,
        ),
        "EVIDENCE_INVALID": (
            "先定位证据不匹配的原因，再准备有正确来源的新构建。",
            "核对原文位置、字节哈希和文献归属；修复来源后通过受控新构建生成合法证据，"
            "不直接修改旧 EvidenceSpan 的定位或哈希来消除提示。",
            "prepare_rebuild",
            None,
        ),
        "NODE_EVIDENCE_MISSING": (
            "回查知识的完整根证据，缺少证据时保留缺口。",
            "逐一核对知识到根原文的来源及关联；有合法证据时准备受控新构建，"
            "没有证据时不补造引用，也不把该知识当作已验证的论文事实。",
            "prepare_rebuild",
            None,
        ),
        "RELATION_BROKEN": (
            "核对关系两端、来源归属和关系证据。",
            "定位缺失端点或失效证据；来源恢复后由受控构建重新验证受影响关系，"
            "不根据画布相邻、名称相似或模型猜测直接连边。",
            "prepare_rebuild",
            None,
        ),
        "SUPPORT_PATH_INVALID": (
            "沿完整支撑路径定位断点，再构建受影响结论单元。",
            "核对结论、成员和每条支撑边的根证据；通过受控构建重新形成合法单元，"
            "不为孤立成员补造科学关系，也不靠隐藏成员消除诊断。",
            "prepare_rebuild",
            None,
        ),
        "SELECTION_INVALID": (
            "检查默认选择引用的单元及其版本。",
            "先确认单元与成员仍合法，再通过现有受控流程重建阅读选择；"
            "展示偏好不能绕过证据校验，旧选择和任务历史保留。",
            "prepare_rebuild",
            None,
        ),
        "DEPENDENCY_INVALID": (
            "先恢复合法根来源，再决定如何更新受影响文档段落。",
            "核对逐段依赖、根证据、当前读取和模型用途授权；只有来源重新有效后，"
            "才准备独立 Wiki 更新或新的综合，不重写旧段落或伪造来源。",
            "prepare_document_update",
            None,
        ),
        "DEPENDENCY_STALE": (
            "对照依赖版本变化，为受影响段落准备显式更新。",
            "确认当前合法来源和变化范围，准备受控文档更新并查看差异；"
            "保存新版本与导出文件分别操作，保留旧段落及其依赖快照。",
            "prepare_document_update",
            None,
        ),
        "DEPENDENCY_UNVERIFIED": (
            "先确认段落归属，缺少根证据时保留未核验状态。",
            "查看段落是个人观点、外部内容还是 AI 综合；只登记能实际核验的来源。"
            "私人或外部文本不继承 Wiki 证据，无法追溯时继续标记未核验。",
            "inspect_attribution",
            False,
        ),
        "ORGANIZATION_CHANGED": (
            "组织结构变化可选择重新整理，不表示原科学段落失效。",
            "比较核心选择和单元组织差异；需要调整阅读结构时再准备独立整理任务。"
            "不因密度、排序或显示变化改写论文 Claim。",
            "prepare_reorganization",
            None,
        ),
        "SUPPORT_CONTEXT_CHANGED": (
            "先重新验证变化后的支撑路径，再检查受影响段落。",
            "回查关联结论单元和全部合法根来源；若支撑重新有效，准备受影响段落的受控更新，"
            "不直接沿用旧支撑清单或自动重发模型。",
            "prepare_document_update",
            None,
        ),
        "FILE_MODIFIED": (
            "保留外部修改，先查看文件差异及受管身份。",
            "通过只读文件检查查看差异；需要使用新文本时显式登记独立外部快照，"
            "不继承旧 Wiki 证据。需要导出当前有效的内部已保存版本时，"
            "在“授权目录与 Markdown 导出”选择不同的独立授权目录，"
            "由程序生成受管路径，保留冲突文件。",
            "inspect_file_diff",
            False,
        ),
        "FILE_MISSING": (
            "先检查目录和文件位置，需要时重新导出当前有效的已保存版本。",
            "确认文件确实缺失、内部已保存版本依赖仍有效及独立写入授权；"
            "显式导出时再次检查目标身份和 hash，同名私人文件不得覆盖。",
            "prepare_export",
            False,
        ),
        "FILE_UNAVAILABLE": (
            "检查当前目录授权和文件权限，恢复读取后再检查状态。",
            "确认读取授权、路径及操作系统权限；必要时在设置中重新选择授权目录。"
            "读取授权不等于写入授权，无法读取时不推断文件内容已变化。",
            "inspect_authorization",
            False,
        ),
        "FILE_CONFLICT": (
            "对照内外版本与发布记录，保留冲突文件。",
            "查看只读差异、登记身份和当前 hash；可将外部文本登记为独立快照，"
            "或在“授权目录与 Markdown 导出”选择不同的独立授权目录，"
            "由程序为当前有效的内部已保存版本生成受管路径。不要覆盖原冲突文件。",
            "inspect_file_conflict",
            False,
        ),
        "MANAGED_IDENTITY_INVALID": (
            "受管身份未确认前停止对该目标的发布。",
            "核对页面身份、段落 manifest 和绑定记录；不能确认时保留原文件，"
            "在“授权目录与 Markdown 导出”选择不同的独立授权目录，"
            "由程序为当前有效的内部已保存版本生成受管路径，并重新完成发布校验。",
            "inspect_managed_identity",
            False,
        ),
        "PUBLICATION_PENDING": (
            "查看原发布操作，按其持久记录显式恢复。",
            "打开原发布操作并恢复；恢复时重新核对来源、版本、授权和目标 hash。"
            "发生外部变化时停止并保留冲突，不新建模型请求或无限重试覆盖。",
            "recover_publication",
            False,
        ),
        "LINK_BROKEN": (
            "检查链接的实际目标，按文件归属选择处理入口。",
            "核对目标是否被移动或缺失，通过原文件管理器恢复应有目标后重新检查；"
            "私人文件中的链接可由用户在原编辑器处理。Lint 不直接改链接或文件。",
            "inspect_link",
            False,
        ),
        "LINK_UNVERIFIABLE": (
            "先确认是否需要检查该链接，超出授权范围时保留无法核验。",
            "仅在需要时显式授权并登记目标文件，再重新检查；"
            "不扩大扫描范围、不自动跟随未授权路径，也不把无法核验当作断链。",
            "inspect_authorization",
            False,
        ),
        "NOTE_CHANGED": (
            "对照私人笔记与登记快照，保留原文件。",
            "核对当前只读授权与原文件；需要采用当前内容时显式刷新或登记新快照。"
            "模型用途另行授权，私人笔记不走受管 Wiki 发布或自动回写。",
            "refresh_personal_snapshot",
            False,
        ),
        "NOTE_UNTRACKED": (
            "私人笔记没有论文依赖并不表示其观点错误。",
            "只核对当前已授权的链接与可追溯来源；需要参与后续任务时显式登记只读快照，"
            "保留个人归属，不给私人文本补造论文依赖或受管身份。",
            "inspect_attribution",
            False,
        ),
        "CONDITION_CONFLICTING": (
            "回查显式冲突的条件值及各自证据，不自动选值。",
            "区分原文备选值、不同实验和不同适用范围；只有明确证据支持时，"
            "才通过受控新构建记录合法状态与来源，保留旧记录和未解决分歧。",
            "prepare_rebuild",
            None,
        ),
        "CONDITION_STATE_INVALID": (
            "核对条件来源与状态含义，为合法状态准备受控新构建。",
            "按原文区分 known、unknown、not_applicable、conflicting；"
            "无法确认时保留信息缺口，不直接改旧节点或把非法状态猜成已知条件。",
            "prepare_rebuild",
            None,
        ),
    }
    summary, description, action, model_policy = guidance.get(
        code,
        (
            f"当前 {category} 诊断缺少对应方案，请先核对规则与问题对象。",
            f"只读查看诊断及原建议（{suggestion}），确认当前规则后重新检查；不执行未知修复。",
            "inspect_context",
            False,
        ),
    )
    if code == "MANAGED_IDENTITY_INVALID" or code not in guidance:
        status = "blocked"
    common = [
        _repair_step(
            "inspect-context",
            "检查关联对象",
            "查看问题对象、原文证据和当前依赖范围，确认问题是否仍然存在。",
            "inspect_context",
        ),
        _repair_step(
            "prepare-controlled-action",
            "准备处理步骤",
            description,
            action,
            requires_model=model_policy,
        ),
        _repair_step(
            "rerun-lint",
            "重新运行 Lint",
            "完成明确的处理后重新检查受影响范围；信息仍不足时保留提示及旧报告。",
            "recheck_lint",
        ),
    ]
    safeguards = [
        "Lint 只提供诊断方案，不直接修改科学知识或私人文件。",
        "修复必须通过当前来源、权限、版本和证据校验。",
        "模型建议不能绕过确定性规则或自动写入文件。",
        "受控流程是否需要模型，由该任务的冻结协议、授权和预算决定。"
        if model_policy is None
        else "这些处理步骤不调用模型。",
    ]
    return {
        "status": status,
        "summary": summary,
        "steps": common,
        "safeguards": safeguards,
    }


def issue_view(row: LintIssue) -> dict[str, Any]:
    repair_plan = _repair_plan(
        row.code,
        row.severity,
        row.category,
        row.suggestion,
        lifecycle=row.lifecycle,
        object_type=row.object_type,
    )
    return {
        k: getattr(row, k)
        for k in (
            "id",
            "fingerprint",
            "code",
            "rule_version",
            "severity",
            "category",
            "object_type",
            "object_id",
            "paper_id",
            "location",
            "message",
            "suggestion",
            "lifecycle",
        )
    } | {"repair_plan": repair_plan, "deterministic": True}


def list_runs(
    session: Session, project_id: str, *, page: int = 1, page_size: int = 10
) -> dict[str, Any]:
    _project(session, project_id)
    query = select(LintRun).where(LintRun.project_id == project_id)
    total = int(session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = session.scalars(
        query.order_by(LintRun.created_at.desc(), LintRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [get_run(session, project_id, r.id) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _note_visible(session: Session, project_id: str, note_id: str) -> bool:
    note = session.get(NoteSnapshot, note_id)
    root = session.get(AuthorizedRoot, note.root_id) if note else None
    return bool(root and note_allowed(session, root, project_id, "local"))


def _personal_visible(session: Session, project_id: str, kind: str, oid: str) -> bool:
    if kind == "note":
        return _note_visible(session, project_id, oid)
    if kind == "external":
        from researchgraph.external_documents import validate_external_version

        try:
            validate_external_version(session, project_id, oid, include_personal=True)
        except KnowledgeError:
            from researchgraph.external_document_models import ExternalDocumentVersion

            origin = session.get(ExternalDocumentVersion, oid)
            root = session.get(AuthorizedRoot, origin.root_id) if origin else None
            return bool(root and note_allowed(session, root, project_id, "local"))
    if kind == "annotation":
        from researchgraph.p5_personal_models import AnnotationUseGrant

        grant = session.get(AnnotationUseGrant, oid)
        return not grant or grant.allow_local
    if kind in {"document", "document_version", "passage"}:
        if kind == "passage":
            paragraph = session.get(QueryPassage, oid)
            paragraphs = [paragraph] if paragraph else []
        else:
            if kind == "document":
                version_ids = list(
                    session.scalars(
                        select(QueryDocumentVersion.id).where(
                            QueryDocumentVersion.document_id == oid
                        )
                    )
                )
            else:
                version_ids = [oid]
            paragraphs = list(
                session.scalars(
                    select(QueryPassage).where(QueryPassage.version_id.in_(version_ids))
                )
            )
        for paragraph in paragraphs:
            version = session.get(QueryDocumentVersion, paragraph.version_id)
            document = session.get(QueryDocument, version.document_id) if version else None
            if document and document.kind == "external":
                if not _personal_visible(session, project_id, "external", paragraph.version_id):
                    return False
                continue
            state = validate_dependencies(session, project_id, paragraph.dependencies, True)
            if any("NOT_AUTHORIZED" in issue for issue in state["issues"]):
                return False
    return True


def list_issues(
    session: Session,
    project_id: str,
    run_id: str,
    *,
    page: int = 1,
    page_size: int = 10,
    severity: str | None = None,
    category: str | None = None,
    lifecycle: str | None = None,
    code: str | None = None,
    paper_id: str | None = None,
) -> dict[str, Any]:
    _run(session, project_id, run_id)
    query = select(LintIssue).where(LintIssue.run_id == run_id)
    for name, value in {
        "severity": severity,
        "category": category,
        "lifecycle": lifecycle,
        "code": code,
        "paper_id": paper_id,
    }.items():
        if value:
            query = query.where(getattr(LintIssue, name) == value)
    rows = [
        r
        for r in session.scalars(query.order_by(LintIssue.fingerprint))
        if _personal_visible(session, project_id, r.object_type, r.object_id)
    ]
    return {
        "items": [issue_view(r) for r in rows[(page - 1) * page_size : page * page_size]],
        "total": len(rows),
        "page": page,
        "page_size": page_size,
    }


def _links(text: str) -> list[str]:
    # Check local target identity only; HTTP URLs and embedded instructions are never fetched.
    wiki = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", text)
    markdown = re.findall(r"(?<!!)\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", text)
    return sorted(set(wiki + markdown))


def _check_links(
    session: Session, root: AuthorizedRoot, relative_path: str, text: str
) -> list[tuple[str, dict[str, Any]]]:
    from pathlib import PurePosixPath

    issues = []
    for link in _links(text):
        if re.match(r"^(?:https?://|mailto:|zotero:|#)", link, re.I):
            continue
        path = link.split("#", 1)[0]
        if not path:
            continue
        local = PurePosixPath(relative_path).parent / path
        if not local.suffix:
            local = local.with_suffix(".md")
        # Never resolve outside the grant or guess basenames across different folders.
        if local.is_absolute() or ".." in local.parts or "\\" in path or ":" in path:
            issues.append(("LINK_UNVERIFIABLE", {"link": link}))
            continue
        _, state = read_authorized_file(root, local.as_posix())
        if state != "available":
            issues.append(
                ("LINK_BROKEN" if state == "missing" else "LINK_UNVERIFIABLE", {"link": link})
            )
    return issues


class LintStore:
    """KnowledgeStore delegate. The caller owns the transaction and cancellation boundary."""

    def __init__(self, store: KnowledgeStore):
        self.store, self.session = store, store.session
        self._batch_links: dict[str, list[NodeEvidence]] | None = None
        self._batch_dependencies: dict[str, list[KnowledgeDependency]] | None = None

    @staticmethod
    def _timing(run: LintRun, phase: str, started: float) -> None:
        timings = run.timings or {}
        key = "dependency_rebuild_seconds" if phase == "dependencies" else f"{phase}_seconds"
        timings = {**timings, key: round(timings.get(key, 0.0) + perf_counter() - started, 6)}
        timings["elapsed_seconds"] = round(
            sum(
                timings.get(stage, 0.0)
                for stage in (
                    "prepare_seconds",
                    "validate_seconds",
                    "check_seconds",
                    "dependency_rebuild_seconds",
                    "finalize_seconds",
                )
            ),
            6,
        )
        run.timings = timings

    def _save_advance(self, op: str, request: Any, run: LintRun, started: float) -> dict[str, Any]:
        run.timings = {
            **run.timings,
            "last_advance_seconds": round(perf_counter() - started, 6),
            "advance_calls": run.timings.get("advance_calls", 0) + 1,
        }
        return self._save(op, request, get_run(self.session, run.project_id, run.id))

    def _prefetch_checks(self, targets: list[dict[str, Any]]) -> list[Any]:
        """Keep only this advance's source rows alive for the ordinary validators.

        This batches reads, not validation decisions. Every link still runs the full
        evidence validator. Callers discard these strong references before returning.
        """
        node_ids = [target["id"] for target in targets if target["type"] == "node"]
        self._batch_links, self._batch_dependencies = {}, {}
        if not node_ids:
            return []
        nodes = list(
            self.session.scalars(select(KnowledgeNode).where(KnowledgeNode.id.in_(node_ids)))
        )
        links = list(
            self.session.scalars(select(NodeEvidence).where(NodeEvidence.node_id.in_(node_ids)))
        )
        deps = list(
            self.session.scalars(
                select(KnowledgeDependency).where(KnowledgeDependency.node_id.in_(node_ids))
            )
        )
        for link in links:
            self._batch_links.setdefault(link.node_id, []).append(link)
        for dep in deps:
            self._batch_dependencies.setdefault(dep.node_id, []).append(dep)
        retained: list[Any] = [*nodes, *links, *deps]

        def load(model: Any, ids: set[str]) -> list[Any]:
            values = sorted(ids)
            result: list[Any] = []
            for offset in range(0, len(values), 400):
                result.extend(
                    self.session.scalars(
                        select(model).where(model.id.in_(values[offset : offset + 400]))
                    )
                )
            retained.extend(result)
            return result

        load(KnowledgeNode, {dep.dependee_id for dep in deps})
        load(AttachmentRevision, {node.document_version_id for node in nodes})
        spans = load(EvidenceSpan, {link.evidence_id for link in links})
        load(Chunk, {span.paragraph_id for span in spans})
        load(Section, {span.section_id for span in spans})
        return retained

    def _cached(self, key: str, request: Any) -> dict[str, Any] | None:
        old = self.session.get(LintOperation, key)
        if old and old.request_hash != digest(request):
            raise KnowledgeError("IDEMPOTENCY_CONFLICT", "操作标识已用于不同的检查请求")
        return old.response if old else None

    def _save(self, key: str, request: Any, response: dict[str, Any]) -> dict[str, Any]:
        self.session.add(LintOperation(key=key, request_hash=digest(request), response=response))
        self.session.flush()
        return response

    def start(self, project_id: str, command: LintRequest, key: str) -> dict[str, Any]:
        scope = command.model_dump(mode="json")
        scope["paper_ids"], scope["document_ids"] = (
            sorted(set(command.paper_ids)),
            sorted(set(command.document_ids)),
        )
        request = {"project_id": project_id, "scope": scope, "rules": RULE_VERSION}
        op = f"lint-start:{project_id}:{key}"
        old = self._cached(op, request)
        if old:
            return get_run(self.session, project_id, old["id"])
        started = perf_counter()
        targets = _catalog(self.session, project_id, scope)
        previous = self.session.scalar(
            select(LintRun)
            .where(
                LintRun.project_id == project_id,
                LintRun.scope_hash == digest(scope),
                LintRun.rule_version == RULE_VERSION,
                LintRun.status == "completed",
            )
            .order_by(LintRun.created_at.desc(), LintRun.id.desc())
            .limit(1)
        )
        stamp = now()
        row = LintRun(
            id=str(uuid4()),
            project_id=project_id,
            status="queued",
            phase="scanning",
            timings={},
            scope=scope,
            scope_hash=digest(scope),
            rule_version=RULE_VERSION,
            event_sequence=_sequence(self.session, project_id),
            input_hash=digest(targets),
            targets=targets,
            processed=0,
            counts={"error": 0, "warning": 0, "info": 0},
            diff={"new": 0, "persistent": 0, "resolved": 0},
            previous_run_id=previous.id if previous else None,
            errors=[],
            created_at=stamp,
            updated_at=stamp,
            finished_at=None,
        )
        self.session.add(row)
        self.session.flush()
        self.store.audit_event(
            project_id,
            "LINT_STARTED",
            {"run_id": row.id, "scope_hash": row.scope_hash},
            actor="user",
            trigger="lint",
        )
        self._timing(row, "prepare", started)
        return self._save(op, request, get_run(self.session, project_id, row.id))

    def _emit(
        self,
        run: LintRun,
        target: dict[str, Any],
        code: str,
        location: dict[str, Any] | None = None,
    ) -> None:
        severity, category, message, suggestion = RULES[code]
        position = location or {}
        fingerprint = digest([RULE_VERSION, code, target["type"], target["id"], position])
        exists = self.session.scalar(
            select(LintIssue.id).where(
                LintIssue.run_id == run.id, LintIssue.fingerprint == fingerprint
            )
        )
        if exists:
            return
        previous = (
            self.session.scalar(
                select(LintIssue.id).where(
                    LintIssue.run_id == run.previous_run_id,
                    LintIssue.fingerprint == fingerprint,
                    LintIssue.lifecycle != "resolved",
                )
            )
            if run.previous_run_id
            else None
        )
        lifecycle = "persistent" if previous else "new"
        self.session.add(
            LintIssue(
                id=str(uuid4()),
                run_id=run.id,
                fingerprint=fingerprint,
                code=code,
                rule_version=RULE_VERSION,
                severity=severity,
                category=category,
                object_type=target["type"],
                object_id=target["id"],
                paper_id=target.get("paper_id"),
                location=position,
                message=message,
                suggestion=suggestion,
                lifecycle=lifecycle,
            )
        )
        run.counts = {**run.counts, severity: run.counts[severity] + 1}
        run.diff = {**run.diff, lifecycle: run.diff[lifecycle] + 1}
        self.session.flush()

    def _check(self, run: LintRun, target: dict[str, Any]) -> None:
        session, kind, oid = self.session, target["type"], target["id"]

        def emit(code: str, **location: Any) -> None:
            self._emit(run, target, code, location)

        if kind == "version":
            row = session.get(AttachmentRevision, oid)
            assert row is not None
            latest = session.scalar(
                select(AttachmentRevision.id)
                .where(AttachmentRevision.paper_id == row.paper_id)
                .order_by(AttachmentRevision.created_at.desc(), AttachmentRevision.id.desc())
                .limit(1)
            )
            if latest != oid:
                emit("SOURCE_VERSION_STALE", document_version_id=oid)
            sources = list(
                session.scalars(select(PaperSource).where(PaperSource.revision_id == oid))
            )
            checks = [(s.last_check or {}).get("original", {}).get("state") for s in sources]
            if not checks or all(c is None for c in checks):
                emit("SOURCE_UNCHECKED", document_version_id=oid)
            elif all(c != "available" for c in checks):
                emit("SOURCE_UNAVAILABLE", document_version_id=oid)
        elif kind == "evidence":
            span = session.get(EvidenceSpan, oid)
            assert span is not None
            try:
                validate_evidence(session, span, span.document_version_id)
            except KnowledgeError:
                emit(
                    "EVIDENCE_INVALID",
                    document_version_id=span.document_version_id,
                    chunk_id=span.paragraph_id,
                    page_index=span.page_index,
                    start=span.start_offset,
                    end=span.end_offset,
                )
        elif kind == "node":
            node = session.get(KnowledgeNode, oid)
            assert node is not None
            links = (
                self._batch_links.get(oid, [])
                if self._batch_links is not None
                else list(session.scalars(select(NodeEvidence).where(NodeEvidence.node_id == oid)))
            )
            from researchgraph.unified_store import evidence_ids

            valid = bool(links) and not evidence_ids(node.payload) - {
                link.evidence_id for link in links
            }
            version = session.get(AttachmentRevision, node.document_version_id)
            valid = valid and bool(version and version.paper_id == node.paper_id)
            for link in links:
                span = session.get(EvidenceSpan, link.evidence_id)
                try:
                    if span is None:
                        raise KnowledgeError("MISSING", "")
                    validate_evidence(session, span, node.document_version_id)
                except KnowledgeError:
                    valid = False
            if not valid:
                emit("NODE_EVIDENCE_MISSING", document_version_id=node.document_version_id)
            deps = (
                self._batch_dependencies.get(oid, [])
                if self._batch_dependencies is not None
                else list(
                    session.scalars(
                        select(KnowledgeDependency).where(KnowledgeDependency.node_id == oid)
                    )
                )
            )
            for dep in deps:
                endpoint = session.get(KnowledgeNode, dep.dependee_id)
                if (
                    not endpoint
                    or endpoint.paper_id != node.paper_id
                    or endpoint.document_version_id != node.document_version_id
                ):
                    emit(
                        "RELATION_BROKEN",
                        relation_id=f"dependency:{oid}:{dep.dependee_id}:{dep.role}",
                    )
            if node.kind == "condition":
                state = (
                    node.known_state or node.payload.get("state") or node.payload.get("known_state")
                )
                if state == "unknown":
                    emit("CONDITION_UNKNOWN", dimension=node.dimension)
                elif state == "conflicting":
                    emit("CONDITION_CONFLICTING", dimension=node.dimension)
                elif state not in {"known", "not_applicable"}:
                    emit("CONDITION_STATE_INVALID", dimension=node.dimension)
        elif kind in {"assertion", "relation"}:
            edge: SourceAssertion | RelationAssertion | None = (
                session.get(SourceAssertion, oid)
                if kind == "assertion"
                else session.get(RelationAssertion, oid)
            )
            assert edge is not None
            left, right = (
                session.get(KnowledgeNode, edge.source_id),
                session.get(KnowledgeNode, edge.target_id),
            )
            papers = {
                p.id
                for p in session.scalars(select(Paper).where(Paper.project_id == run.project_id))
            }
            valid = bool(
                left
                and right
                and left.paper_id in papers
                and right.paper_id in papers
                and edge.evidence_ids
            )
            for eid in edge.evidence_ids:
                evidence = session.get(EvidenceSpan, eid)
                try:
                    if (
                        not evidence
                        or not left
                        or not right
                        or evidence.document_version_id
                        not in {left.document_version_id, right.document_version_id}
                    ):
                        raise KnowledgeError("MISSING", "")
                    validate_evidence(session, evidence, evidence.document_version_id)
                except KnowledgeError:
                    valid = False
            if isinstance(edge, SourceAssertion) and left and right:
                from researchgraph.reading_contracts import check_relation

                try:
                    if left.document_version_id != right.document_version_id:
                        raise KnowledgeError("RELATION_SOURCE_INVALID", "关系跨越文献版本")
                    check_relation(
                        "ResearchQuestion"
                        if left.kind == "research_question"
                        else left.kind.title(),
                        "ResearchQuestion"
                        if right.kind == "research_question"
                        else right.kind.title(),
                        edge.relation,
                    )
                except (KnowledgeError, ValueError, KeyError):
                    valid = False
            if not valid:
                emit("RELATION_BROKEN", relation_id=oid)
        elif kind == "unit":
            unit = session.get(ReadingUnit, oid)
            assert unit is not None
            nodes = {
                n.id: n
                for n in session.scalars(
                    select(KnowledgeNode).where(
                        KnowledgeNode.document_version_id == unit.document_version_id
                    )
                )
            }
            members = [
                (m.node_id, m.association_ids)
                for m in session.scalars(select(ReadingMember).where(ReadingMember.unit_id == oid))
            ]
            try:
                reading = self.store.reading()
                paths = support_paths(reading, unit.document_version_id, nodes)
                validate_member_paths(
                    reading, unit.document_version_id, unit.root_claim_id, members, nodes, paths
                )
            except (KnowledgeError, KeyError):
                emit(
                    "SUPPORT_PATH_INVALID",
                    document_version_id=unit.document_version_id,
                    root_claim_id=unit.root_claim_id,
                )
        elif kind == "selection":
            selection = session.get(ReadingSelection, oid)
            assert selection is not None
            # The unit's full path is checked independently, never by its canvas visibility.
            for entry in selection.data.get("units", []):
                unit_id = entry.get("id") if isinstance(entry, dict) else None
                unit = session.get(ReadingUnit, unit_id) if isinstance(unit_id, str) else None
                if (
                    not unit
                    or unit.document_version_id != selection.document_version_id
                    or unit.root_claim_id != entry.get("root_claim_id")
                ):
                    emit("SELECTION_INVALID", unit_id=unit_id)
        elif kind == "passage":
            passage = session.get(QueryPassage, oid)
            assert passage is not None
            result = validate_dependencies(
                session,
                run.project_id,
                passage.dependencies,
                run.scope.get("include_personal", False),
            )
            state = result["content_state"]
            if "organization" in target.get("impact_categories", []):
                emit("ORGANIZATION_CHANGED", passage_id=oid)
            if "support" in target.get("impact_categories", []):
                emit("SUPPORT_CONTEXT_CHANGED", passage_id=oid)
            section_metadata = session.get(WikiSection, oid)
            if text_hash(passage.text) != passage.sha256:
                state = "invalid"
                result["issues"] = [*result["issues"], "QUERY_ANCHOR_INVALID"]
            elif state == "valid" and section_metadata and section_metadata.stale_reason:
                state = "stale"
                result["issues"] = [*result["issues"], "WIKI_SECTION_MARKED_STALE"]
            if state != "valid":
                emit(
                    {
                        "invalid": "DEPENDENCY_INVALID",
                        "stale": "DEPENDENCY_STALE",
                        "unverified": "DEPENDENCY_UNVERIFIED",
                    }[state],
                    passage_id=oid,
                    issue_codes=result["issues"],
                )
        elif kind == "document":
            document = session.get(QueryDocument, oid)
            assert document is not None
            if document.kind == "external":
                return  # Independent source versions are checked by the external target below.
            state = file_state(session, document)
            if state in {"modified", "missing", "unavailable", "conflict"}:
                emit(f"FILE_{state.upper()}", document_id=oid)
            binding = session.get(QueryFileBinding, oid)
            root = session.get(AuthorizedRoot, binding.root_id) if binding else None
            if binding and root and note_allowed(session, root, run.project_id, "local"):
                data, state = read_authorized_file(root, binding.relative_path)
                if data is not None and state == "available":
                    try:
                        for code, location in _check_links(
                            session, root, binding.relative_path, data.decode("utf-8-sig")
                        ):
                            self._emit(run, target, code, location)
                    except UnicodeError:
                        emit("MANAGED_IDENTITY_INVALID", document_id=oid)
            self._managed_hook(run, target, document.id)
        elif kind == "annotation":
            from researchgraph.p5_personal import annotation_source

            try:
                annotation = annotation_source(session, run.project_id, oid)
            except KnowledgeError as exc:
                emit("DEPENDENCY_INVALID", issue_codes=[exc.code], field="comment")
            else:
                if annotation["anchor_status"] == "unresolved":
                    emit("DEPENDENCY_UNVERIFIED", field="highlight", anchor_status="unresolved")
        elif kind == "external":
            from researchgraph.external_documents import validate_external_version

            try:
                external = validate_external_version(
                    session, run.project_id, oid, include_personal=True
                )
            except KnowledgeError as exc:
                if "NOT_AUTHORIZED" not in exc.code:
                    emit("DEPENDENCY_INVALID", issue_codes=[exc.code])
                return
            emit("DEPENDENCY_UNVERIFIED", source_verified=False)
            if external["file_state"] in {"modified", "missing", "unavailable"}:
                emit(f"FILE_{external['file_state'].upper()}", document_id=external["document_id"])
            root = session.get(AuthorizedRoot, external["root_id"])
            if root:
                data, file_read_state = read_authorized_file(root, external["relative_path"])
                if data is not None and file_read_state == "available":
                    try:
                        for code, location in _check_links(
                            session, root, external["relative_path"], data.decode("utf-8-sig")
                        ):
                            self._emit(run, target, code, location)
                    except UnicodeError:
                        emit("FILE_UNAVAILABLE", document_id=external["document_id"])
        elif kind == "note":
            note = session.get(NoteSnapshot, oid)
            assert note is not None
            root = session.get(AuthorizedRoot, note.root_id)
            if not root or not note_allowed(session, root, run.project_id, "local"):
                return
            data, state = read_authorized_file(root, note.relative_path)
            location = {"root_id": note.root_id, "relative_path": note.relative_path}
            if (
                data is None
                or state != "available"
                or hashlib.sha256(data).hexdigest() != note.sha256
            ):
                emit("NOTE_CHANGED", **location)
            # It is a personal source, not an automatically verified scientific passage.
            emit("NOTE_UNTRACKED", **location)
            if data is not None and state == "available":
                try:
                    for code, extra in _check_links(
                        session, root, note.relative_path, data.decode("utf-8-sig")
                    ):
                        self._emit(run, target, code, {**location, **extra})
                except UnicodeError:
                    emit("NOTE_CHANGED", **location)

    def _managed_hook(self, run: LintRun, target: dict[str, Any], document_id: str) -> None:
        # Publisher owns its file format. Integrations register no arbitrary executable hooks.
        from researchgraph.wiki_publish import file_diagnostics

        codes = {
            "WIKI_PUBLICATION_PENDING": "PUBLICATION_PENDING",
            "WIKI_FILE_MODIFIED": "FILE_MODIFIED",
            "WIKI_FILE_MISSING": "FILE_MISSING",
            "WIKI_FILE_UNAVAILABLE": "FILE_UNAVAILABLE",
            "WIKI_SECTION_MAPPING_INVALID": "MANAGED_IDENTITY_INVALID",
            "WIKI_LINK_BROKEN": "LINK_BROKEN",
            "WIKI_REFERENCE_LINK_BROKEN": "LINK_BROKEN",
        }
        for issue in file_diagnostics(self.session, run.project_id, document_id):
            code = codes.get(issue.get("code", ""), "MANAGED_IDENTITY_INVALID")
            self._emit(
                run,
                target,
                code if code in RULES else "MANAGED_IDENTITY_INVALID",
                {"source_id": issue.get("source_id"), **issue.get("details", {})},
            )

    def advance(self, project_id: str, run_id: str, max_items: int, key: str) -> dict[str, Any]:
        advance_started = perf_counter()
        run = _run(self.session, project_id, run_id)
        request = {"run_id": run_id, "max_items": max_items}
        op = f"lint-step:{project_id}:{key}"
        cached = self._cached(op, request)
        if cached:
            return get_run(self.session, project_id, run_id)
        if run.status not in {"queued", "running"}:
            return self._save(op, request, get_run(self.session, project_id, run_id))
        if not 1 <= max_items <= 100:
            raise KnowledgeError("LINT_BATCH_INVALID", "单次检查数必须为 1 到 100")
        started = perf_counter()
        valid = validate_run_input(self.session, project_id, run_id)
        self._timing(run, "validate", started)
        if not valid:
            run.status, run.finished_at, run.updated_at = "input_stale", now(), now()
            run.phase = "finished"
            for issue in self.session.scalars(select(LintIssue).where(LintIssue.run_id == run_id)):
                issue.lifecycle = "input_stale"
            return self._save_advance(op, request, run, advance_started)
        run.status = "running"
        if run.phase == "rebuilding_dependencies":
            started = perf_counter()
            rebuild_dependencies(
                self.store,
                project_id,
                include_personal=run.scope.get("include_personal", False),
            )
            self._timing(run, "dependencies", started)
            self._finish(run)
            return self._save_advance(op, request, run, advance_started)
        started = perf_counter()
        batch = run.targets[run.processed : run.processed + max_items]
        retained = self._prefetch_checks(batch)
        try:
            for target in batch:
                try:
                    self._check(run, target)
                except Exception:
                    # Preserve completed scope and stable codes; never echo private exceptions.
                    run.errors = [
                        *run.errors,
                        {
                            "object_type": target["type"],
                            "object_id": target["id"],
                            "code": "LINT_RULE_FAILED",
                        },
                    ]
                run.processed += 1
        finally:
            self._batch_links = self._batch_dependencies = None
            retained.clear()
        self._timing(run, "check", started)
        run.updated_at = now()
        if run.processed == len(run.targets):
            if (
                not run.errors
                and not run.scope.get("incremental")
                and not run.scope.get("paper_ids")
                and not run.scope.get("document_ids")
                and not self.session.get(DependencyCursor, project_id)
            ):
                # Commit the final object count before the potentially expensive rebuild.
                # A new advance revalidates sources and can resume this phase after restart.
                run.phase = "rebuilding_dependencies"
            else:
                self._finish(run)
        return self._save_advance(op, request, run, advance_started)

    def _finish(self, run: LintRun) -> None:
        started = perf_counter()
        run.status = "partial" if run.errors else "completed"
        run.phase = "finished"
        run.finished_at = run.updated_at = now()
        if run.status == "completed":
            self._resolved(run)
        self.store.audit_event(
            run.project_id,
            "LINT_FINISHED",
            {"run_id": run.id, "status": run.status, "processed": run.processed},
            actor="system",
            trigger="lint",
        )
        self._timing(run, "finalize", started)

    def _resolved(self, run: LintRun) -> None:
        if not run.previous_run_id:
            return
        current = set(
            self.session.scalars(select(LintIssue.fingerprint).where(LintIssue.run_id == run.id))
        )
        old = self.session.scalars(
            select(LintIssue).where(
                LintIssue.run_id == run.previous_run_id, LintIssue.lifecycle != "resolved"
            )
        )
        count = 0
        for issue in old:
            if issue.fingerprint in current or (
                issue.object_type == "note"
                and not _note_visible(self.session, run.project_id, issue.object_id)
            ):
                continue
            self.session.add(
                LintIssue(
                    id=str(uuid4()),
                    run_id=run.id,
                    fingerprint=issue.fingerprint,
                    code=issue.code,
                    rule_version=issue.rule_version,
                    severity=issue.severity,
                    category=issue.category,
                    object_type=issue.object_type,
                    object_id=issue.object_id,
                    paper_id=issue.paper_id,
                    location=issue.location,
                    message=issue.message,
                    suggestion=issue.suggestion,
                    lifecycle="resolved",
                )
            )
            count += 1
        run.diff = {**run.diff, "resolved": count}

    def cancel(self, project_id: str, run_id: str, key: str) -> dict[str, Any]:
        run = _run(self.session, project_id, run_id)
        op, request = f"lint-cancel:{project_id}:{key}", {"run_id": run_id}
        if self._cached(op, request):
            return get_run(self.session, project_id, run_id)
        if run.status in {"queued", "running"}:
            run.status, run.finished_at, run.updated_at = "cancelled", now(), now()
            run.phase = "finished"
            self.store.audit_event(
                project_id,
                "LINT_CANCELLED",
                {"run_id": run_id, "processed": run.processed},
                actor="user",
                trigger="lint",
            )
        return self._save(op, request, get_run(self.session, project_id, run_id))

    def rebuild_dependencies(self, project_id: str, key: str) -> dict[str, Any]:
        """Full deterministic reconciliation also recovers missed events and old-version writes."""
        request, op = {"project_id": project_id}, f"lint-index:{project_id}:{key}"
        old = self._cached(op, request)
        if old:
            return old
        return self._save(op, request, rebuild_dependencies(self.store, project_id))

    def reconcile(self, project_id: str, max_items: int = 25) -> dict[str, Any] | None:
        """Worker-only deterministic incremental diagnostics for an explicitly enabled project.

        The old and new edge union retains impacts after an edge/source is removed.
        A full authoritative hash is retained even though only the impact subset is checked.
        Incremental reports never resolve issues from an unscanned earlier full report.
        """
        cursor = self.session.get(DependencyCursor, project_id)
        if cursor is None:
            return None
        active = self.session.scalar(
            select(LintRun)
            .where(
                LintRun.project_id == project_id,
                LintRun.status.in_({"queued", "running"}),
            )
            .order_by(LintRun.created_at, LintRun.id)
        )
        if active and active.scope.get("incremental"):
            return self.advance(
                project_id,
                active.id,
                max_items,
                f"automatic-{active.id}-{active.phase}-{active.processed}",
            )
        # Never compete with an explicit scan; its frozen input guard remains authoritative.
        if active:
            return None
        started = perf_counter()
        previous_edges = list(
            self.session.execute(
                select(
                    DependencyIndex.source_type,
                    DependencyIndex.source_id,
                    DependencyIndex.dependent_type,
                    DependencyIndex.dependent_id,
                ).where(DependencyIndex.project_id == project_id)
            )
        )
        previous_pairs = [
            (e.source_type, e.source_id, e.dependent_type, e.dependent_id) for e in previous_edges
        ]
        rebuilt = rebuild_dependencies(self.store, project_id, skip_unchanged=True)
        if not rebuilt["changes"]:
            return None
        current_edges = list(
            self.session.execute(
                select(
                    DependencyIndex.source_type,
                    DependencyIndex.source_id,
                    DependencyIndex.dependent_type,
                    DependencyIndex.dependent_id,
                ).where(DependencyIndex.project_id == project_id)
            )
        )
        pairs = previous_pairs + [
            (e.source_type, e.source_id, e.dependent_type, e.dependent_id) for e in current_edges
        ]
        adjacency: dict[tuple[str, str], set[tuple[str, str]]] = {}
        for source_type, source_id, dependent_type, dependent_id in pairs:
            adjacency.setdefault((source_type, source_id), set()).add(
                (dependent_type, dependent_id)
            )
        affected: dict[tuple[str, str], set[str]] = {}
        queue: deque[tuple[tuple[str, str], str]] = deque()
        for change in rebuilt["changes"]:
            source = (change["object_type"], change["object_id"])
            category = (
                "support"
                if change["object_type"] in {"assertion", "relation", "unit"}
                else change["category"]
            )
            queue.append((source, category))
        while queue:
            source, category = queue.popleft()
            if category in affected.setdefault(source, set()):
                continue
            affected[source].add(category)
            queue.extend((dependent, category) for dependent in adjacency.get(source, set()))
        include_personal = cursor.objects.get("settings:include_personal") == "true"
        scope: dict[str, Any] = {
            "paper_ids": [],
            "document_ids": [],
            "include_personal": include_personal,
            "incremental": True,
            "changed_objects": rebuilt["changes"],
        }
        full = _catalog(self.session, project_id, scope)
        targets = [
            {**target, "impact_categories": sorted(affected[(target["type"], target["id"])])}
            for target in full
            if (target["type"], target["id"]) in affected
        ]
        if not targets:
            return None
        stamp = now()
        row = LintRun(
            id=str(uuid4()),
            project_id=project_id,
            status="queued",
            phase="scanning",
            timings={},
            scope=scope,
            scope_hash=digest(scope),
            rule_version=RULE_VERSION,
            event_sequence=rebuilt["event_sequence"],
            input_hash=digest(full),
            targets=targets,
            processed=0,
            counts={"error": 0, "warning": 0, "info": 0},
            diff={"new": 0, "persistent": 0, "resolved": 0},
            previous_run_id=None,
            errors=[],
            created_at=stamp,
            updated_at=stamp,
            finished_at=None,
        )
        self.session.add(row)
        self.session.flush()
        self._timing(row, "prepare", started)
        return self.advance(project_id, row.id, max_items, f"automatic-{row.id}-scanning-0")


def rebuild_dependencies(
    store: KnowledgeStore,
    project_id: str,
    *,
    include_personal: bool | None = None,
    skip_unchanged: bool = False,
) -> dict[str, Any]:
    from researchgraph.lint_dependencies import rebuild_dependencies as rebuild

    return rebuild(
        store, project_id, include_personal=include_personal, skip_unchanged=skip_unchanged
    )


def dependencies(
    session: Session,
    project_id: str,
    *,
    object_type: str | None = None,
    object_id: str | None = None,
    direction: str = "dependents",
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    from researchgraph.lint_dependencies import dependencies as lookup

    return lookup(
        session,
        project_id,
        object_type=object_type,
        object_id=object_id,
        direction=direction,
        page=page,
        page_size=page_size,
    )
