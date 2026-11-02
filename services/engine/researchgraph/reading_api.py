"""Read all candidates; preferences change projections, never scientific content."""

from collections.abc import Callable
from typing import Any, Literal, cast
from uuid import uuid4

from fastapi import FastAPI, Query
from pydantic import Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.knowledge_api import Key
from researchgraph.knowledge_contracts import NodeView, StrictModel
from researchgraph.knowledge_models import KnowledgeNode
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import Job, Paper, now
from researchgraph.reading_models import CandidateMetadata
from researchgraph.schemas import JobView


class ReadingRebuild(StrictModel):
    document_version_id: str
    density: Literal["concise", "standard", "detailed"] = "standard"
    expected_revision: int = Field(ge=0)
    allow_network: bool = False


class ReadingPreferenceRequest(StrictModel):
    candidate_id: str
    expected_revision: int = Field(ge=1)
    action: Literal["include_core", "exclude_core", "reset_automatic"]
    reason: str = Field(default="用户显示偏好", min_length=1, max_length=500)


def register_reading_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    from researchgraph.app import remember, remembered

    @app.get("/api/v1/papers/{paper_id}/graph-selection")
    def selection(paper_id: str) -> dict[str, Any]:
        with Session(engine()) as session:
            if not session.get(Paper, paper_id):
                raise KnowledgeError("PAPER_NOT_FOUND", "论文不存在")
            current = KnowledgeStore(session).reading().current(paper_id)
            return (
                current.data
                if current
                else {
                    "selection_revision": 0,
                    "units": [],
                    "entries": [],
                    "build_state": "not_built",
                }
            )

    @app.get("/api/v1/papers/{paper_id}/knowledge-units")
    def units(paper_id: str) -> dict[str, Any]:
        data = selection(paper_id)
        return {"items": data["units"], "selection_revision": data["selection_revision"]}

    @app.get("/api/v1/papers/{paper_id}/candidates")
    def candidates(
        paper_id: str,
        search: str = Query("", max_length=160),
        cursor: str = Query("", max_length=300),
        limit: int = Query(40, ge=1, le=100),
    ) -> dict[str, Any]:
        with Session(engine()) as session:
            if not session.get(Paper, paper_id):
                raise KnowledgeError("PAPER_NOT_FOUND", "论文不存在")
            reading = KnowledgeStore(session).reading()
            current = reading.current(paper_id)
            query = select(KnowledgeNode).where(KnowledgeNode.paper_id == paper_id)
            rows = list(session.scalars(query.order_by(KnowledgeNode.id)))
            signature = digest(
                [
                    paper_id,
                    search,
                    [(n.id, n.revision) for n in rows],
                    current.revision if current else 0,
                ]
            )
            after = ""
            if cursor:
                parts = cursor.split(":", 1)
                if len(parts) != 2 or parts[0] != signature:
                    raise KnowledgeError("CURSOR_STALE", "候选快照已变化，请重新搜索")
                after = parts[1]
            roles = {e["candidate_id"]: e for e in current.data["entries"]} if current else {}
            rows = [
                n
                for n in rows
                if n.id > after
                and (not search or search.casefold() in (n.text + str(n.payload)).casefold())
            ]
            items = []
            for node in rows[:limit]:
                metadata = session.get(CandidateMetadata, node.id)
                items.append(
                    {
                        "node": NodeView.model_validate(node).model_dump(mode="json"),
                        "quality": metadata.quality if metadata else {},
                        "source_valid": reading.source_valid(node),
                        **roles.get(
                            node.id, {"graph_role": "retrieval_only", "reason": "尚未整合"}
                        ),
                    }
                )
            return {
                "items": items,
                "next_cursor": signature + ":" + rows[limit - 1].id if len(rows) > limit else None,
            }

    @app.post(
        "/api/v1/papers/{paper_id}/graph-selection/rebuild", response_model=JobView, status_code=202
    )
    def rebuild(paper_id: str, body: ReadingRebuild, idempotency_key: Key) -> JobView:
        with Session(engine()) as session, session.begin():
            reading = KnowledgeStore(session).reading()
            _, paper = reading.source(body.document_version_id)
            if paper.id != paper_id:
                raise KnowledgeError("SOURCE_MISMATCH", "论文与版本不匹配")
            request_data = {**body.model_dump(), "paper_id": paper_id}
            previous = remembered(session, "reading-rebuild:" + idempotency_key, request_data)
            if previous:
                return JobView.model_validate(previous)
            current = reading.current(paper_id)
            if (current.revision if current else 0) != body.expected_revision:
                raise KnowledgeError("SELECTION_REVISION_CONFLICT", "图谱已更新，请刷新")
            jid = str(uuid4())
            result: dict[str, Any] | None = None
            payload: dict[str, Any] = {
                "document_version_id": body.document_version_id,
                "density": body.density,
                "pipeline": "paper-reading-v1",
                "reading_only": True,
                "allow_network": body.allow_network,
                "provider": "project",
            }
            if (
                current
                and current.document_version_id == body.document_version_id
                and current.snapshot_hash == reading.snapshot(body.document_version_id)
            ):
                data = reading.publish(
                    version_id=body.document_version_id,
                    snapshot=current.snapshot_hash,
                    unit_ids=current.data["integration_unit_ids"],
                    proposal=current.data["selection_proposal"],
                    density=body.density,
                    expected_revision=current.revision,
                    key="reading-density:" + idempotency_key,
                )
                result = {
                    "selection_revision": data["selection_revision"],
                    "build_state": data["build_state"],
                }
            else:
                if not body.allow_network:
                    raise KnowledgeError(
                        "NETWORK_PERMISSION_REQUIRED", "首次整合需发送候选及必要证据到已配置模型"
                    )
                from researchgraph.model_settings import snapshot_for

                payload["model_snapshot"] = snapshot_for(session, paper.project_id, "extraction")
            job = Job(
                id=jid,
                kind="knowledge_extract",
                project_id=paper.project_id,
                payload=payload,
                status="succeeded" if result else "queued",
                stage="publishing" if result else "integrating",
                result=result,
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
            session.add(job)
            session.flush()
            response = JobView.model_validate(job)
            remember(
                session, "reading-rebuild:" + idempotency_key, request_data, response.model_dump()
            )
            return response

    @app.post("/api/v1/papers/{paper_id}/graph-selection/preferences")
    def preference(
        paper_id: str, body: ReadingPreferenceRequest, idempotency_key: Key
    ) -> dict[str, Any]:
        with Session(engine()) as session, session.begin():
            request_data = {**body.model_dump(), "paper_id": paper_id}
            previous = remembered(session, "reading-preference:" + idempotency_key, request_data)
            if previous:
                return previous
            reading = KnowledgeStore(session).reading()
            current = reading.current(paper_id)
            node = session.get(KnowledgeNode, body.candidate_id)
            if (
                not current
                or not node
                or node.paper_id != paper_id
                or node.document_version_id != current.document_version_id
            ):
                raise KnowledgeError("NODE_NOT_FOUND", "当前选择不存在该候选")
            if current.revision != body.expected_revision:
                raise KnowledgeError("SELECTION_REVISION_CONFLICT", "选择已变化，请刷新")
            if body.action == "include_core":
                metadata = session.get(CandidateMetadata, node.id)
                if (
                    node.kind != "claim"
                    or not reading.source_valid(node)
                    or not metadata
                    or metadata.quality.get("blocking_issues")
                    or metadata.canonical_id
                ):
                    raise KnowledgeError(
                        "BLOCKED_CORE_REASON", "该候选尚不满足来源、归属或证据门槛"
                    )
            reading.set_preference(node.id, body.action, body.reason)
            data = reading.publish(
                version_id=current.document_version_id,
                snapshot=current.snapshot_hash,
                unit_ids=current.data["integration_unit_ids"],
                proposal=current.data["selection_proposal"],
                density=current.data["density"],
                expected_revision=current.revision,
                key="reading-preference:" + idempotency_key,
            )
            KnowledgeStore(session).event(
                reading.source(current.document_version_id)[1].project_id,
                "graph.preference_changed",
                request_data,
            )
            remember(session, "reading-preference:" + idempotency_key, request_data, data)
            return cast(dict[str, Any], data)
