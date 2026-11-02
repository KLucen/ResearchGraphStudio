"""Optional display-only translation, guarded against stale scientific revisions."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI
from pydantic import Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from researchgraph.extraction import call_model, mark_run, reusable_model_run
from researchgraph.graph_models import KnowledgeDisplay
from researchgraph.graph_projection import display_data
from researchgraph.knowledge_contracts import StrictModel
from researchgraph.knowledge_models import KnowledgeNode, KnowledgeOperation, ModelRun
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import Job, Paper, now
from researchgraph.providers import provider_for
from researchgraph.schemas import JobView
from researchgraph.unified_contracts import TranslationRepair


class TranslationRequest(StrictModel):
    node_ids: list[str] = Field(min_length=1, max_length=30)
    provider: Literal["mock", "project"] = "project"
    allow_network: bool = False


def apply_translation(
    store: KnowledgeStore,
    candidate: dict[str, Any],
    snapshot: dict[str, Any],
    run_id: str,
    key: str,
) -> dict[str, Any]:
    parsed = TranslationRepair.model_validate(candidate)
    fingerprint = digest({"candidate": candidate, "snapshot": snapshot})
    previous = store.session.get(KnowledgeOperation, key)
    if previous:
        if previous.request_hash != fingerprint:
            raise KnowledgeError("IDEMPOTENCY_CONFLICT", "补译结果与已有操作冲突")
        return previous.response
    if {i.node_ref for i in parsed.items} != set(snapshot) or len(parsed.items) != len(snapshot):
        raise KnowledgeError("SOURCE_MISMATCH", "补译对象与请求不一致")
    changes = []
    project_id = ""
    for item in parsed.items:
        expected = snapshot[item.node_ref]
        node = store.session.get(KnowledgeNode, expected["id"])
        if (
            not node
            or node.revision != expected["revision"]
            or digest(node.payload) != expected["hash"]
        ):
            raise KnowledgeError("REVISION_CONFLICT", "原文知识已更新，请重新请求补译")
        before = display_data(store.session, node)
        if digest(before) != expected["display_hash"]:
            raise KnowledgeError("REVISION_CONFLICT", "显示译文已更新，请重新请求补译")
        paper = store.session.get(Paper, node.paper_id)
        assert paper
        project_id = paper.project_id
        row = store.session.get(KnowledgeDisplay, node.id)
        if row is None:
            row = KnowledgeDisplay(
                node_id=node.id, source_revision=node.revision, model_run_id=run_id, data={}
            )
            store.session.add(row)
        after = {
            **before,
            "label_zh": item.label_zh,
            "summary_zh": item.summary_zh,
            "translation_status": "machine_unreviewed",
        }
        row.data, row.model_run_id, row.source_revision = after, run_id, node.revision
        changes.append({"node_id": node.id, "before": before, "after": after})
    revision = store.event(
        project_id, "DISPLAY_TRANSLATED", {"changes": changes}, model_run_id=run_id
    )
    result = {"node_ids": [x["node_id"] for x in changes], "new_revision": revision}
    store.session.add(KnowledgeOperation(key=key, request_hash=fingerprint, response=result))
    return result


async def run_translation(engine: Engine, job_id: str) -> None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        assert job and job.payload
        payload = dict(job.payload)
    if payload.get("model_snapshot"):
        from researchgraph.model_settings import from_snapshot

        provider = from_snapshot(
            payload["model_snapshot"],
            Path(str(engine.url.database)).parent,
            payload["allow_network"],
        )
    else:
        provider = provider_for(payload["provider"], payload["allow_network"])
    prompt = "P04_label_translation_repair"
    data = {"items": payload["items"]}
    cached = reusable_model_run(engine, job_id, provider, prompt, data)
    run_id, raw = cached or await call_model(
        engine,
        job_id,
        payload["version_id"],
        provider,
        prompt,
        data,
        TranslationRepair.model_json_schema(),
    )
    try:
        with Session(engine) as session, session.begin():
            job = session.get(Job, job_id)
            if not job or job.status != "running":
                return
            result = KnowledgeStore(session).apply_translation(
                TranslationRepair.model_validate_json(raw).model_dump(),
                payload["snapshot"],
                run_id,
                "translation:" + job_id,
            )
            run = session.get(ModelRun, run_id)
            assert run
            run.status, run.finished_at = "succeeded", now()
            job.result, job.status, job.updated_at = result, "succeeded", now()
    except Exception:
        mark_run(engine, run_id, "validation_failed", "补译校验失败或原文版本已改变")
        raise


def register_translation_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    from researchgraph.app import Key, remember, remembered

    @app.post(
        "/api/v1/projects/{project_id}/graph/translate", response_model=JobView, status_code=202
    )
    def translate(project_id: str, body: TranslationRequest, idempotency_key: Key) -> JobView:
        with Session(engine()) as session, session.begin():
            request = {"project_id": project_id, **body.model_dump()}
            prior = remembered(session, "translation:" + idempotency_key, request)
            if prior:
                return JobView.model_validate(prior)
            snapshot, items = {}, []
            version_id = ""
            for index, node_id in enumerate(dict.fromkeys(body.node_ids)):
                node = session.get(KnowledgeNode, node_id)
                paper = session.get(Paper, node.paper_id) if node else None
                if not node or not paper or paper.project_id != project_id:
                    raise KnowledgeError("NODE_NOT_FOUND", "项目中不存在该知识")
                ref = f"node{index}"
                display = display_data(session, node)
                snapshot[ref] = {
                    "id": node.id,
                    "revision": node.revision,
                    "hash": digest(node.payload),
                    "display_hash": digest(display),
                }
                items.append(
                    {
                        "node_ref": ref,
                        "label_en": display["label_en"],
                        "summary_en": display["summary_en"],
                    }
                )
                version_id = node.document_version_id
            payload = {
                **body.model_dump(),
                "snapshot": snapshot,
                "items": items,
                "version_id": version_id,
            }
            if body.provider == "project":
                from researchgraph.model_settings import from_snapshot, snapshot_for

                profile = snapshot_for(session, project_id, "extraction")
                from_snapshot(profile, Path(str(engine().url.database)).parent, body.allow_network)
                payload["model_snapshot"] = profile
            job = Job(
                id=str(uuid4()),
                project_id=project_id,
                kind="translation_repair",
                payload=payload,
                status="queued",
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
            session.add(job)
            session.flush()
            result = JobView.model_validate(job)
            remember(session, "translation:" + idempotency_key, request, result.model_dump())
            return result
