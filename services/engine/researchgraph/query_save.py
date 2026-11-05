"""Explicit Query saves through Store, without paper mutation or Markdown writes."""

from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.knowledge_models import KnowledgeNode
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, text_hash
from researchgraph.models import Paper, now
from researchgraph.query_contracts import (
    DocumentSaveRequest,
    QueryAnswer,
    QuerySaveCommand,
    SavedReadingAnnotation,
    SavedReadingRemoval,
)
from researchgraph.query_documents import file_state, validate_dependencies
from researchgraph.query_models import (
    QueryAnswerVersion,
    QueryDocument,
    QueryDocumentVersion,
    QueryOperation,
    QueryPassage,
    QueryRun,
)
from researchgraph.query_numeric_layout import freeze_layout, validate_numeric_layout
from researchgraph.query_saved_lifecycle import (
    answer_lineage_hash as _lineage_hash,
)
from researchgraph.query_saved_lifecycle import (
    passage_lineage,
)
from researchgraph.query_saved_lifecycle import (
    reference_dependency as _dependency,
)
from researchgraph.query_saved_models import QuerySavedKnowledge, QuerySavedPreference
from researchgraph.query_source_scope import paper_ids_from_sources


def _root_dependencies(
    session: Session, dependencies: list[dict[str, Any]], trail: set[str] | None = None
) -> list[dict[str, Any]]:
    """Keep semantic node revisions, but flatten immutable document wrappers to their roots."""
    result = []
    visiting = set(trail or ())
    for dependency in dependencies:
        if dependency["type"] != "passage":
            if dependency["type"] == "node":
                node = session.get(KnowledgeNode, dependency["id"])
                if node is None:
                    raise KnowledgeError("QUERY_SAVE_DEPENDENCY_INVALID", "知识根来源不存在")
                dependency = {**dependency, "payload_sha256": digest(node.payload)}
            result.append(dependency)
            continue
        pid = dependency["id"]
        passage = session.get(QueryPassage, pid)
        if not passage or pid in visiting:
            raise KnowledgeError("QUERY_SAVE_DEPENDENCY_INVALID", "段落来源缺失或出现循环")
        result.extend(_root_dependencies(session, passage.dependencies, visiting | {pid}))
    return list({digest(dep): dep for dep in result}.values())


def _checked_answer(
    session: Session, project_id: str, body: QuerySaveCommand, *, revalidate: bool = True
) -> tuple[QueryRun, QueryAnswerVersion, QueryAnswer]:
    # Imported late so the independent answer and save modules share one validation path.
    from researchgraph.query_answers import validate_answer

    run = session.get(QueryRun, body.source_query_id)
    answer = session.get(QueryAnswerVersion, body.answer_version_id)
    if (
        not run
        or run.project_id != project_id
        or not answer
        or answer.project_id != project_id
        or answer.query_run_id != run.id
    ):
        raise KnowledgeError("QUERY_SAVE_SCOPE_INVALID", "回答不属于当前项目或查询")
    if body.expected_input_hash != run.input_hash or answer.input_hash != run.input_hash:
        raise KnowledgeError("QUERY_SAVE_INPUT_CHANGED", "回答输入版本不匹配，请重新准备查询")
    if revalidate:
        answer = validate_answer(session, project_id, run.id, answer.id)
    try:
        data = QueryAnswer.model_validate(answer.data)
    except ValidationError as exc:
        raise KnowledgeError("QUERY_SAVE_ANSWER_INVALID", "回答未通过保存契约校验") from exc
    if (
        answer.state != "validated"
        or data.status != "validated"
        or data.knowledge_status == "insufficient"
        or data.answer_version_id != answer.id
        or data.query_run_id != run.id
        or data.input_hash != answer.input_hash
        or data.revision != answer.revision
    ):
        raise KnowledgeError("QUERY_SAVE_ANSWER_INVALID", "仅可保存来源完整且已验证的回答段落")
    return run, answer, data


def _check_selected_numeric_layout(
    session: Session, run: QueryRun, data: QueryAnswer, selected: set[str]
) -> None:
    # New writes use today's source gate, including v1 answers whose immutable
    # read/raw/hash protocol predates layout cautions. Never rewrite that history.
    passages = [p for p in data.passages if p.local_ref in selected]
    if len(passages) != len(selected):
        raise KnowledgeError("QUERY_SAVE_PASSAGE_INVALID", "所选段落不属于本次回答")
    validate_numeric_layout(passages, freeze_layout(session, run.snapshot["context"]["references"]))


def _view(
    session: Session,
    saved: QuerySavedKnowledge,
    *,
    include_personal: bool,
    purpose: str,
) -> dict[str, Any] | None:
    document = session.get(QueryDocument, saved.document_id)
    version = session.get(QueryDocumentVersion, saved.document_version_id)
    if (
        document is None
        or version is None
        or document.project_id != saved.project_id
        or version.document_id != document.id
        or version.state != "saved"
    ):
        raise KnowledgeError("QUERY_SAVED_INVALID", "保存内容的文档版本不可用")
    passages = []
    states = set()
    allowed_papers = set(
        session.scalars(select(Paper.id).where(Paper.project_id == saved.project_id))
    )
    preference = session.get(QuerySavedPreference, saved.id)
    frozen = saved.manifest.get("passages", [])
    if len(saved.passage_ids) != len(frozen):
        raise KnowledgeError("QUERY_SAVED_INVALID", "保存内容的清单不完整")
    for pid, original in zip(saved.passage_ids, frozen, strict=True):
        passage = session.get(QueryPassage, pid)
        if passage is None or passage.version_id != version.id:
            raise KnowledgeError("QUERY_SAVED_INVALID", "保存内容的段落版本不可用")
        if (
            passage.local_ref != original["document_local_ref"]
            or passage.sha256 != original["text_hash"]
            or passage.attribution != original["attribution"]
            or passage.dependencies != original["dependencies"]
            or passage.caveats != original["caveats"]
        ):
            raise KnowledgeError("QUERY_SAVED_INVALID", "保存内容与冻结清单不匹配")
        lineage = passage_lineage(session, saved, original)
        checked = validate_dependencies(
            session,
            saved.project_id,
            [*passage.dependencies, *lineage["lineage_dependencies"]],
            include_personal,
            purpose,
        )
        if "QUERY_NOTE_NOT_AUTHORIZED" in checked["issues"] or (
            passage.attribution == "user_view" and not include_personal
        ):
            return None  # Never expose a private interpretation via a saved wrapper.
        if text_hash(passage.text) != passage.sha256:
            checked = {
                **checked,
                "content_state": "invalid",
                "issues": [*checked["issues"], "QUERY_ANCHOR_INVALID"],
            }
        if lineage.get("lineage_issue"):
            checked = {
                **checked,
                "content_state": "invalid",
                "issues": [*checked["issues"], lineage["lineage_issue"]],
            }
        states.add(checked["content_state"])
        passages.append(
            {
                "id": passage.id,
                "local_ref": passage.local_ref,
                "text": passage.text if checked["content_state"] == "valid" else "",
                "attribution": passage.attribution,
                "dependencies": passage.dependencies,
                "caveats": passage.caveats if checked["content_state"] == "valid" else [],
                "source_refs": original["source_refs"],
                "lineage_dependencies": lineage["lineage_dependencies"],
                **checked,
                "paper_ids": paper_ids_from_sources(checked["roots"], allowed_papers),
            }
        )
    state = next((s for s in ("invalid", "stale", "unverified", "valid") if s in states), "invalid")
    return {
        "saved_id": saved.id,
        "kind": saved.kind,
        "title": saved.title,
        "source_query_id": saved.source_query_id,
        "answer_version_id": saved.answer_version_id,
        "document_id": document.id,
        "version_id": version.id,
        "revision": version.revision,
        "created_at": saved.created_at,
        "passages": passages,
        "paper_ids": sorted({pid for passage in passages for pid in passage["paper_ids"]}),
        "passage_ids": saved.passage_ids,
        "content_state": state,
        "file_state": file_state(session, document),
        "graph_revision": saved.graph_revision,
        "annotation": preference.annotation if preference else "",
        "metadata_revision": preference.revision if preference else 0,
        "removed_at": preference.removed_at if preference else None,
    }


def get_saved(
    session: Session,
    project_id: str,
    saved_id: str,
    include_personal: bool = False,
    purpose: str = "local",
) -> dict[str, Any]:
    saved = session.get(QuerySavedKnowledge, saved_id)
    if saved is None or saved.project_id != project_id:
        raise KnowledgeError("QUERY_SAVED_NOT_FOUND", "项目中没有该保存内容")
    preference = session.get(QuerySavedPreference, saved.id)
    if preference and preference.removed_at:
        raise KnowledgeError("QUERY_SAVED_REMOVED", "该阅读知识已移除，原问答与证据历史仍保留")
    view = _view(session, saved, include_personal=include_personal, purpose=purpose)
    if view is None:
        raise KnowledgeError("QUERY_SAVED_NOT_ACCESSIBLE", "个人来源未获本次用途授权")
    return view


def list_saved(
    session: Session, project_id: str, include_personal: bool = False, purpose: str = "local"
) -> list[dict[str, Any]]:
    result = []
    for saved in session.scalars(
        select(QuerySavedKnowledge)
        .outerjoin(QuerySavedPreference, QuerySavedPreference.saved_id == QuerySavedKnowledge.id)
        .where(
            QuerySavedKnowledge.project_id == project_id,
            QuerySavedPreference.removed_at.is_(None),
        )
        .order_by(QuerySavedKnowledge.created_at.desc(), QuerySavedKnowledge.id)
    ):
        view = _view(session, saved, include_personal=include_personal, purpose=purpose)
        if view is not None:
            result.append(view)
    return result


def _metadata_operation(
    session: Session, project_id: str, saved_id: str, action: str, body: Any, key: str
) -> tuple[str, str, QueryOperation | None]:
    if not key.strip() or len(key) > 120:
        raise KnowledgeError("IDEMPOTENCY_KEY_INVALID", "操作请求标识为空或过长")
    operation = f"query-saved-{action}:{project_id}:{key}"
    fingerprint = digest({"saved_id": saved_id, **body.model_dump(mode="json")})
    previous = session.get(QueryOperation, operation)
    if previous and previous.request_hash != fingerprint:
        raise KnowledgeError("IDEMPOTENCY_CONFLICT", "相同操作键对应不同阅读知识操作")
    return operation, fingerprint, previous


def _preference(session: Session, saved_id: str, expected_revision: int) -> QuerySavedPreference:
    preference = session.get(QuerySavedPreference, saved_id)
    if (preference.revision if preference else 0) != expected_revision:
        raise KnowledgeError(
            "QUERY_SAVED_METADATA_CONFLICT", "批注或移除状态已变化，请刷新后再操作"
        )
    if preference is None:
        preference = QuerySavedPreference(
            saved_id=saved_id, annotation="", revision=0, removed_at=None, updated_at=now()
        )
        session.add(preference)
    return preference


def annotate_saved(
    store: KnowledgeStore,
    project_id: str,
    saved_id: str,
    command: SavedReadingAnnotation | dict[str, Any],
    key: str,
    include_personal: bool = False,
) -> dict[str, Any]:
    """Personal annotation does not rewrite model text, dependencies or science revisions."""
    body = SavedReadingAnnotation.model_validate(command)
    session = store.session
    operation, fingerprint, previous = _metadata_operation(
        session, project_id, saved_id, "annotate", body, key
    )
    get_saved(session, project_id, saved_id, include_personal)
    if previous:
        return get_saved(session, project_id, saved_id, include_personal)
    preference = _preference(session, saved_id, body.expected_revision)
    before = preference.annotation
    preference.annotation = body.annotation
    preference.revision += 1
    preference.updated_at = now()
    store.audit_event(
        project_id,
        "query.saved_annotation_changed",
        {
            "saved_id": saved_id,
            "metadata_revision": preference.revision,
            "before": before,
            "annotation": body.annotation,
            "attribution": "user_view",
        },
        actor="user",
        trigger="query_library",
    )
    session.add(
        QueryOperation(key=operation, request_hash=fingerprint, response={"saved_id": saved_id})
    )
    session.flush()
    return get_saved(session, project_id, saved_id, include_personal)


def remove_saved(
    store: KnowledgeStore,
    project_id: str,
    saved_id: str,
    command: SavedReadingRemoval | dict[str, Any],
    key: str,
    include_personal: bool = False,
) -> dict[str, Any]:
    """Retire library eligibility, retaining all immutable records and exact original raw."""
    body = SavedReadingRemoval.model_validate(command)
    session = store.session
    operation, fingerprint, previous = _metadata_operation(
        session, project_id, saved_id, "remove", body, key
    )
    saved = session.get(QuerySavedKnowledge, saved_id)
    if saved is None or saved.project_id != project_id:
        raise KnowledgeError("QUERY_SAVED_NOT_FOUND", "项目中没有该保存内容")
    preference = session.get(QuerySavedPreference, saved_id)
    if previous or (preference and preference.removed_at):
        if preference is None or preference.removed_at is None:
            raise KnowledgeError("QUERY_SAVED_INVALID", "移除记录不完整")
        return {
            "saved_id": saved_id,
            "removed_at": preference.removed_at,
            "metadata_revision": preference.revision,
        }
    get_saved(session, project_id, saved_id, include_personal)
    preference = _preference(session, saved_id, body.expected_revision)
    preference.removed_at = preference.updated_at = now()
    preference.revision += 1
    store.audit_event(
        project_id,
        "query.saved_removed",
        {"saved_id": saved_id, "metadata_revision": preference.revision},
        actor="user",
        trigger="query_library",
    )
    result = {
        "saved_id": saved_id,
        "removed_at": preference.removed_at,
        "metadata_revision": preference.revision,
    }
    session.add(QueryOperation(key=operation, request_hash=fingerprint, response=result))
    session.flush()
    return result


def save_query(
    store: KnowledgeStore,
    command: QuerySaveCommand | dict[str, Any],
    key: str,
    *,
    project_id: str,
) -> dict[str, Any]:
    """Caller owns one transaction. No chargeable P08 call is needed to copy validated passages."""
    body = QuerySaveCommand.model_validate(command)
    session = store.session
    if not key.strip() or len(key) > 120:
        raise KnowledgeError("IDEMPOTENCY_KEY_INVALID", "保存请求标识为空或过长")
    op_key = f"query-save:{project_id}:{key}"
    request_hash = digest(body.model_dump(mode="json"))
    previous = session.get(QueryOperation, op_key)
    if previous and previous.request_hash != request_hash:
        raise KnowledgeError("IDEMPOTENCY_CONFLICT", "相同操作键对应不同保存请求")
    # Selected reference order is answer order, not checkbox click order. Baseline
    # protects a new append, but does not make an already saved selection duplicate.
    fingerprint = digest(
        {
            "source_query_id": body.source_query_id,
            "answer_version_id": body.answer_version_id,
            "selected_passage_refs": sorted(body.selected_passage_refs),
            "kind": body.kind,
            "target_document_id": body.target_document_id,
        }
    )
    existing = session.scalar(
        select(QuerySavedKnowledge).where(
            QuerySavedKnowledge.project_id == project_id,
            QuerySavedKnowledge.fingerprint == fingerprint,
        )
    )
    if previous or existing:
        saved_id = previous.response["saved_id"] if previous else existing.id  # type: ignore[union-attr]
        saved_row = session.get(QuerySavedKnowledge, saved_id)
        run, answer, data = _checked_answer(session, project_id, body, revalidate=False)
        if saved_row is None or (
            saved_row.fingerprint != fingerprint
            or saved_row.manifest.get("answer_hash") != digest(answer.data)
            or saved_row.manifest.get("model_lineage_hash") != _lineage_hash(session, answer)
            or saved_row.manifest.get("source_context_hash") != digest(run.snapshot["context"])
        ):
            raise KnowledgeError("QUERY_SAVED_INVALID", "保存来源谱系与冻结记录不匹配")
        _check_selected_numeric_layout(session, run, data, set(body.selected_passage_refs))
        result = get_saved(session, project_id, saved_id, include_personal=True)
        if result["content_state"] != "valid":
            raise KnowledgeError("QUERY_SAVE_DEPENDENCY_INVALID", "已保存内容的来源已变化")
        if previous is None:
            session.add(
                QueryOperation(
                    key=op_key, request_hash=request_hash, response={"saved_id": saved_id}
                )
            )
        return result
    run, answer, data = _checked_answer(session, project_id, body)
    selected = set(body.selected_passage_refs)
    _check_selected_numeric_layout(session, run, data, selected)
    passages = [p for p in data.passages if p.local_ref in selected]
    if len(passages) != len(selected):
        raise KnowledgeError("QUERY_SAVE_PASSAGE_INVALID", "所选段落不属于本次回答")
    context = run.snapshot["context"]
    references = {r["ref"]: r for r in context["references"]}
    new_passages = []
    frozen = []
    for passage in passages:
        try:
            refs = [references[r] for r in passage.source_refs]
            dependencies = [d for ref in refs if (d := _dependency(ref)) is not None]
        except (KeyError, TypeError) as exc:
            raise KnowledgeError(
                "QUERY_SAVE_REFERENCE_INVALID", "回答引用不属于冻结来源清单"
            ) from exc
        dependencies = list({digest(d): d for d in dependencies}.values())
        checked = validate_dependencies(session, project_id, dependencies, True, "local")
        if checked["content_state"] != "valid":
            raise KnowledgeError(
                "QUERY_SAVE_DEPENDENCY_INVALID", ",".join(checked["issues"]) or "段落缺少有效根来源"
            )
        lineage_dependencies = dependencies
        dependencies = _root_dependencies(session, dependencies)
        local_ref = f"query-{answer.id}-{passage.local_ref}"
        new_passages.append(
            {
                "local_ref": local_ref,
                "text": passage.text,
                "attribution": passage.attribution,
                "dependencies": dependencies,
                "caveats": passage.caveats,
            }
        )
        frozen.append(
            {
                "answer_local_ref": passage.local_ref,
                "document_local_ref": local_ref,
                "text_hash": text_hash(passage.text),
                "attribution": passage.attribution,
                "caveats": passage.caveats,
                "source_refs": passage.source_refs,
                "lineage_dependencies": lineage_dependencies,
                "dependencies": dependencies,
                "roots": checked["roots"],
            }
        )
    title = run.request["question"].strip()[:160]
    kind = "synthesis"  # Insight is a derived knowledge type, not a new Wiki/file format.
    old_passages = []
    if body.target_document_id:
        document = session.get(QueryDocument, body.target_document_id)
        version = session.get(QueryDocumentVersion, body.base_version_id)
        if (
            not document
            or document.project_id != project_id
            or not version
            or version.document_id != document.id
            or version.state != "saved"
            or document.current_version_id != version.id
        ):
            raise KnowledgeError("DOCUMENT_VERSION_CONFLICT", "目标文档或明确基线已变化")
        kind, title = document.kind, document.title
        for old in session.scalars(
            select(QueryPassage)
            .where(QueryPassage.version_id == version.id)
            .order_by(QueryPassage.ordinal)
        ):
            if text_hash(old.text) != old.sha256:
                raise KnowledgeError("QUERY_SAVE_DEPENDENCY_INVALID", "目标文档段落哈希不匹配")
            old_passages.append(
                {
                    "local_ref": old.local_ref,
                    "text": old.text,
                    "attribution": old.attribution,
                    "dependencies": old.dependencies,
                    "caveats": old.caveats,
                }
            )
    saved_id = str(uuid4())
    document_result = store.query().save_document(
        DocumentSaveRequest.model_validate(
            {
                "project_id": project_id,
                "kind": kind,
                "title": title,
                "document_id": body.target_document_id,
                "base_version_id": body.base_version_id,
                "passages": [*old_passages, *new_passages],
                "state": "saved",
            }
        ),
        f"query-save-document:{saved_id}",
    )
    saved_pids = document_result["passage_ids"][len(old_passages) :]
    graph_revision = store.event(
        project_id,
        "QUERY_KNOWLEDGE_SAVED",
        {
            "saved_id": saved_id,
            "kind": body.kind,
            "source_query_id": run.id,
            "answer_version_id": answer.id,
            "document_id": document_result["document_id"],
            "version_id": document_result["version_id"],
            "passage_ids": saved_pids,
        },
        actor="user",
        trigger="query_save",
    )
    saved = QuerySavedKnowledge(
        id=saved_id,
        project_id=project_id,
        kind=body.kind,
        title=title,
        source_query_id=run.id,
        answer_version_id=answer.id,
        document_id=document_result["document_id"],
        document_version_id=document_result["version_id"],
        fingerprint=fingerprint,
        input_hash=run.input_hash,
        selected_passage_refs=[p.local_ref for p in passages],
        passage_ids=saved_pids,
        manifest={
            "policy": "query-saved-1",
            "source_query_id": run.id,
            "answer_version_id": answer.id,
            "answer_hash": digest(answer.data),
            "model_lineage_hash": _lineage_hash(session, answer),
            "source_context_hash": digest(run.snapshot["context"]),
            "input_hash": run.input_hash,
            "passages": frozen,
            "transformation": "validated_passage_copy",
            "model_calls": 0,
        },
        graph_revision=graph_revision,
        created_at=now(),
    )
    session.add(saved)
    session.add(
        QueryOperation(key=op_key, request_hash=request_hash, response={"saved_id": saved.id})
    )
    session.flush()
    return get_saved(session, project_id, saved.id, include_personal=True)


def derived_graph(
    session: Session, project_id: str, include_personal: bool = False, purpose: str = "local"
) -> dict[str, Any]:
    """A separate citation layer; it never promotes these edges to scientific relations."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    for saved in list_saved(session, project_id, include_personal, purpose):
        if saved["content_state"] != "valid":
            continue
        sid = saved["saved_id"]
        nodes[sid] = {
            "id": sid,
            "kind": saved["kind"],
            "label": saved["title"],
            "saved_id": sid,
            "layer": "derived",
        }
        dependencies = {
            (d["type"], d["id"]): d
            for p in saved["passages"]
            for d in p["dependencies"]
            if d["type"] == "node"
        }
        roots = {digest(r): r for passage in saved["passages"] for r in passage["roots"]}
        targets: set[str] = set()
        for (_, nid), _ in dependencies.items():
            node = session.get(KnowledgeNode, nid)
            if node is not None:
                nodes[nid] = {
                    "id": nid,
                    "kind": node.kind,
                    "label": node.text,
                    "source_id": nid,
                    "paper_id": node.paper_id,
                    "layer": "source_reference",
                }
                targets.add(nid)
        for root in roots.values():
            oid = root["id"]
            nodes[oid] = {
                "id": oid,
                "kind": root["type"],
                "label": root.get("quote") or root.get("relative_path") or root["type"],
                "source_id": oid,
                "paper_id": root.get("paper_id"),
                "layer": "source_reference",
            }
            targets.add(oid)
            if root.get("paper_id"):
                paper = session.get(Paper, root["paper_id"])
                if paper is not None:
                    nodes[paper.id] = {
                        "id": paper.id,
                        "kind": "paper",
                        "label": paper.title,
                        "source_id": paper.id,
                        "layer": "source_reference",
                    }
                    targets.add(paper.id)
        for target in sorted(targets):
            edge_id = digest([sid, target])
            edges[edge_id] = {
                "id": edge_id,
                "source": sid,
                "target": target,
                "relation": "DERIVED_FROM",
                "epistemic_status": "derived_reference",
            }
    return {"nodes": [nodes[k] for k in sorted(nodes)], "edges": [edges[k] for k in sorted(edges)]}
