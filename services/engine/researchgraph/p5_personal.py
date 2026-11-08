"""Explicit P5 personal-source selection; never scan, write or authorize user files."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.knowledge_models import Annotation, EvidenceSpan, ZoteroLink
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, validate_evidence
from researchgraph.models import AttachmentRevision, Paper, Project
from researchgraph.p5_contracts import PersonalSources
from researchgraph.p5_personal_models import AnnotationHead, AnnotationUseGrant
from researchgraph.query_models import QueryOperation


def annotation_source(
    session: Session, project_id: str, annotation_id: str, *, purpose: str = "local"
) -> dict[str, Any]:
    row = session.get(Annotation, annotation_id)
    link = session.get(ZoteroLink, row.link_id) if row else None
    paper = session.get(Paper, link.paper_id) if link else None
    version = session.get(AttachmentRevision, row.document_version_id) if row else None
    if not row or not link or not paper or paper.project_id != project_id or not version:
        raise KnowledgeError("QUERY_ANNOTATION_NOT_AUTHORIZED", "批注不属于当前授权项目")
    if version.paper_id != paper.id or link.document_version_id != version.id:
        raise KnowledgeError("QUERY_ANNOTATION_CHANGED", "批注附件版本已变化")
    head = session.get(AnnotationHead, (link.id, row.annotation_key))
    if not head or head.removed or head.annotation_id != row.id:
        raise KnowledgeError("QUERY_ANNOTATION_CHANGED", "批注已在显式同步时更新或移除")
    grant = session.get(AnnotationUseGrant, row.id)
    if (
        purpose not in {"local", "model", "grant"}
        or (purpose == "model" and not (grant and grant.allow_model))
        or (purpose == "local" and grant and not grant.allow_local)
    ):
        raise KnowledgeError("QUERY_ANNOTATION_NOT_AUTHORIZED", "批注评论未获本次用途授权")
    if not row.comment.strip():
        raise KnowledgeError("QUERY_ANNOTATION_EMPTY", "批注没有可选的用户评论")
    fingerprint = digest(
        {
            "comment": row.comment,
            "source_hash": row.source_hash,
            "link_id": link.id,
            "annotation_key": row.annotation_key,
            "document_version_id": version.id,
        }
    )
    source: dict[str, Any] = {
        "id": row.id,
        "type": "annotation",
        "source_kind": "annotation",
        "text": row.comment,
        "sha256": fingerprint,
        "field": "comment",
        "attribution": "user_view",
        "link_id": link.id,
        "annotation_key": row.annotation_key,
        "document_version_id": version.id,
        "paper_id": paper.id,
        "source_sha256": row.source_hash,
        "authorization_revision": grant.revision if grant else 0,
        "allow_model": bool(grant and grant.allow_model),
        "allow_local": grant.allow_local if grant else True,
        "head_revision": head.revision,
        "anchor_status": "unresolved",
        "currentness": "last_explicit_import",
        "library_id": link.library_id,
        "attachment_key": link.attachment_key,
    }
    evidence = session.get(EvidenceSpan, row.evidence_id) if row.evidence_id else None
    if evidence and row.anchor_status == "block_matched":
        try:
            validate_evidence(session, evidence, version.id)
        except KnowledgeError:
            pass
        else:
            position = row.source_position
            if (
                evidence.document_version_id == version.id
                and row.text
                and evidence.quote.count(row.text) == 1
                and type(position.get("pageIndex")) is int
                and evidence.page_index == position["pageIndex"]
            ):
                source.update(
                    anchor_status="block_matched",
                    evidence_id=evidence.id,
                    page_index=evidence.page_index,
                )
    return source


def set_annotation_grant(
    store: KnowledgeStore,
    project_id: str,
    annotation_id: str,
    allow_model: bool,
    expected_revision: int,
    key: str,
    *,
    allow_local: bool | None = None,
) -> dict[str, Any]:
    source = annotation_source(store.session, project_id, annotation_id, purpose="grant")
    request = {
        "project_id": project_id,
        "annotation_id": annotation_id,
        "allow_model": allow_model,
        "expected_revision": expected_revision,
        "allow_local": allow_local,
    }
    operation_key = f"p5-annotation-grant:{project_id}:{key}"
    operation = store.session.get(QueryOperation, operation_key)
    if operation:
        if operation.request_hash != digest(request):
            raise KnowledgeError("IDEMPOTENCY_CONFLICT", "同一操作标识对应不同批注授权")
        return operation.response
    if source["authorization_revision"] != expected_revision:
        raise KnowledgeError("P5_GRANT_CONFLICT", "批注授权版本已改变，请刷新")
    grant = store.session.get(AnnotationUseGrant, annotation_id)
    if not grant:
        grant = AnnotationUseGrant(
            annotation_id=annotation_id, allow_local=True, allow_model=False, revision=0
        )
        store.session.add(grant)
    grant.allow_model, grant.revision = allow_model, expected_revision + 1
    if allow_local is not None:
        grant.allow_local = allow_local
    result = {
        "annotation_id": annotation_id,
        "allow_model": allow_model,
        "revision": grant.revision,
        "allow_local": grant.allow_local,
    }
    store.session.add(
        QueryOperation(key=operation_key, request_hash=digest(request), response=result)
    )
    store.audit_event(project_id, "ANNOTATION_USE_CHANGED", result)
    return result


def selected_sources(
    session: Session, project_id: str, selection: dict[str, Any], *, purpose: str = "model"
) -> list[dict[str, Any]]:
    from researchgraph.query_documents import read_notes

    selected = PersonalSources.model_validate(selection)
    notes = {
        n["id"]: n
        for n in read_notes(session, project_id, True, purpose, selected_ids=set(selected.note_ids))
    }
    result = []
    for note_id in selected.note_ids:
        if note_id not in notes:
            raise KnowledgeError("QUERY_NOTE_NOT_AUTHORIZED", "所选笔记快照或当前用途授权不可用")
        result.append({"type": "note", "source_kind": "note", **notes[note_id]})
    result.extend(
        annotation_source(session, project_id, aid, purpose=purpose)
        for aid in selected.annotation_ids
    )
    if selected.external_version_ids:
        from researchgraph.external_documents import validate_external_version

        for version_id in selected.external_version_ids:
            external = validate_external_version(
                session, project_id, version_id, include_personal=True, purpose=purpose
            )
            if not external.get("snapshot_valid"):
                raise KnowledgeError("QUERY_EXTERNAL_INVALID", "外部文档快照不可用")
            result.append(
                {
                    **external,
                    "type": "external",
                    "source_kind": "external",
                    "id": version_id,
                    "source_attribution": external["attribution"],
                }
            )
    return sorted(result, key=lambda s: (s["type"], s["id"]))


def assert_selected_roots(roots: list[dict[str, Any]], selection: dict[str, Any]) -> None:
    selected = PersonalSources.model_validate(selection)
    allowed = {
        "note": set(selected.note_ids),
        "annotation": set(selected.annotation_ids),
        "external": set(selected.external_version_ids),
    }
    for root in roots:
        kind = root.get("source_kind", root.get("type"))
        if kind in allowed and root.get("id") not in allowed[kind]:
            raise KnowledgeError(
                "P5_PERSONAL_SOURCE_NOT_SELECTED", "间接依赖含未明确选中的个人来源"
            )


def personal_catalog(
    session: Session, project_id: str, *, page: int = 1, page_size: int = 50
) -> dict[str, Any]:
    from researchgraph.query_documents import read_notes
    from researchgraph.query_models import NoteUseGrant

    if not session.get(Project, project_id):
        raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
    items: list[dict[str, Any]] = []
    for note in read_notes(session, project_id, True, "local"):
        grant = session.get(NoteUseGrant, note["root_id"])
        items.append(
            {
                **note,
                "type": "note",
                "label": note["relative_path"],
                "allow_model": bool(grant and grant.allow_model),
            }
        )
    rows = session.scalars(
        select(Annotation)
        .join(ZoteroLink, Annotation.link_id == ZoteroLink.id)
        .join(Paper, ZoteroLink.paper_id == Paper.id)
        .where(Paper.project_id == project_id)
    )
    for row in rows:
        local_grant = session.get(AnnotationUseGrant, row.id)
        if local_grant and not local_grant.allow_local:
            items.append(
                {
                    "type": "annotation",
                    "id": row.id,
                    "label": "已撤销本地读取的批注",
                    "allow_local": False,
                    "allow_model": local_grant.allow_model,
                    "authorization_revision": local_grant.revision,
                    "redacted": True,
                }
            )
            continue
        try:
            source = annotation_source(session, project_id, row.id)
        except KnowledgeError:
            continue
        items.append({**source, "label": f"批注评论 {row.annotation_key}", "highlight": row.text})
    from researchgraph.external_documents import personal_external_sources

    items.extend(personal_external_sources(session, project_id))
    items.sort(key=lambda r: (r["type"], r.get("label", ""), r["id"]))
    return {
        "items": items[(page - 1) * page_size : page * page_size],
        "total": len(items),
        "page": page,
        "page_size": page_size,
    }
