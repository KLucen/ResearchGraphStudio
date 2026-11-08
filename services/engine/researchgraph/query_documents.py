"""Versioned document adapter. Reading files never publishes or mutates scientific knowledge."""

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from researchgraph.integrations import file_identity, safe_root, unsafe_path, verify_open_note
from researchgraph.knowledge_models import (
    AuthorizedRoot,
    EvidenceSpan,
    KnowledgeNode,
    NodeEvidence,
    NoteSnapshot,
)
from researchgraph.knowledge_store import (
    KnowledgeError,
    KnowledgeStore,
    digest,
    text_hash,
    validate_evidence,
)
from researchgraph.models import AttachmentRevision, Chunk, Paper, Project, now
from researchgraph.query_contracts import DocumentSaveRequest, QueryDependency
from researchgraph.query_models import (
    NoteUseGrant,
    QueryDocument,
    QueryDocumentVersion,
    QueryFileBinding,
    QueryOperation,
    QueryPassage,
)
from researchgraph.query_saved_lifecycle import saved_passage_states


def note_allowed(session: Session, root: AuthorizedRoot, project_id: str, purpose: str) -> bool:
    if not root.active or root.project_id != project_id or purpose not in {"local", "model"}:
        return False
    grant = session.get(NoteUseGrant, root.id)
    # Existing directory authorization permits local reading, never model transmission.
    return bool(
        grant.allow_model
        if purpose == "model" and grant
        else grant.allow_local
        if purpose == "local" and grant
        else purpose == "local"
    )


def read_authorized_file(root: AuthorizedRoot, relative_path: str) -> tuple[bytes | None, str]:
    """Read through the existing handle boundary checker; no path registration grants writes."""
    relative = PurePosixPath(relative_path)
    if (
        not root.active
        or relative.is_absolute()
        or ".." in relative.parts
        or "\\" in relative_path
        or not relative.parts
        or relative.suffix.lower() != ".md"
        or any(":" in part for part in relative.parts)
    ):
        return None, "unavailable"
    try:
        boundary = safe_root(Path(root.path))
        path = boundary.joinpath(*relative.parts)
        if not path.exists():
            return None, "missing"
        if any(unsafe_path(p) for p in (path, *path.parents) if p.is_relative_to(boundary)):
            return None, "unavailable"
        before = path.stat()
        with path.open("rb") as stream:
            verify_open_note(stream, boundary)
            data = stream.read(1_000_001)
        after = path.stat()
        if (
            len(data) > 1_000_000
            or file_identity(before) != file_identity(after)
            or unsafe_path(path)
        ):
            return None, "unavailable"
        return data, "available"
    except FileNotFoundError:
        return None, "missing"
    except (KnowledgeError, OSError, ValueError):
        return None, "unavailable"


def read_notes(
    session: Session,
    project_id: str,
    include_personal: bool = False,
    purpose: str = "local",
    selected_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if not include_personal:
        return []
    result = []
    for root in session.scalars(
        select(AuthorizedRoot).where(AuthorizedRoot.project_id == project_id)
    ):
        if not note_allowed(session, root, project_id, purpose):
            continue
        notes = list(
            session.scalars(
                select(NoteSnapshot)
                .where(NoteSnapshot.root_id == root.id)
                .order_by(NoteSnapshot.created_at.desc(), NoteSnapshot.id.desc())
            )
        )
        if selected_ids is not None:
            notes = [n for n in notes if n.id in selected_ids]
        by_path: dict[str, list[NoteSnapshot]] = {}
        for note in notes:
            by_path.setdefault(note.relative_path, []).append(note)
        for path, snapshots in by_path.items():
            data, state = read_authorized_file(root, path)
            if state != "available" or data is None:
                continue
            try:
                decoded = data.decode("utf-8-sig")
            except UnicodeError:
                continue
            fingerprint = hashlib.sha256(data).hexdigest()
            match = next(
                (n for n in snapshots if n.sha256 == fingerprint and n.text == decoded), None
            )
            if match is None:
                continue
            note = match
            grant = session.get(NoteUseGrant, root.id)
            result.append(
                {
                    "id": note.id,
                    "root_id": root.id,
                    "text": note.text,
                    "sha256": note.sha256,
                    "relative_path": note.relative_path,
                    "file_state": "in_sync",
                    "attribution": "user_view",
                    "authorization_revision": grant.revision if grant else 0,
                }
            )
    return result


def _paper_root(session: Session, version_id: str, project_id: str) -> tuple[dict[str, Any], bool]:
    version = session.get(AttachmentRevision, version_id)
    paper = session.get(Paper, version.paper_id) if version else None
    if not version or not paper or paper.project_id != project_id:
        raise KnowledgeError("QUERY_SCOPE_INVALID", "来源不属于当前项目")
    latest = session.scalar(
        select(AttachmentRevision.id)
        .where(AttachmentRevision.paper_id == paper.id)
        .order_by(AttachmentRevision.created_at.desc(), AttachmentRevision.id.desc())
        .limit(1)
    )
    return {
        "source_kind": "paper",
        "paper_id": paper.id,
        "document_version_id": version.id,
        "source_sha256": version.sha256,
    }, latest != version.id


def validate_dependencies(
    session: Session,
    project_id: str,
    dependencies: list[dict[str, Any]],
    include_personal: bool = False,
    purpose: str = "local",
    visited: set[str] | None = None,
    _eligible: dict[str, set[str]] | None = None,
    _saved: dict[tuple[str, str], dict[str, Any]] | None = None,
    _wiki: dict[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Recompute current eligibility and transitive roots; never trust cached document status."""
    roots: list[dict[str, Any]] = []
    issues: list[str] = []
    states: set[str] = set()
    trail = set(visited or ())
    eligible = _eligible if _eligible is not None else {}
    saved_states = _saved
    wiki_states = _wiki if _wiki is not None else {}
    if not dependencies:
        return {"content_state": "unverified", "roots": [], "issues": ["NO_DEPENDENCIES"]}
    for raw in dependencies:
        try:
            dep = QueryDependency.model_validate(raw)
            key = f"{dep.type}:{dep.id}"
            if key in trail:
                raise KnowledgeError("QUERY_DEPENDENCY_CYCLE", "文档依赖存在循环")
            nested_trail = trail | {key}
            if dep.type in {"chunk", "evidence", "node"}:
                if dep.type == "chunk":
                    chunk = session.get(Chunk, dep.id)
                    if chunk is None:
                        raise KnowledgeError("QUERY_SOURCE_MISSING", "原文块不存在")
                    root, stale = _paper_root(session, chunk.revision_id, project_id)
                    if (
                        text_hash(chunk.text) != dep.sha256
                        or dep.start is None
                        or dep.end is None
                        or dep.end > len(chunk.text)
                        or chunk.text[dep.start : dep.end] != dep.quote
                    ):
                        raise KnowledgeError("QUERY_ANCHOR_INVALID", "原文片段或哈希不匹配")
                    roots.append({**root, **dep.model_dump(exclude_none=True)})
                elif dep.type == "evidence":
                    evidence = session.get(EvidenceSpan, dep.id)
                    if evidence is None:
                        raise KnowledgeError("QUERY_SOURCE_MISSING", "证据不存在")
                    root, stale = _paper_root(session, evidence.document_version_id, project_id)
                    validate_evidence(session, evidence, evidence.document_version_id)
                    if evidence.text_sha256 != dep.sha256:
                        raise KnowledgeError("QUERY_ANCHOR_INVALID", "证据哈希不匹配")
                    roots.append(
                        {
                            **root,
                            **dep.model_dump(exclude_none=True),
                            "chunk_id": evidence.paragraph_id,
                            "start": evidence.start_offset,
                            "end": evidence.end_offset,
                            "quote": evidence.quote,
                        }
                    )
                else:
                    node = session.get(KnowledgeNode, dep.id)
                    if node is None:
                        raise KnowledgeError("QUERY_SOURCE_MISSING", "知识不存在")
                    _, stale = _paper_root(session, node.document_version_id, project_id)
                    from researchgraph.query_graph import eligible_nodes

                    if node.paper_id not in eligible:
                        eligible[node.paper_id] = {
                            n.id for n in eligible_nodes(session, project_id, [node.paper_id])
                        }
                    if node.id not in eligible[node.paper_id]:
                        raise KnowledgeError("QUERY_SOURCE_INVALID", "知识候选范围或验证状态不可用")
                    if node.revision != dep.revision:
                        states.add("stale")
                        issues.append("KNOWLEDGE_REVISION_CHANGED")
                    if dep.payload_sha256 is not None and dep.payload_sha256 != digest(
                        node.payload
                    ):
                        raise KnowledgeError("QUERY_PAYLOAD_CHANGED", "知识语义字段哈希不匹配")
                    if dep.sha256 is not None and dep.sha256 != text_hash(node.text):
                        raise KnowledgeError("QUERY_ANCHOR_INVALID", "知识文本哈希不匹配")
                    if node.source_status not in {
                        "source_verified",
                        "anchored",
                    } or node.review_status in {"rejected", "superseded"}:
                        raise KnowledgeError("QUERY_SOURCE_INVALID", "知识来源或状态不可用")
                    evidence_ids = list(
                        session.scalars(
                            select(NodeEvidence.evidence_id).where(NodeEvidence.node_id == node.id)
                        )
                    )
                    if not evidence_ids:
                        raise KnowledgeError("QUERY_SOURCE_INVALID", "知识缺少根证据")
                    for eid in evidence_ids:
                        evidence = session.get(EvidenceSpan, eid)
                        if not evidence or evidence.document_version_id != node.document_version_id:
                            raise KnowledgeError("QUERY_SOURCE_INVALID", "知识证据归属不匹配")
                        child = validate_dependencies(
                            session,
                            project_id,
                            [{"type": "evidence", "id": eid, "sha256": evidence.text_sha256}],
                            include_personal,
                            purpose,
                            nested_trail,
                            eligible,
                            saved_states,
                            wiki_states,
                        )
                        states.add(child["content_state"])
                        roots.extend(child["roots"])
                        issues.extend(child["issues"])
                states.add("stale" if stale else "valid")
                if stale:
                    issues.append("DOCUMENT_VERSION_CHANGED")
            elif dep.type == "note":
                note = session.get(NoteSnapshot, dep.id)
                note_root = session.get(AuthorizedRoot, note.root_id) if note else None
                if (
                    not note
                    or not note_root
                    or not include_personal
                    or not note_allowed(session, note_root, project_id, purpose)
                ):
                    raise KnowledgeError("QUERY_NOTE_NOT_AUTHORIZED", "个人资料未获本次用途授权")
                encoded = note.text.encode("utf-8")
                if note.sha256 != dep.sha256 or note.sha256 not in {
                    hashlib.sha256(encoded).hexdigest(),
                    hashlib.sha256(b"\xef\xbb\xbf" + encoded).hexdigest(),
                }:
                    raise KnowledgeError("QUERY_ANCHOR_INVALID", "笔记快照哈希不匹配")
                grant = session.get(NoteUseGrant, note_root.id)
                roots.append(
                    {
                        "source_kind": "note",
                        **dep.model_dump(exclude_none=True),
                        "root_id": note_root.id,
                        "relative_path": note.relative_path,
                        "authorization_revision": grant.revision if grant else 0,
                    }
                )
                states.add("valid")
            elif dep.type in {"annotation", "external"}:
                if not include_personal:
                    raise KnowledgeError(
                        "QUERY_PERSONAL_NOT_AUTHORIZED", "个人资料未获本次用途授权"
                    )
                if dep.type == "annotation":
                    from researchgraph.p5_personal import annotation_source

                    source = annotation_source(session, project_id, dep.id, purpose=purpose)
                    root = {k: v for k, v in source.items() if k != "text"}
                else:
                    from researchgraph.external_documents import validate_external_version

                    source = validate_external_version(
                        session, project_id, dep.id, include_personal=True, purpose=purpose
                    )
                    if not source.get("snapshot_valid"):
                        raise KnowledgeError("QUERY_EXTERNAL_INVALID", "外部文档快照不可用")
                    root = source["roots"][0]
                if source["sha256"] != dep.sha256:
                    raise KnowledgeError("QUERY_ANCHOR_INVALID", "个人资料快照哈希不匹配")
                roots.append({**root, **dep.model_dump(exclude_none=True)})
                states.add("valid")  # Personal snapshot identity, never scientific truth.
            else:
                passage = session.get(QueryPassage, dep.id)
                version = session.get(QueryDocumentVersion, passage.version_id) if passage else None
                document = session.get(QueryDocument, version.document_id) if version else None
                if not passage or not version or not document or document.project_id != project_id:
                    raise KnowledgeError("QUERY_SCOPE_INVALID", "文档段落不属于当前项目")
                if version.state != "saved":
                    raise KnowledgeError("QUERY_DOCUMENT_UNSAVED", "草稿不能作为科学依据")
                if saved_states is None:
                    saved_states = saved_passage_states(session, project_id)
                lifecycle = saved_states.get((document.id, passage.local_ref), {})
                if lifecycle.get("removed"):
                    raise KnowledgeError("QUERY_SAVED_REMOVED", "引用的阅读知识已从已保存内容移除")
                if lifecycle.get("lineage_issue"):
                    raise KnowledgeError(
                        lifecycle["lineage_issue"], "阅读知识的原始保存谱系无法核验"
                    )
                if passage.sha256 != dep.sha256 or text_hash(passage.text) != passage.sha256:
                    raise KnowledgeError("QUERY_ANCHOR_INVALID", "文档段落哈希不匹配")
                child = validate_dependencies(
                    session,
                    project_id,
                    [*passage.dependencies, *lifecycle.get("lineage_dependencies", [])],
                    include_personal,
                    purpose,
                    nested_trail,
                    eligible,
                    saved_states,
                    wiki_states,
                )
                from researchgraph.wiki_store import wiki_passage_state, wiki_version_state

                if version.id not in wiki_states:
                    wiki_states[version.id] = wiki_version_state(session, version.id)
                wiki_state = wiki_passage_state(session, passage.id)
                if wiki_states[version.id]:
                    wiki_state = wiki_states[version.id]
                if wiki_state:
                    states.add(wiki_state["content_state"])
                    issues.extend(wiki_state["issues"])
                roots.extend(child["roots"])
                issues.extend(child["issues"])
                states.add(child["content_state"])
        except (KnowledgeError, ValidationError) as error:
            states.add("invalid")
            issues.append(
                error.code
                if isinstance(error, KnowledgeError)
                else "QUERY_DEPENDENCY_SCHEMA_INVALID"
            )
    state = next(
        (s for s in ("invalid", "stale", "unverified", "valid") if s in states), "unverified"
    )
    unique = {digest(r): r for r in roots}
    return {
        "content_state": state,
        "roots": [unique[k] for k in sorted(unique)],
        "issues": sorted(set(issues)),
    }


def file_state(session: Session, document: QueryDocument) -> str:
    from researchgraph.wiki_models import WikiPage

    if session.get(WikiPage, document.id):
        from researchgraph.wiki_publish import file_status

        return str(file_status(session, document.project_id, document.id)["state"])
    binding = session.get(QueryFileBinding, document.id)
    if not binding:
        return "not_exported"
    root = session.get(AuthorizedRoot, binding.root_id)
    if not root or not note_allowed(session, root, document.project_id, "local"):
        return "unavailable"
    if binding.conflict:
        return "conflict"
    if binding.version_id != document.current_version_id:
        return "conflict"
    data, state = read_authorized_file(root, binding.relative_path)
    if state != "available" or data is None:
        return state
    return "in_sync" if hashlib.sha256(data).hexdigest() == binding.sha256 else "modified"


def read_passages(
    session: Session, project_id: str, include_personal: bool = False, purpose: str = "local"
) -> list[dict[str, Any]]:
    result = []
    saved_states = saved_passage_states(session, project_id)
    wiki_states: dict[str, dict[str, Any] | None] = {}
    for document in session.scalars(
        select(QueryDocument)
        .where(QueryDocument.project_id == project_id)
        .order_by(QueryDocument.id)
    ):
        if document.kind == "external":
            continue  # External text has an independent explicit-version read/selection API.
        version = (
            session.get(QueryDocumentVersion, document.current_version_id)
            if document.current_version_id
            else None
        )
        if not version or version.state != "saved" or version.document_id != document.id:
            continue
        from researchgraph.wiki_store import wiki_version_state

        snapshot_state = wiki_version_state(session, version.id)
        wiki_states[version.id] = snapshot_state
        state: str | None = None
        for passage in session.scalars(
            select(QueryPassage)
            .where(QueryPassage.version_id == version.id)
            .order_by(QueryPassage.ordinal)
        ):
            lifecycle = saved_states.get((document.id, passage.local_ref), {})
            if lifecycle.get("removed"):
                continue
            if passage.attribution == "user_view" and not include_personal:
                continue
            checked = validate_dependencies(
                session,
                project_id,
                [*passage.dependencies, *lifecycle.get("lineage_dependencies", [])],
                include_personal,
                purpose,
                {f"passage:{passage.id}"},
                _saved=saved_states,
                _wiki=wiki_states,
            )
            if any("NOT_AUTHORIZED" in issue for issue in checked["issues"]):
                continue  # Do not expose unauthorized text indirectly via a document.
            if text_hash(passage.text) != passage.sha256:
                checked = {
                    **checked,
                    "content_state": "invalid",
                    "issues": [*checked["issues"], "QUERY_ANCHOR_INVALID"],
                }
            if lifecycle.get("lineage_issue"):
                checked = {
                    **checked,
                    "content_state": "invalid",
                    "issues": [*checked["issues"], lifecycle["lineage_issue"]],
                }
            from researchgraph.wiki_store import wiki_passage_state

            wiki_state = wiki_passage_state(session, passage.id)
            if snapshot_state:
                wiki_state = snapshot_state
            if wiki_state:
                checked = {
                    **checked,
                    "content_state": (
                        "invalid"
                        if "invalid" in {checked["content_state"], wiki_state["content_state"]}
                        else "stale"
                    ),
                    "issues": [*checked["issues"], *wiki_state["issues"]],
                }
            if state is None:
                state = file_state(session, document)
            result.append(
                {
                    "id": passage.id,
                    "document_id": document.id,
                    "version_id": version.id,
                    "revision": version.revision,
                    "kind": document.kind,
                    "title": document.title,
                    "state": version.state,
                    "text": passage.text if checked["content_state"] == "valid" else "",
                    "sha256": passage.sha256,
                    "attribution": passage.attribution,
                    "file_state": state,
                    "dependencies": passage.dependencies,
                    "caveats": passage.caveats if checked["content_state"] == "valid" else [],
                    **checked,
                }
            )
    return result


class QueryMutations:
    """All document registration uses the shared Store transaction, never a file writer."""

    def __init__(self, store: KnowledgeStore):
        self.store, self.session = store, store.session

    def save_document(
        self,
        request: DocumentSaveRequest | dict[str, Any],
        key: str,
        *,
        preserve_version_id: str | None = None,
    ) -> dict[str, Any]:
        body = DocumentSaveRequest.model_validate(request)
        fingerprint = digest(body.model_dump())
        previous = self.session.get(QueryOperation, key)
        if previous:
            if previous.request_hash != fingerprint:
                raise KnowledgeError("IDEMPOTENCY_CONFLICT", "相同操作键对应不同文档请求")
            return previous.response
        if not self.session.get(Project, body.project_id):
            raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
        document = self.session.get(QueryDocument, body.document_id) if body.document_id else None
        if body.document_id and (
            not document or document.project_id != body.project_id or document.kind != body.kind
        ):
            raise KnowledgeError("QUERY_SCOPE_INVALID", "目标文档不属于当前项目或类型")
        if document and document.current_version_id != body.base_version_id:
            raise KnowledgeError("DOCUMENT_VERSION_CONFLICT", "文档基线已变化")
        if not document and body.base_version_id is not None:
            raise KnowledgeError("DOCUMENT_VERSION_CONFLICT", "新文档不能指定旧版本")
        preserved: dict[str, QueryPassage] = {}
        if preserve_version_id is not None:
            baseline = self.session.get(QueryDocumentVersion, preserve_version_id)
            if (
                body.state != "draft"
                or not document
                or not baseline
                or baseline.document_id != document.id
            ):
                raise KnowledgeError("DOCUMENT_VERSION_CONFLICT", "仅同一文档的草稿可保留旧段落")
            preserved = {
                p.local_ref: p
                for p in self.session.scalars(
                    select(QueryPassage).where(QueryPassage.version_id == baseline.id)
                )
            }
        checked_passages = []
        for passage in body.passages:
            dependencies = [dep.model_dump(exclude_none=True) for dep in passage.dependencies]
            checked = validate_dependencies(
                self.session, body.project_id, dependencies, True, "local"
            )
            old = preserved.get(passage.local_ref)
            unchanged = bool(
                old
                and old.text == passage.text
                and old.attribution == passage.attribution
                and old.dependencies == dependencies
                and old.caveats == passage.caveats
                and old.sha256 == text_hash(passage.text)
            )
            if checked["content_state"] != "valid" and not unchanged:
                raise KnowledgeError(
                    "DOCUMENT_DEPENDENCY_INVALID", ",".join(checked["issues"]) or "文档依据未验证"
                )
            personal = any(
                root["source_kind"] in {"note", "annotation"}
                or (root["source_kind"] == "external" and root.get("attribution") == "user_view")
                for root in checked["roots"]
            )
            paper = any(root["source_kind"] == "paper" for root in checked["roots"])
            external_source = any(
                root["source_kind"] == "external" and root.get("attribution") == "external_source"
                for root in checked["roots"]
            )
            if not unchanged and (
                (passage.attribution == "user_view" and not personal)
                or (
                    passage.attribution in {"paper_author", "citation_report"}
                    and (not paper or personal or external_source)
                )
                or (passage.attribution == "model_synthesis" and personal)
            ):
                raise KnowledgeError("DOCUMENT_ATTRIBUTION_INVALID", "段落归属与根来源不匹配")
            checked_passages.append((passage, dependencies))
        if document is None:
            document = QueryDocument(
                id=str(uuid4()),
                project_id=body.project_id,
                kind=body.kind,
                title=body.title,
                created_at=now(),
            )
            self.session.add(document)
            self.session.flush()
        previous_revision = (
            self.session.scalar(
                select(func.max(QueryDocumentVersion.revision)).where(
                    QueryDocumentVersion.document_id == document.id
                )
            )
            or 0
        )
        version = QueryDocumentVersion(
            id=str(uuid4()),
            document_id=document.id,
            revision=previous_revision + 1,
            state=body.state,
            sha256=digest(body.model_dump()),
            created_at=now(),
        )
        self.session.add(version)
        self.session.flush()
        ids = []
        for ordinal, (passage, dependencies) in enumerate(checked_passages):
            entry = QueryPassage(
                id=str(uuid4()),
                version_id=version.id,
                ordinal=ordinal,
                local_ref=passage.local_ref,
                text=passage.text,
                sha256=text_hash(passage.text),
                attribution=passage.attribution,
                dependencies=dependencies,
                caveats=passage.caveats,
            )
            self.session.add(entry)
            ids.append(entry.id)
        if body.state == "saved":
            document.current_version_id = version.id
        response = {
            "document_id": document.id,
            "version_id": version.id,
            "revision": version.revision,
            "passage_ids": ids,
        }
        self.session.add(QueryOperation(key=key, request_hash=fingerprint, response=response))
        self.store.audit_event(
            body.project_id,
            "DOCUMENT_REGISTERED",
            response,
            actor="user",
            trigger="document_registration",
        )
        return response

    def register_file(
        self, document_id: str, root_id: str, relative_path: str, version_id: str, sha256: str
    ) -> None:
        document = self.session.get(QueryDocument, document_id)
        root = self.session.get(AuthorizedRoot, root_id)
        version = self.session.get(QueryDocumentVersion, version_id)
        if (
            not document
            or not root
            or not root.active
            or root.project_id != document.project_id
            or not version
            or version.document_id != document.id
        ):
            raise KnowledgeError("QUERY_SCOPE_INVALID", "文件登记来源或版本不匹配")
        data, state = read_authorized_file(root, relative_path)
        if state != "available" or data is None or hashlib.sha256(data).hexdigest() != sha256:
            raise KnowledgeError("DOCUMENT_FILE_MISMATCH", "仅可登记当前授权文件的准确哈希")
        binding = self.session.get(QueryFileBinding, document.id)
        if not binding:
            binding = QueryFileBinding(
                document_id=document.id,
                root_id=root_id,
                relative_path=relative_path,
                version_id=version_id,
                sha256=sha256,
                conflict=False,
            )
            self.session.add(binding)
        else:
            binding.root_id, binding.relative_path = root_id, relative_path
            binding.version_id, binding.sha256, binding.conflict = version_id, sha256, False

    def set_note_grant(
        self, project_id: str, root_id: str, allow_local: bool, allow_model: bool
    ) -> dict[str, Any]:
        root = self.session.get(AuthorizedRoot, root_id)
        if not root or not root.active or root.project_id != project_id:
            raise KnowledgeError("ROOT_NOT_AUTHORIZED", "笔记目录未授权或已撤销")
        grant = self.session.get(NoteUseGrant, root_id)
        if grant is None:
            grant = NoteUseGrant(
                root_id=root_id, allow_local=allow_local, allow_model=allow_model, revision=1
            )
            self.session.add(grant)
        elif (grant.allow_local, grant.allow_model) != (allow_local, allow_model):
            grant.allow_local, grant.allow_model = allow_local, allow_model
            grant.revision += 1
        self.store.audit_event(
            project_id,
            "NOTE_USE_CHANGED",
            {"root_id": root_id, "revision": grant.revision},
            actor="user",
            trigger="note_permissions",
        )
        return {
            "root_id": root_id,
            "allow_local": grant.allow_local,
            "allow_model": grant.allow_model,
            "revision": grant.revision,
        }
