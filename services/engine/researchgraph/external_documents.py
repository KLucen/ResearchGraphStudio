"""Read-only files become explicitly attributed immutable sources, never inherited Wiki evidence."""

import hashlib
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.external_document_contracts import ExternalDocumentRegister
from researchgraph.external_document_models import ExternalDocumentVersion
from researchgraph.knowledge_models import AuthorizedRoot
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, text_hash
from researchgraph.models import Project, now
from researchgraph.query_documents import note_allowed, read_authorized_file
from researchgraph.query_models import (
    NoteUseGrant,
    QueryDocument,
    QueryDocumentVersion,
    QueryOperation,
    QueryPassage,
)


def _root(
    session: Session, project_id: str, root_id: str, include_personal: bool, purpose: str
) -> AuthorizedRoot:
    root = session.get(AuthorizedRoot, root_id)
    if not include_personal or not root or not note_allowed(session, root, project_id, purpose):
        raise KnowledgeError("EXTERNAL_SOURCE_NOT_AUTHORIZED", "外部资料未获本次用途的读取授权")
    return root


def preview_external_document(
    session: Session,
    project_id: str,
    root_id: str,
    relative_path: str,
    *,
    include_personal: bool = False,
) -> dict[str, Any]:
    root = _root(session, project_id, root_id, include_personal, "local")
    data, state = read_authorized_file(root, relative_path)
    if state != "available" or data is None:
        raise KnowledgeError(
            "EXTERNAL_FILE_UNAVAILABLE", "所选Markdown文件无法在授权目录内安全读取"
        )
    try:
        # Retaining the BOM, CRLF and every Unicode character makes UTF-8 re-encoding exact.
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise KnowledgeError(
            "EXTERNAL_FILE_ENCODING", "外部Markdown必须使用有效UTF-8编码"
        ) from error
    return {
        "root_id": root.id,
        "relative_path": relative_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "text": text,
        "source_verified": False,
        "file_state": "in_sync",
    }


def _snapshot(origin: ExternalDocumentVersion, text: str, document_id: str) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "root_id": origin.root_id,
        "relative_path": origin.relative_path,
        "sha256": origin.sha256,
        "title": origin.title,
        "attribution": origin.attribution,
        "text_sha256": text_hash(text),
        "policy": "external-document-1",
    }


def _version(
    session: Session, project_id: str, version_id: str
) -> tuple[QueryDocument, QueryDocumentVersion, ExternalDocumentVersion]:
    version = session.get(QueryDocumentVersion, version_id)
    origin = session.get(ExternalDocumentVersion, version_id)
    document = session.get(QueryDocument, version.document_id) if version else None
    if (
        not version
        or not origin
        or not document
        or document.project_id != project_id
        or document.kind != "external"
    ):
        raise KnowledgeError("EXTERNAL_DOCUMENT_NOT_FOUND", "当前项目中没有该外部文档版本")
    return document, version, origin


def _checked_snapshot(
    session: Session,
    document: QueryDocument,
    version: QueryDocumentVersion,
    origin: ExternalDocumentVersion,
) -> QueryPassage:
    paragraphs = list(
        session.scalars(select(QueryPassage).where(QueryPassage.version_id == version.id))
    )
    if (
        version.state != "saved"
        or len(paragraphs) != 1
        or paragraphs[0].ordinal != 0
        or paragraphs[0].local_ref != "external-body"
        or paragraphs[0].dependencies != []
        or paragraphs[0].caveats != []
        or paragraphs[0].attribution != origin.attribution
        or origin.attribution not in {"user_view", "external_source"}
        or paragraphs[0].sha256 != origin.sha256
        or text_hash(paragraphs[0].text) != origin.sha256
        or digest(_snapshot(origin, paragraphs[0].text, document.id)) != version.sha256
    ):
        raise KnowledgeError("EXTERNAL_SNAPSHOT_INVALID", "外部文档快照或来源归属完整性已变化")
    return paragraphs[0]


def validate_external_version(
    session: Session,
    project_id: str,
    version_id: str,
    *,
    include_personal: bool = False,
    purpose: str = "local",
) -> dict[str, Any]:
    document, version, origin = _version(session, project_id, version_id)
    root = _root(session, project_id, origin.root_id, include_personal, purpose)
    paragraph = _checked_snapshot(session, document, version, origin)
    data, state = read_authorized_file(root, origin.relative_path)
    current_hash = hashlib.sha256(data).hexdigest() if data is not None else None
    file_state = (
        "in_sync" if current_hash == origin.sha256 else "modified" if data is not None else state
    )
    grant = session.get(NoteUseGrant, root.id)
    authorization_revision = grant.revision if grant else 0
    source = {
        "source_kind": "external",
        "type": "external",
        "id": version.id,
        "document_id": document.id,
        "version_id": version.id,
        "root_id": root.id,
        "relative_path": origin.relative_path,
        "sha256": origin.sha256,
        "authorization_revision": authorization_revision,
        "attribution": origin.attribution,
        "source_verified": False,
    }
    return {
        **source,
        "title": origin.title,
        "revision": version.revision,
        "current_version_id": document.current_version_id,
        "text": paragraph.text,
        "content_state": "unverified",
        "snapshot_valid": True,
        "file_state": file_state,
        "current_sha256": current_hash,
        "roots": [source],
    }


def read_external_document(
    session: Session,
    project_id: str,
    document_id: str,
    version_id: str | None = None,
    *,
    include_personal: bool = False,
    purpose: str = "local",
    require_local: bool = False,
) -> dict[str, Any]:
    document = session.get(QueryDocument, document_id)
    if (
        not document
        or document.project_id != project_id
        or document.kind != "external"
        or not document.current_version_id
    ):
        raise KnowledgeError("EXTERNAL_DOCUMENT_NOT_FOUND", "当前项目中没有该外部文档")
    selected = version_id or document.current_version_id
    selected_document, _, _ = _version(session, project_id, selected)
    if selected_document.id != document.id:
        raise KnowledgeError("EXTERNAL_DOCUMENT_NOT_FOUND", "外部文档版本不属于所选文档")
    if require_local and purpose != "local":
        validate_external_version(
            session, project_id, selected, include_personal=include_personal, purpose="local"
        )
    result = validate_external_version(
        session, project_id, selected, include_personal=include_personal, purpose=purpose
    )
    versions = []
    for version in session.scalars(
        select(QueryDocumentVersion)
        .where(QueryDocumentVersion.document_id == document.id)
        .order_by(QueryDocumentVersion.revision.desc())
    ):
        try:
            if require_local and purpose != "local":
                validate_external_version(
                    session,
                    project_id,
                    version.id,
                    include_personal=include_personal,
                    purpose="local",
                )
            item = validate_external_version(
                session, project_id, version.id, include_personal=include_personal, purpose=purpose
            )
        except KnowledgeError:
            continue  # Do not leak historical titles from a different revoked reading root.
        versions.append(
            {k: item[k] for k in ("version_id", "revision", "sha256", "title", "attribution")}
        )
    return {**result, "versions": versions}


def list_external_documents(
    session: Session, project_id: str, *, include_personal: bool = False, purpose: str = "local"
) -> dict[str, Any]:
    if not session.get(Project, project_id):
        raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
    if not include_personal:
        return {"items": [], "total": 0}
    items = []
    for document in session.scalars(
        select(QueryDocument)
        .where(QueryDocument.project_id == project_id, QueryDocument.kind == "external")
        .order_by(QueryDocument.created_at.desc(), QueryDocument.id.desc())
    ):
        try:
            item = read_external_document(
                session, project_id, document.id, include_personal=True, purpose=purpose
            )
        except KnowledgeError:
            continue
        items.append(item)
    return {"items": items, "total": len(items)}


def lint_document_metadata(
    session: Session, project_id: str, include_personal: bool = False
) -> list[dict[str, Any]]:
    """Authorized metadata only, retaining missing/modified files for diagnostic selection."""
    if not include_personal:
        return []
    items = []
    for document in session.scalars(
        select(QueryDocument).where(
            QueryDocument.project_id == project_id, QueryDocument.kind == "external"
        )
    ):
        if not document.current_version_id:
            continue
        try:
            _, version, origin = _version(session, project_id, document.current_version_id)
            _root(session, project_id, origin.root_id, True, "local")
        except KnowledgeError:
            continue
        try:
            _checked_snapshot(session, document, version, origin)
            status, title = "unverified", origin.title
        except KnowledgeError:
            status, title = "invalid", "外部文档快照完整性异常"
        items.append(
            {
                "id": document.id,
                "title": title,
                "kind": "external",
                "status": status,
                "current_version_id": version.id,
                "latest_version_id": version.id,
            }
        )
    return items


def personal_external_sources(session: Session, project_id: str) -> list[dict[str, Any]]:
    """Each registered immutable version is an explicit personal-source selection candidate."""
    items = []
    for version_id in session.scalars(
        select(ExternalDocumentVersion.version_id)
        .join(QueryDocumentVersion, QueryDocumentVersion.id == ExternalDocumentVersion.version_id)
        .join(QueryDocument, QueryDocument.id == QueryDocumentVersion.document_id)
        .where(QueryDocument.project_id == project_id, QueryDocument.kind == "external")
        .order_by(QueryDocument.created_at.desc(), QueryDocumentVersion.revision.desc())
    ):
        try:
            item = validate_external_version(session, project_id, version_id, include_personal=True)
        except KnowledgeError:
            continue
        root = session.get(AuthorizedRoot, item["root_id"])
        assert root
        items.append(
            {
                **item,
                "type": "external",
                "label": item["title"],
                "allow_model": note_allowed(session, root, project_id, "model"),
            }
        )
    return items


class ExternalDocumentMutations:
    """Only this explicit Store transaction registers source snapshots; no file writer exists."""

    def __init__(self, store: KnowledgeStore):
        self.store, self.session = store, store.session

    def register(
        self,
        project_id: str,
        request: ExternalDocumentRegister | dict[str, Any],
        key: str,
        *,
        include_personal: bool = False,
    ) -> dict[str, Any]:
        body = ExternalDocumentRegister.model_validate(request)
        current = preview_external_document(
            self.session,
            project_id,
            body.root_id,
            body.relative_path,
            include_personal=include_personal,
        )
        if current["sha256"] != body.expected_sha256:
            raise KnowledgeError("EXTERNAL_FILE_CHANGED", "文件已在预览后变化，请重新预览再登记")
        payload = {"project_id": project_id, **body.model_dump()}
        op_key = f"external-document:{project_id}:{key}"
        previous = self.session.get(QueryOperation, op_key)
        if previous:
            if previous.request_hash != digest(payload):
                raise KnowledgeError("IDEMPOTENCY_CONFLICT", "登记标识已用于不同外部文档请求")
            result = read_external_document(
                self.session,
                project_id,
                previous.response["document_id"],
                previous.response["version_id"],
                include_personal=include_personal,
            )
            if result["file_state"] != "in_sync":
                raise KnowledgeError("EXTERNAL_FILE_CHANGED", "文件在登记重放期间变化，请重新预览")
            return result
        document = self.session.get(QueryDocument, body.document_id) if body.document_id else None
        if body.document_id and (
            not document or document.project_id != project_id or document.kind != "external"
        ):
            raise KnowledgeError("EXTERNAL_DOCUMENT_NOT_FOUND", "目标不是当前项目的独立外部文档")
        if document:
            if document.current_version_id != body.base_version_id:
                raise KnowledgeError("EXTERNAL_VERSION_CONFLICT", "外部文档当前保存版本已变化")
            # Refreshing a source cannot launder corrupt or revoked previous history.
            validate_external_version(
                self.session,
                project_id,
                body.base_version_id or "",
                include_personal=include_personal,
            )
        else:
            document = QueryDocument(
                id=str(uuid4()),
                project_id=project_id,
                kind="external",
                title=body.title,
                created_at=now(),
            )
            self.session.add(document)
            self.session.flush()
        origin = ExternalDocumentVersion(
            version_id=str(uuid4()),
            root_id=body.root_id,
            relative_path=body.relative_path,
            sha256=body.expected_sha256,
            title=body.title,
            attribution=body.attribution,
        )
        version = QueryDocumentVersion(
            id=origin.version_id,
            document_id=document.id,
            revision=(
                self.session.scalar(
                    select(QueryDocumentVersion.revision)
                    .where(QueryDocumentVersion.document_id == document.id)
                    .order_by(QueryDocumentVersion.revision.desc())
                    .limit(1)
                )
                or 0
            )
            + 1,
            state="saved",
            sha256=digest(_snapshot(origin, current["text"], document.id)),
            created_at=now(),
        )
        self.session.add(version)
        self.session.flush()
        self.session.add(origin)
        self.session.add(
            QueryPassage(
                id=str(uuid4()),
                version_id=version.id,
                ordinal=0,
                local_ref="external-body",
                text=current["text"],
                sha256=body.expected_sha256,
                attribution=body.attribution,
                dependencies=[],
                caveats=[],
            )
        )
        self.session.flush()
        # This only records exact bytes in a read-authorized root; it grants no write rights.
        self.store.query().register_file(
            document.id, body.root_id, body.relative_path, version.id, body.expected_sha256
        )
        document.current_version_id, document.title = version.id, body.title
        result = {"document_id": document.id, "version_id": version.id}
        self.session.add(QueryOperation(key=op_key, request_hash=digest(payload), response=result))
        self.store.audit_event(
            project_id,
            "EXTERNAL_DOCUMENT_REGISTERED",
            {**result, "root_id": body.root_id, "sha256": body.expected_sha256},
            actor="user",
            trigger="external_document_registration",
        )
        self.session.flush()
        result = read_external_document(
            self.session, project_id, document.id, version.id, include_personal=include_personal
        )
        if result["file_state"] != "in_sync":
            raise KnowledgeError("EXTERNAL_FILE_CHANGED", "文件在登记期间变化，请重新预览")
        return result
