"""P5 preparation, terminal validation and explicit document materialization."""

import math
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, text_hash
from researchgraph.model_settings import snapshot_for
from researchgraph.models import Job, now
from researchgraph.p5_contracts import WorkflowPrepare
from researchgraph.p5_models import P5ModelRun, P5Workflow
from researchgraph.p5_sources import collect_scope, selection_map
from researchgraph.p5_transport import (
    PROMPTS,
    load_prompt,
    make_wire,
    output_schema,
    validate_output,
)
from researchgraph.query_context import build_context, validate_context
from researchgraph.query_documents import validate_dependencies
from researchgraph.query_models import (
    QueryDocument,
    QueryDocumentVersion,
    QueryOperation,
    QueryPassage,
)


class WorkflowInputError(KnowledgeError):
    """A changed trusted input, rather than a defective model response."""


def checked(session: Session, project_id: str, workflow_id: str) -> P5Workflow:
    row = session.get(P5Workflow, workflow_id)
    if row is None or row.project_id != project_id:
        raise KnowledgeError("P5_WORKFLOW_NOT_FOUND", "项目中不存在该工作流")
    return row


def runs(session: Session, workflow_id: str) -> list[P5ModelRun]:
    return list(
        session.scalars(
            select(P5ModelRun)
            .where(P5ModelRun.workflow_id == workflow_id)
            .order_by(P5ModelRun.sequence)
        )
    )


def _base(
    session: Session, project_id: str, request: WorkflowPrepare, *, require_head: bool = True
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    if request.kind != "wiki_delta":
        return None, {}
    from researchgraph.wiki_models import WikiPage, WikiSection, WikiVersion
    from researchgraph.wiki_store import wiki_version_state

    doc = session.get(QueryDocument, request.page_id)
    page = session.get(WikiPage, request.page_id)
    version = session.get(QueryDocumentVersion, request.base_version_id)
    metadata = session.get(WikiVersion, request.base_version_id)
    if (
        not doc
        or not page
        or doc.project_id != project_id
        or not version
        or not metadata
        or version.document_id != doc.id
    ):
        raise KnowledgeError("WIKI_PAGE_NOT_FOUND", "更新目标不属于本项目或版本不可用")
    if require_head and page.head_version_id != request.base_version_id:
        raise KnowledgeError("WIKI_VERSION_CONFLICT", "Wiki基线已更新，请读取新版本")
    if wiki_version_state(session, version.id):
        raise KnowledgeError("WIKI_SNAPSHOT_INVALID", "Wiki基线快照完整性无法核验")
    sections = list(
        session.execute(
            select(WikiSection, QueryPassage)
            .join(QueryPassage, WikiSection.passage_id == QueryPassage.id)
            .where(WikiSection.version_id == version.id)
            .order_by(QueryPassage.ordinal)
        )
    )
    selected = {
        s.section_id: (s, p) for s, p in sections if s.section_id in request.affected_section_ids
    }
    if set(selected) != set(request.affected_section_ids):
        raise KnowledgeError("P5_DELTA_SCOPE_INVALID", "更新范围包含未知段落")
    model_sections = []
    targets = {}
    signatures = {}
    for index, section_id in enumerate(request.affected_section_ids, 1):
        section, passage = selected[section_id]
        state = validate_dependencies(
            session, project_id, passage.dependencies, request.query.include_personal, "model"
        )
        if any("NOT_AUTHORIZED" in issue for issue in state["issues"]):
            raise KnowledgeError(
                "P5_PERMISSION_CHANGED", "旧Wiki包含未获本次模型用途授权的个人来源"
            )
        if request.personal_sources is not None:
            from researchgraph.p5_personal import assert_selected_roots
            from researchgraph.query_save import _root_dependencies

            assert_selected_roots(state["roots"], request.personal_sources.model_dump(mode="json"))
            assert_selected_roots(
                _root_dependencies(session, passage.dependencies),
                request.personal_sources.model_dump(mode="json"),
            )
        if passage.attribution == "user_view" and not request.query.include_personal:
            raise KnowledgeError("P5_PERMISSION_CHANGED", "个人段落未获本次模型用途授权")
        short = f"T{index:05d}"
        targets[short] = section_id
        signatures[short] = digest(
            {
                "text": passage.text,
                "sha256": passage.sha256,
                "dependencies": passage.dependencies,
                "caveats": passage.caveats,
                "attribution": passage.attribution,
                "heading": section.heading,
                "conditions": section.conditions,
                "stale_reason": section.stale_reason,
            }
        )
        model_sections.append(
            {
                "section_ref": short,
                "heading": section.heading,
                "text": passage.text,
                "attribution": passage.attribution,
                "conditions": section.conditions,
                "content_state": state["content_state"],
                "stale_reason": section.stale_reason,
                "notice": "历史待更新文本不是本次新结论的证据；仅本次来源短编号可用于新依据",
            }
        )
    return {
        "version_id": version.id,
        "content_hash": metadata.content_hash,
        "section_hashes": signatures,
        "model_sections": model_sections,
    }, targets


def _lint_snapshot(
    session: Session, project_id: str, request: WorkflowPrepare
) -> dict[str, Any] | None:
    run_id = request.lint_run_id
    if not run_id:
        return None
    from researchgraph.lint_service import get_run, list_issues, validate_run_input

    report = get_run(session, project_id, run_id)
    if report["scope"]["include_personal"] != request.query.include_personal or set(
        report["scope"]["paper_ids"]
    ) != set(request.query.paper_ids):
        raise KnowledgeError(
            "P5_LINT_SCOPE_INVALID", "语义检查须使用相同论文和个人资料范围的规则报告"
        )
    if report["status"] not in {"completed", "partial"}:
        raise KnowledgeError("P5_LINT_NOT_READY", "请先完成确定性规则检查")
    if not validate_run_input(session, project_id, run_id):
        raise KnowledgeError("P5_BASE_CHANGED", "诊断来源或权限已变化，请重新检查")
    issues = list_issues(session, project_id, run_id, page_size=2**31 - 1)["items"]
    # Repair plans are current presentation guidance, never frozen model input.
    # Keep old P09 snapshots/wire hashes unchanged when read-only UI fields evolve.
    issues = [
        {key: value for key, value in issue.items() if key != "repair_plan"} for issue in issues
    ]
    scope = report["scope"]
    if request.personal_sources is not None:
        from researchgraph.p5_personal import assert_selected_roots

        selection = request.personal_sources.model_dump(mode="json")
        selected_ids = {
            "note": set(selection["note_ids"]),
            "annotation": set(selection["annotation_ids"]),
            "external": set(selection["external_version_ids"]),
        }

        def permitted(kind: str, oid: str) -> bool:
            if kind in selected_ids:
                return oid in selected_ids[kind]
            paragraphs = []
            if kind == "passage":
                paragraph = session.get(QueryPassage, oid)
                paragraphs = [paragraph] if paragraph else []
            elif kind in {"document", "document_version"}:
                if kind == "document":
                    document = session.get(QueryDocument, oid)
                    if document and document.kind == "external":
                        return bool(
                            session.scalar(
                                select(QueryDocumentVersion.id).where(
                                    QueryDocumentVersion.document_id == oid,
                                    QueryDocumentVersion.id.in_(selected_ids["external"]),
                                )
                            )
                        )
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
                paragraph_version = session.get(QueryDocumentVersion, paragraph.version_id)
                paragraph_document = (
                    session.get(QueryDocument, paragraph_version.document_id)
                    if paragraph_version
                    else None
                )
                if paragraph_document and paragraph_document.kind == "external":
                    if paragraph.version_id not in selected_ids["external"]:
                        return False
                    continue
                state = validate_dependencies(
                    session,
                    project_id,
                    paragraph.dependencies,
                    request.query.include_personal,
                    "model",
                )
                if any("NOT_AUTHORIZED" in code for code in state["issues"]) or (
                    paragraph.attribution == "user_view" and state["content_state"] != "valid"
                ):
                    return False
                try:
                    assert_selected_roots(state["roots"], selection)
                    from researchgraph.query_save import _root_dependencies

                    assert_selected_roots(
                        _root_dependencies(session, paragraph.dependencies), selection
                    )
                except KnowledgeError:
                    return False
            return True

        issues = [issue for issue in issues if permitted(issue["object_type"], issue["object_id"])]
        scope = {
            **scope,
            "document_ids": [
                oid for oid in scope.get("document_ids", []) if permitted("document", oid)
            ],
        }
    return {
        "run_id": run_id,
        "scope": scope,
        "input_hash": report["input_hash"],
        "rule_version": report["rule_version"],
        "status": report["status"],
        "issues": issues,
        "notice": "确定性报告独立保留；模型仅提供额外语义建议",
    }


def validate_workflow(session: Session, row: P5Workflow, *, require_head: bool = False) -> None:
    try:
        _validate_workflow(session, row, require_head=require_head)
    except KnowledgeError as exc:
        raise WorkflowInputError(exc.code, str(exc)) from exc


def _validate_workflow(session: Session, row: P5Workflow, *, require_head: bool = False) -> None:
    snapshot = row.snapshot
    if row.input_hash != digest(snapshot):
        raise KnowledgeError("P5_PROTOCOL_CHANGED", "工作流冻结输入已变化")
    request = WorkflowPrepare.model_validate(row.request)
    if request.query.project_id != row.project_id or snapshot["request"] != row.request:
        raise KnowledgeError("P5_SCOPE_INVALID", "工作流项目或请求身份不匹配")
    validate_context(
        session, snapshot["context"], snapshot["retrieval"], model_snapshot=snapshot["model"]
    )
    if selection_map(session, snapshot["context"]) != snapshot["source_revisions"]:
        raise KnowledgeError("P5_BASE_CHANGED", "来源组织版本已变化，请准备新的工作流")
    base, targets = _base(session, row.project_id, request, require_head=require_head)
    if base != snapshot["base"] or targets != snapshot["targets"]:
        raise KnowledgeError("P5_BASE_CHANGED", "Wiki版本或待更新段落已改变")
    if _lint_snapshot(session, row.project_id, request) != snapshot["lint"]:
        raise KnowledgeError("P5_BASE_CHANGED", "确定性检查范围已变化")
    if text_hash(load_prompt(row.kind)) != snapshot["prompt_hash"]:
        raise KnowledgeError("P5_PROTOCOL_CHANGED", "任务Prompt版本发生变化，请准备新任务")
    schema = output_schema(row.kind, snapshot["context"], list(targets))
    wire = make_wire(row.kind, snapshot["context"], base, targets, snapshot["lint"])
    if digest(schema) != snapshot["schema_hash"] or digest(wire) != snapshot["wire_hash"]:
        raise KnowledgeError("P5_PROTOCOL_CHANGED", "任务Schema或传输契约已变化")


def prepare(session: Session, project_id: str, body: WorkflowPrepare, key: str) -> P5Workflow:
    if body.query.project_id != project_id:
        raise KnowledgeError("P5_SCOPE_INVALID", "请求项目与路径不一致")
    request = body.model_dump(mode="json")
    op_key = f"p5-prepare:{project_id}:{key}"
    previous = session.get(QueryOperation, op_key)
    if previous:
        if previous.request_hash != digest(request):
            raise KnowledgeError("IDEMPOTENCY_CONFLICT", "同一标识对应不同工作流")
        row = checked(session, project_id, previous.response["workflow_id"])
        validate_workflow(session, row)
        return row
    query = body.query
    if query.include_personal and body.personal_sources is None:
        if body.kind == "lint_semantic":
            _lint_snapshot(session, project_id, body)
        raise KnowledgeError(
            "P5_PERSONAL_SELECTION_REQUIRED", "新工作流须明确逐份选择个人来源；可选择空集合"
        )
    model = snapshot_for(session, project_id, "reasoning")
    found = collect_scope(
        session,
        project_id,
        query,
        exclude_document_id=body.page_id if body.kind == "wiki_delta" else None,
        personal_sources=body.personal_sources.model_dump(mode="json")
        if body.personal_sources is not None
        else None,
    )
    context = build_context(
        session,
        query.model_dump(mode="json"),
        found,
        model_snapshot=model,
        include_layout=True,
        include_scientific_guidance=True,
    )
    validate_context(session, context, found, model_snapshot=model)
    base, targets = _base(session, project_id, body)
    lint = _lint_snapshot(session, project_id, body)
    schema = output_schema(body.kind, context, list(targets))
    wire = make_wire(body.kind, context, base, targets, lint)
    prompt = load_prompt(body.kind)
    estimated = math.ceil((len(str(wire).encode("utf-8")) + len(prompt.encode("utf-8"))) / 3)
    capacity = context["capacity"]
    window, output = capacity["context_window"], capacity["reserved_output_tokens"]
    sufficient = window is None or estimated <= window - (output or 0)
    snapshot = {
        "request": request,
        "retrieval": found,
        "context": context,
        "model": model,
        "base": base,
        "targets": targets,
        "lint": lint,
        "source_revisions": selection_map(session, context),
        "schema_hash": digest(schema),
        "wire_hash": digest(wire),
        "prompt_hash": text_hash(prompt),
        "estimated_input_tokens": estimated,
        "complete_context_sufficient": sufficient,
    }
    fingerprint = digest(snapshot)
    cache_key = f"p5-prepared-input:{project_id}:{fingerprint}"
    cache = session.get(QueryOperation, cache_key)
    if cache:
        row = checked(session, project_id, cache.response["workflow_id"])
        validate_workflow(session, row)
    else:
        row = P5Workflow(
            id=str(uuid4()),
            project_id=project_id,
            kind=body.kind,
            request=request,
            snapshot=snapshot,
            input_hash=fingerprint,
            status="prepared" if context["status"] == "ready" and sufficient else "insufficient",
            created_at=now(),
            updated_at=now(),
        )
        session.add(row)
        session.flush()
        session.add(
            QueryOperation(
                key=cache_key, request_hash=fingerprint, response={"workflow_id": row.id}
            )
        )
        KnowledgeStore(session).audit_event(
            project_id, "p5.prepared", {"workflow_id": row.id, "kind": row.kind}
        )
    session.add(
        QueryOperation(key=op_key, request_hash=digest(request), response={"workflow_id": row.id})
    )
    return row


def validate_run(session: Session, row: P5Workflow, run: P5ModelRun) -> dict[str, Any]:
    validate_workflow(session, row)
    job = session.get(Job, run.job_id)
    if (
        run.workflow_id != row.id
        or not job
        or job.kind != "p5_workflow"
        or job.project_id != row.project_id
        or (job.payload or {}).get("workflow_id") != row.id
        or run.prompt_name != PROMPTS[row.kind]
        or run.prompt_hash != row.snapshot["prompt_hash"]
        or run.input_hash != row.snapshot["wire_hash"]
        or run.parameters.get("workflow_hash") != row.input_hash
        or run.parameters.get("schema_hash") != row.snapshot["schema_hash"]
        or run.parameters.get("model_snapshot") != row.snapshot["model"]
        or not run.raw_output
        or not run.parameters.get("raw_complete")
        or run.parameters.get("raw_sha256") != text_hash(run.raw_output)
    ):
        raise WorkflowInputError("P5_RESPONSE_CHANGED", "模型记录或原始输出与冻结请求不一致")
    result = validate_output(session, row, run.id, run.raw_output)
    if run.status == "succeeded" and run.parameters.get("validated_result_hash") != digest(result):
        raise WorkflowInputError("P5_RESPONSE_CHANGED", "已完成模型结果指纹不匹配")
    return result


def _validate_local_result(session: Session, row: P5Workflow) -> None:
    """GET authority also covers personal text supplied only as historical target/diagnostics."""
    from researchgraph.query_saved_lifecycle import reference_dependency

    dependencies = [
        dependency
        for reference in row.snapshot["context"]["references"]
        if (dependency := reference_dependency(reference)) is not None
    ]
    selection = row.request.get("personal_sources")
    if selection is not None:
        from researchgraph.p5_personal import selected_sources

        selected_sources(session, row.project_id, selection, purpose="local")
    paragraph_ids: set[str] = set()
    if row.kind == "wiki_delta":
        from researchgraph.wiki_models import WikiSection

        paragraph_ids.update(
            session.scalars(
                select(WikiSection.passage_id).where(
                    WikiSection.version_id == row.request["base_version_id"],
                    WikiSection.section_id.in_(row.request["affected_section_ids"]),
                )
            )
        )
    lint = row.snapshot.get("lint")
    for issue in lint.get("issues", []) if lint else []:
        kind, oid = issue["object_type"], issue["object_id"]
        if kind == "note":
            from researchgraph.knowledge_models import NoteSnapshot

            note = session.get(NoteSnapshot, oid)
            if note:
                dependencies.append({"type": "note", "id": oid, "sha256": note.sha256})
        elif kind == "annotation":
            from researchgraph.p5_personal import annotation_source

            annotation_source(session, row.project_id, oid, purpose="local")
        elif kind == "external":
            from researchgraph.external_documents import validate_external_version

            validate_external_version(session, row.project_id, oid, include_personal=True)
        elif kind == "passage":
            paragraph_ids.add(oid)
        elif kind in {"document", "document_version"}:
            version_ids = (
                list(
                    session.scalars(
                        select(QueryDocumentVersion.id).where(
                            QueryDocumentVersion.document_id == oid
                        )
                    )
                )
                if kind == "document"
                else [oid]
            )
            paragraph_ids.update(
                session.scalars(
                    select(QueryPassage.id).where(QueryPassage.version_id.in_(version_ids))
                )
            )
    for paragraph_id in paragraph_ids:
        paragraph = session.get(QueryPassage, paragraph_id)
        if paragraph:
            dependencies.extend(paragraph.dependencies)
    state = validate_dependencies(
        session, row.project_id, dependencies, row.request["query"]["include_personal"], "local"
    )
    if any("NOT_AUTHORIZED" in issue for issue in state["issues"]):
        raise KnowledgeError("P5_PERMISSION_CHANGED", "旧结果的个人资料本地读取授权已撤销")


def view(session: Session, row: P5Workflow) -> dict[str, Any]:
    recorded = runs(session, row.id)
    job = session.get(Job, row.job_id) if row.job_id else None
    status = job.status if job and row.status not in {"succeeded", "insufficient"} else row.status
    result, error, code = row.result, row.error, row.error_code
    current_input = True
    try:
        validate_workflow(session, row)
        _validate_local_result(session, row)
        if row.status == "succeeded":
            valid = next((r for r in recorded if r.status == "succeeded"), None)
            if not valid or validate_run(session, row, valid) != result:
                raise KnowledgeError("P5_RESPONSE_CHANGED", "工作流结果与终验原响应不一致")
    except KnowledgeError as exc:
        status, result, error, code = "failed", None, str(exc), exc.code
        current_input = not isinstance(exc, WorkflowInputError)
    recoverable = False
    if current_input and status in {"failed", "interrupted", "cancelled"}:
        for old in recorded:
            if old.parameters.get("raw_complete"):
                try:
                    validate_run(session, row, old)
                except WorkflowInputError as exc:
                    current_input = False
                    status, result, error, code = "failed", None, str(exc), exc.code
                    break
                except KnowledgeError:
                    pass
                else:
                    recoverable = True
                    break
    return {
        "id": row.id,
        "kind": row.kind,
        "status": status,
        "historical_status": row.status,
        "input_hash": row.input_hash,
        "job_id": row.job_id,
        "result": result,
        "question": row.request["query"]["question"],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "error_code": code,
        "error": error,
        "request_count": len(recorded),
        "request_limit": 2,
        "can_continue": status in {"failed", "interrupted", "cancelled"}
        and current_input
        and (len(recorded) < 2 or recoverable),
        "model_runs": [
            {
                "id": r.id,
                "status": r.status,
                "usage": r.parameters.get("usage", {}),
                "duration_seconds": r.parameters.get("duration_seconds"),
                "error_code": r.parameters.get("error_code"),
                "error": r.error,
                "cost_known": False,
            }
            for r in recorded
        ],
    }


def enqueue(session: Session, row: P5Workflow, key: str, *, continue_requested: bool) -> Job:
    validate_workflow(session, row, require_head=True)
    if row.status == "insufficient":
        raise KnowledgeError(
            "P5_EVIDENCE_INSUFFICIENT", "完整范围缺少证据或超出已知模型容量；未发模型"
        )
    op_key = f"p5-generate:{row.project_id}:{key}"
    fingerprint = digest({"workflow_id": row.id, "continue_requested": continue_requested})
    previous = session.get(QueryOperation, op_key)
    if previous:
        if previous.request_hash != fingerprint:
            raise KnowledgeError("IDEMPOTENCY_CONFLICT", "同一标识不能用于不同任务")
        job = session.get(Job, previous.response["job_id"])
        if not job:
            raise KnowledgeError("JOB_NOT_FOUND", "模型任务不存在")
        return job
    latest = session.get(Job, row.job_id) if row.job_id else None
    if latest and (latest.status in {"queued", "running", "succeeded"} or not continue_requested):
        job = latest
    else:
        previous_runs = runs(session, row.id)
        recoverable = False
        for old in previous_runs:
            if old.parameters.get("raw_complete"):
                try:
                    validate_run(session, row, old)
                    recoverable = True
                except WorkflowInputError:
                    raise
                except KnowledgeError:
                    pass
        if len(previous_runs) >= 2 and not recoverable:
            raise KnowledgeError(
                "P5_REQUEST_LIMIT", "已达本任务两次显式请求上限，已发送槽位不会重发"
            )
        if previous_runs and not continue_requested:
            raise KnowledgeError(
                "P5_CONTINUE_REQUIRED", "失败请求保留，请明确继续后使用下一请求槽位"
            )
        job = Job(
            id=str(uuid4()),
            kind="p5_workflow",
            project_id=row.project_id,
            payload={
                "workflow_id": row.id,
                "input_hash": row.input_hash,
                "allow_network": True,
                "request_budget": len(previous_runs) if recoverable else len(previous_runs) + 1,
            },
            status="queued",
            attempt=0,
            created_at=now(),
            updated_at=now(),
        )
        session.add(job)
        session.flush()
        row.job_id, row.status, row.error, row.error_code, row.updated_at = (
            job.id,
            "queued",
            None,
            None,
            now(),
        )
    session.add(QueryOperation(key=op_key, request_hash=fingerprint, response={"job_id": job.id}))
    return job


def materialize(
    store: KnowledgeStore, project_id: str, workflow_id: str, key: str
) -> dict[str, Any]:
    session = store.session
    row = checked(session, project_id, workflow_id)
    validate_workflow(session, row)
    if row.status != "succeeded" or not row.result:
        raise KnowledgeError("P5_NOT_READY", "尚无可保存的终验结果")
    recorded = next((r for r in runs(session, row.id) if r.status == "succeeded"), None)
    if not recorded or validate_run(session, row, recorded) != row.result:
        raise KnowledgeError("P5_RESPONSE_CHANGED", "模型原结果未通过完整复验")
    if row.kind == "lint_semantic":
        raise KnowledgeError("P5_ACTION_INVALID", "语义诊断仅为建议，不能作为文件或知识编辑执行")
    from researchgraph.wiki_store import read_page

    stable_key = f"p5-materialize:{row.id}"
    previous = session.get(QueryOperation, stable_key)
    if previous:
        return read_page(
            session,
            project_id,
            previous.response["page_id"],
            version_id=previous.response["version_id"],
            include_personal=row.request["query"]["include_personal"],
        )
    validate_workflow(session, row, require_head=True)
    if row.kind == "wiki_delta" and not row.result["patch"]["operations"]:
        raise KnowledgeError("P5_NO_CHANGES", "本次更新未提出改动，无需创建新版本")
    if row.kind == "wiki_synthesis":
        result: dict[str, Any] = store.wiki().create_draft(project_id, row.result["draft"], key)
    else:
        result = store.wiki().apply_patch(
            project_id,
            row.request["page_id"],
            {**row.result["patch"], "provenance": row.result["provenance"]},
            key,
        )
    session.add(
        QueryOperation(
            key=stable_key,
            request_hash=row.input_hash,
            response={"page_id": result["page_id"], "version_id": result["version_id"]},
        )
    )
    return read_page(
        session,
        project_id,
        result["page_id"],
        version_id=result["version_id"],
        include_personal=row.request["query"]["include_personal"],
    )
