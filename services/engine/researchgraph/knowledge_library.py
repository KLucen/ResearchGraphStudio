"""Library transactions and source adapters; this module never calls a model."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, cast
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.core import digest, stable_id
from researchgraph.knowledge_library_contracts import (
    CollectionView,
    CollectOverview,
    KnowledgeVersionView,
    LibraryPaperView,
    LibrarySettings,
    LibrarySourceLinkView,
    LibraryView,
)
from researchgraph.knowledge_library_models import (
    KnowledgeCollection,
    KnowledgeCollectionMember,
    KnowledgeLibrary,
    LibraryPaper,
    LibraryPaperSourceLink,
    PaperKnowledgeVersion,
)
from researchgraph.models import AttachmentRevision, Paper, ZoteroLink, now

PERSONAL_LIBRARY_ID = "personal"


def library_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def ensure_library(db: Session) -> KnowledgeLibrary:
    library = db.get(KnowledgeLibrary, PERSONAL_LIBRARY_ID)
    if library is None:
        library = KnowledgeLibrary(
            id=PERSONAL_LIBRARY_ID,
            name="个人研究知识库",
            settings_json=LibrarySettings().model_dump(),
            created_at=now(),
            updated_at=now(),
        )
        db.add(library)
        db.flush()
    return library


def library_view(library: KnowledgeLibrary | None) -> LibraryView:
    return LibraryView(
        id=PERSONAL_LIBRARY_ID,
        name=library.name if library else "个人研究知识库",
        settings=LibrarySettings.model_validate(library.settings_json if library else {}),
        created_at=library.created_at if library else "",
        updated_at=library.updated_at if library else "",
    )


def reliable_paper_keys(db: Session, paper: Paper) -> set[str]:
    keys: set[str] = set()
    for link in db.scalars(select(ZoteroLink).where(ZoteroLink.paper_id == paper.id)):
        # Attachment identity preserves distinct versions of the same item.
        keys.add(f"zotero:{link.library_id}:{link.item_key}:{link.attachment_key}")
    for revision in db.scalars(
        select(AttachmentRevision).where(AttachmentRevision.paper_id == paper.id)
    ):
        if len(revision.sha256) == 64 and all(
            c in "0123456789abcdefABCDEF" for c in revision.sha256
        ):
            keys.add("sha256:" + revision.sha256.lower())
    return keys


def ensure_library_paper(db: Session, paper: Paper) -> LibraryPaper:
    ensure_library(db)
    existing_link = db.scalar(
        select(LibraryPaperSourceLink).where(LibraryPaperSourceLink.original_paper_id == paper.id)
    )
    keys = reliable_paper_keys(db, paper)
    library_paper = db.get(LibraryPaper, existing_link.library_paper_id) if existing_link else None
    if library_paper is None and keys:
        matches = [
            candidate
            for candidate in db.scalars(
                select(LibraryPaper).where(LibraryPaper.library_id == PERSONAL_LIBRARY_ID)
            )
            if keys.intersection(candidate.identity_keys)
        ]
        if len(matches) > 1:
            raise library_error(
                409, "LIBRARY_IDENTITY_CONFLICT", "文献身份对应多个知识条目，请先核对来源"
            )
        library_paper = matches[0] if matches else None
    if library_paper is None:
        library_paper = LibraryPaper(
            id=str(uuid4()),
            library_id=PERSONAL_LIBRARY_ID,
            title=paper.title,
            identity_keys=sorted(keys),
            note="",
            archived=False,
            created_at=now(),
            updated_at=now(),
        )
        db.add(library_paper)
        db.flush()
    else:
        library_paper.identity_keys = sorted(set(library_paper.identity_keys) | keys)
    if existing_link is None:
        db.add(
            LibraryPaperSourceLink(
                id=str(uuid4()),
                library_paper_id=library_paper.id,
                paper_id=paper.id,
                original_paper_id=paper.id,
                project_id=paper.project_id,
                created_at=now(),
            )
        )
    else:
        existing_link.paper_id = paper.id
    db.flush()
    return library_paper


def publish_version(
    db: Session,
    *,
    paper_id: str,
    source_kind: str,
    source_id: str,
    source_fingerprint: str,
    content_json: dict[str, Any],
    source_snapshot_json: dict[str, Any],
    evidence_status: Literal["legacy", "grounded"] = "grounded",
    provider_id: str | None = None,
    model_id: str | None = None,
    job_id: str | None = None,
    prompt_version: str = "",
    schema_version: str = "paper-knowledge-1",
) -> PaperKnowledgeVersion:
    """Publish a caller-validated immutable snapshot in the caller's transaction.

    Exact semantic/source replays reuse the same version, independent of a new
    job ID. Selecting a result never mutates an existing version's JSON.
    """
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise library_error(404, "PAPER_NOT_FOUND", "论文不存在")
    if source_kind not in {"local_revision", "model_parse", "legacy_overview"}:
        raise ValueError("Unknown library source kind")
    library_paper = ensure_library_paper(db, paper)
    snapshot_hash = digest(
        {
            "source_kind": source_kind,
            "source_id": source_id,
            "source_fingerprint": source_fingerprint,
            "schema_version": schema_version,
            "evidence_status": evidence_status,
            "content": content_json,
            "source_snapshot": source_snapshot_json,
        }
    )
    version = db.scalar(
        select(PaperKnowledgeVersion).where(
            PaperKnowledgeVersion.library_paper_id == library_paper.id,
            PaperKnowledgeVersion.snapshot_hash == snapshot_hash,
        )
    )
    if version is None:
        version = PaperKnowledgeVersion(
            id=str(uuid4()),
            library_paper_id=library_paper.id,
            source_kind=source_kind,
            source_id=source_id,
            source_paper_id=paper.id,
            project_id=paper.project_id,
            source_fingerprint=source_fingerprint,
            snapshot_hash=snapshot_hash,
            schema_version=schema_version,
            evidence_status=evidence_status,
            content_json=deepcopy(content_json),
            source_snapshot_json=deepcopy(source_snapshot_json),
            provider_id=provider_id,
            model_id=model_id,
            job_id=job_id,
            prompt_version=prompt_version,
            created_at=now(),
        )
        db.add(version)
        db.flush()
    library_paper.current_version_id = version.id
    library_paper.updated_at = now()
    return version


def version_view(version: PaperKnowledgeVersion) -> KnowledgeVersionView:
    return KnowledgeVersionView(
        id=version.id,
        library_paper_id=version.library_paper_id,
        source_kind=version.source_kind,
        source_id=version.source_id,
        source_paper_id=version.source_paper_id,
        project_id=version.project_id,
        source_fingerprint=version.source_fingerprint,
        snapshot_hash=version.snapshot_hash,
        schema_version=version.schema_version,
        evidence_status=cast(Literal["legacy", "grounded"], version.evidence_status),
        content=deepcopy(version.content_json),
        provider_id=version.provider_id,
        model_id=version.model_id,
        job_id=version.job_id,
        created_at=version.created_at,
    )


def paper_view(db: Session, paper: LibraryPaper) -> LibraryPaperView:
    versions = list(
        db.scalars(
            select(PaperKnowledgeVersion)
            .where(PaperKnowledgeVersion.library_paper_id == paper.id)
            .order_by(PaperKnowledgeVersion.created_at.desc(), PaperKnowledgeVersion.id.desc())
        )
    )
    views = [version_view(version) for version in versions]
    links = list(
        db.scalars(
            select(LibraryPaperSourceLink)
            .where(LibraryPaperSourceLink.library_paper_id == paper.id)
            .order_by(LibraryPaperSourceLink.created_at, LibraryPaperSourceLink.id)
        )
    )
    return LibraryPaperView(
        id=paper.id,
        title=paper.title,
        note=paper.note,
        archived=paper.archived,
        project_ids=sorted({link.project_id for link in links}),
        source_links=[
            LibrarySourceLinkView(
                paper_id=link.paper_id,
                original_paper_id=link.original_paper_id,
                project_id=link.project_id,
                source_available=bool(link.paper_id and db.get(Paper, link.paper_id)),
            )
            for link in links
        ],
        collection_ids=list(
            db.scalars(
                select(KnowledgeCollectionMember.collection_id)
                .where(KnowledgeCollectionMember.library_paper_id == paper.id)
                .order_by(KnowledgeCollectionMember.collection_id)
            )
        ),
        current_version=next((view for view in views if view.id == paper.current_version_id), None),
        versions=views,
        created_at=paper.created_at,
        updated_at=paper.updated_at,
    )


def collection_view(collection: KnowledgeCollection) -> CollectionView:
    return CollectionView(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        created_at=collection.created_at,
    )


def _rooted_legacy(content: dict[str, Any], paper: Paper) -> dict[str, Any]:
    result = deepcopy(content)
    graph = result["graph"]
    root_id = stable_id("library-paper-root", paper.id)
    graph["nodes"].insert(
        0,
        {
            "id": root_id,
            "type": "PAPER",
            "label_zh": paper.title,
            "label_en": None,
            "description_zh": "历史概览快照，未提供逐项原文定位。",
            "basis": "EXPLICIT",
            "source_refs": [],
        },
    )
    graph["edges"].extend(
        {
            "id": stable_id("library-root-edge", root_id + "/" + node["id"]),
            "source": root_id,
            "target": node["id"],
            "type": "HAS_KNOWLEDGE",
            "basis": "EXPLICIT",
            "source_refs": [],
        }
        for node in graph["nodes"][1:]
    )
    result["coverage"] = {
        "status": "legacy_unanchored",
        "warnings": ["旧图只用于概览导航；没有逐项原文定位，不作为强关联依据。"],
    }
    result["sources"] = []
    return result


def collect_overview(db: Session, request: CollectOverview) -> LibraryPaper:
    from researchgraph.model_document_models import LlmDocumentOutput, LlmDocumentParse
    from researchgraph.model_document_overview import model_document_paper, validate_model_overview
    from researchgraph.paper_overview_models import PaperOverviewResult

    paper = db.get(Paper, request.paper_id)
    if paper is None:
        raise library_error(404, "PAPER_NOT_FOUND", "论文不存在")
    provider_id: str | None
    model_id: str | None
    if request.source_kind == "local_revision":
        revision = db.get(AttachmentRevision, request.source_id)
        if revision is None or revision.paper_id != paper.id:
            raise library_error(409, "KNOWLEDGE_SOURCE_MISMATCH", "解析来源不属于该论文")
        query = select(PaperOverviewResult).where(
            PaperOverviewResult.paper_id == paper.id,
            PaperOverviewResult.document_version_id == revision.id,
            PaperOverviewResult.status == "COMPLETED",
        )
        if request.overview_result_id:
            query = query.where(PaperOverviewResult.id == request.overview_result_id)
        result = db.scalar(query.order_by(PaperOverviewResult.created_at.desc()).limit(1))
        if result is None or result.paper_card_json is None or result.graph_json is None:
            raise library_error(409, "OVERVIEW_NOT_READY", "尚无可收藏的成功概览")
        if result.pdf_hash != revision.sha256 or result.project_id != paper.project_id:
            raise library_error(409, "KNOWLEDGE_SOURCE_CHANGED", "概览与当前解析来源不一致")
        try:
            content = validate_model_overview(
                {
                    "schema_version": result.schema_version,
                    "paper_card": result.paper_card_json,
                    "graph": result.graph_json,
                },
                paper.id,
            )
        except ValueError as exc:
            raise library_error(
                409, "KNOWLEDGE_SOURCE_INVALID", "历史概览未通过内容或来源校验"
            ) from exc
        source_fingerprint = digest(
            {"revision": revision.id, "sha256": revision.sha256, "input_hash": result.input_hash}
        )
        provider_id, model_id, prompt_version = (
            result.provider_id,
            result.model_id,
            result.prompt_version,
        )
        result_id = result.id
    else:
        parse = db.get(LlmDocumentParse, request.source_id)
        owner = model_document_paper(db, parse) if parse else None
        if parse is None or owner is None or owner.id != paper.id or parse.status != "succeeded":
            raise library_error(409, "KNOWLEDGE_SOURCE_MISMATCH", "模型解析来源不属于该论文")
        model_query = select(LlmDocumentOutput).where(
            LlmDocumentOutput.parse_id == parse.id,
            LlmDocumentOutput.item_kind == "paper_overview",
            LlmDocumentOutput.status == "succeeded",
        )
        if request.overview_result_id:
            model_query = model_query.where(LlmDocumentOutput.id == request.overview_result_id)
        output = db.scalar(model_query.order_by(LlmDocumentOutput.created_at.desc()).limit(1))
        if output is None or output.output_json is None:
            raise library_error(409, "OVERVIEW_NOT_READY", "尚无可收藏的成功概览")
        if output.import_session_id != parse.import_session_id:
            raise library_error(409, "KNOWLEDGE_SOURCE_MISMATCH", "概览与模型解析任务不一致")
        recorded_update = (output.usage or {}).get("source_updated_at")
        if recorded_update and recorded_update != parse.updated_at:
            raise library_error(
                409, "KNOWLEDGE_SOURCE_CHANGED", "模型解析已更新，旧概览不能作为当前收藏"
            )
        try:
            content = validate_model_overview(output.output_json, paper.id)
        except ValueError as exc:
            raise library_error(
                409, "KNOWLEDGE_SOURCE_INVALID", "历史概览未通过内容或来源校验"
            ) from exc
        source_fingerprint = digest(
            {"parse": parse.id, "updated_at": parse.updated_at, "output": output.id}
        )
        provider_id, model_id, prompt_version = (
            output.provider_id,
            output.model_id,
            "paper_overview_with_light_graph_v1",
        )
        result_id = output.id
    library_paper = ensure_library_paper(db, paper)
    version = publish_version(
        db,
        paper_id=paper.id,
        source_kind="legacy_overview",
        source_id=result_id,
        source_fingerprint=source_fingerprint,
        content_json=_rooted_legacy(content, paper),
        source_snapshot_json={
            "source_kind": request.source_kind,
            "source_id": request.source_id,
            "overview_result_id": result_id,
            "title": paper.title,
        },
        evidence_status="legacy",
        provider_id=provider_id,
        model_id=model_id,
        prompt_version=prompt_version,
        schema_version="paper_overview_graph.v1",
    )
    library_paper.current_version_id = version.id
    db.flush()
    return library_paper
