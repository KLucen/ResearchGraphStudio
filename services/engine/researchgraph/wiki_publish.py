"""Explicit output authorization and crash-recoverable, compare-before-replace Wiki publishing."""

import difflib
import hashlib
import os
import re
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from filelock import FileLock, Timeout
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.integrations import file_identity, safe_root, unsafe_path, verify_open_note
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import Project, now
from researchgraph.query_documents import validate_dependencies
from researchgraph.query_models import QueryDocument, QueryDocumentVersion, QueryPassage
from researchgraph.wiki_contracts import WikiPublishCommand
from researchgraph.wiki_models import (
    WikiFileBinding,
    WikiFileObservation,
    WikiPublication,
    WikiSection,
    WikiVersion,
    WikiWriteRoot,
)


def _identity(info: os.stat_result) -> dict[str, str]:
    return {"device": str(info.st_dev), "inode": str(info.st_ino)}


def _folder(project_id: str) -> str:
    return "ResearchGraphStudio-" + hashlib.sha256(project_id.encode()).hexdigest()[:16]


def _relative(project_id: str, page_id: str) -> str:
    from researchgraph.wiki_store import page_filename

    return _folder(project_id) + "/" + page_filename(page_id)


def _boundary(root: WikiWriteRoot) -> Path:
    if not root.active:
        raise KnowledgeError("WIKI_ROOT_REVOKED", "Wiki 写入授权已撤销")
    boundary = safe_root(Path(root.path))
    if _identity(boundary.stat()) != {"device": root.device, "inode": root.inode}:
        raise KnowledgeError("WIKI_ROOT_CHANGED", "授权目录身份已变化，请重新选择目录")
    return boundary


def authorize_root(store: KnowledgeStore, project_id: str, path: str) -> dict[str, Any]:
    """Only a native dialog endpoint may call this method; reading rights never imply writing."""
    if not store.session.get(Project, project_id):
        raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
    boundary = safe_root(Path(path))
    identity = _identity(boundary.stat())
    root = store.session.scalar(
        select(WikiWriteRoot).where(
            WikiWriteRoot.project_id == project_id, WikiWriteRoot.path == str(boundary)
        )
    )
    if root is None:
        root = WikiWriteRoot(
            id=str(uuid4()),
            project_id=project_id,
            path=str(boundary),
            **identity,
            active=True,
            revision=1,
            created_at=now(),
        )
        store.session.add(root)
    else:
        root.active = True
        root.revision += 1
        root.device, root.inode = identity["device"], identity["inode"]
    store.audit_event(
        project_id,
        "WIKI_WRITE_AUTHORIZED",
        {"root_id": root.id, "revision": root.revision},
        actor="user",
        trigger="wiki_output_dialog",
    )
    return root_view(root)


def root_view(root: WikiWriteRoot) -> dict[str, Any]:
    return {"root_id": root.id, "path": root.path, "active": root.active, "revision": root.revision}


def revoke_root(store: KnowledgeStore, project_id: str, root_id: str) -> dict[str, Any]:
    root = store.session.get(WikiWriteRoot, root_id)
    if not root or root.project_id != project_id:
        raise KnowledgeError("WIKI_ROOT_NOT_FOUND", "写入授权不存在")
    if root.active:
        root.active = False
        root.revision += 1
        store.audit_event(
            project_id,
            "WIKI_WRITE_REVOKED",
            {"root_id": root.id, "revision": root.revision},
            actor="user",
            trigger="wiki_output_revoke",
        )
    return root_view(root)


def _read(
    path: Path, boundary: Path, owned_identity: dict[str, str] | None = None
) -> tuple[bytes | None, dict[str, str] | None]:
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None, None
    owned_links = before.st_nlink == 2 and owned_identity == _identity(before)
    if (
        unsafe_path(path)
        or not stat.S_ISREG(before.st_mode)
        or (before.st_nlink != 1 and not owned_links)
    ):
        raise KnowledgeError("WIKI_UNSAFE_FILE", "受管文件不能是链接、特殊文件或多重硬链接")
    for ancestor in (path.parent, *path.parent.parents):
        if ancestor.is_relative_to(boundary) and unsafe_path(ancestor):
            raise KnowledgeError("WIKI_UNSAFE_PATH", "受管路径经过链接或重解析点")
    with path.open("rb") as stream:
        verify_open_note(stream, boundary)
        data = stream.read(16_000_001)
        opened = os.fstat(stream.fileno())
    after = path.lstat()
    if (
        len(data) > 16_000_000
        or file_identity(before) != file_identity(after)
        or _identity(opened) != _identity(before)
        or unsafe_path(path)
    ):
        raise KnowledgeError("WIKI_FILE_CHANGED", "文件在读取期间改变或超过受管文件限制")
    return data, _identity(after)


def file_status(session: Session, project_id: str, page_id: str) -> dict[str, Any]:
    document = session.get(QueryDocument, page_id)
    if not document or document.project_id != project_id:
        raise KnowledgeError("WIKI_NOT_FOUND", "当前项目中没有该文档")
    binding = session.get(WikiFileBinding, page_id)
    if not binding:
        return {"state": "not_exported", "issues": []}
    result: dict[str, Any] = {
        "root_id": binding.root_id,
        "relative_path": binding.relative_path,
        "version_id": binding.version_id,
        "sha256": binding.sha256,
        "current_hash": None,
        "state": "unavailable",
        "issues": [],
    }
    try:
        root = session.get(WikiWriteRoot, binding.root_id)
        if not root or root.project_id != project_id:
            raise KnowledgeError("WIKI_ROOT_NOT_FOUND", "受管文件授权不存在")
        boundary = _boundary(root)
        if binding.relative_path != _relative(project_id, page_id):
            raise KnowledgeError("WIKI_UNSAFE_PATH", "文件登记路径不匹配")
        data, identity = _read(boundary / binding.relative_path, boundary)
        if data is None:
            result["state"] = "missing"
        else:
            fingerprint = hashlib.sha256(data).hexdigest()
            result["current_hash"] = fingerprint
            result["state"] = (
                "in_sync"
                if fingerprint == binding.sha256
                and identity == {"device": binding.device, "inode": binding.inode}
                else "modified"
            )
    except (KnowledgeError, OSError) as error:
        result["issues"] = [
            error.code if isinstance(error, KnowledgeError) else "WIKI_FILE_UNAVAILABLE"
        ]
    return result


def _assert_valid(
    session: Session, operation: WikiPublication
) -> tuple[WikiWriteRoot, WikiVersion]:
    root = session.get(WikiWriteRoot, operation.root_id)
    wiki = session.get(WikiVersion, operation.version_id)
    version = session.get(QueryDocumentVersion, operation.version_id)
    document = session.get(QueryDocument, operation.document_id)
    if (
        not root
        or root.project_id != operation.project_id
        or not root.active
        or root.revision != operation.root_revision
    ):
        raise KnowledgeError("WIKI_ROOT_REVOKED", "本次发布的独立写授权已变化或撤销")
    _boundary(root)
    if (
        not document
        or document.project_id != operation.project_id
        or not wiki
        or not version
        or version.document_id != document.id
        or version.state != "saved"
        or document.current_version_id != version.id
    ):
        raise KnowledgeError("WIKI_VERSION_CONFLICT", "仅可发布明确保存且仍为当前保存版本的页面")
    if hashlib.sha256(wiki.markdown.encode()).hexdigest() != operation.target_hash:
        raise KnowledgeError("WIKI_CONTENT_CHANGED", "发布内容指纹发生变化")
    for passage in session.scalars(
        select(QueryPassage).where(QueryPassage.version_id == version.id)
    ):
        checked = validate_dependencies(
            session, operation.project_id, passage.dependencies, True, "local"
        )
        section = session.get(WikiSection, passage.id)
        if (
            checked["content_state"] != "valid"
            or not section
            or section.stale_reason
            or hashlib.sha256(passage.text.encode()).hexdigest() != passage.sha256
        ):
            raise KnowledgeError("WIKI_CONTENT_STALE", "页面依据失效或已标过期，不能发布")
    if operation.relative_path != _relative(operation.project_id, operation.document_id):
        raise KnowledgeError("WIKI_UNSAFE_PATH", "发布路径不是程序生成的受管路径")
    from researchgraph.wiki_store import (
        _derive_references,
        _sections,
        render_markdown,
        wiki_version_state,
    )

    sections = _sections(session, operation.version_id)
    references, section_refs = _derive_references(session, operation.project_id, sections)
    if (
        wiki_version_state(session, operation.version_id)
        or references != wiki.references
        or render_markdown(
            operation.document_id,
            wiki.title,
            sections,
            references,
            section_refs,
            wiki.content_hash,
        )
        != wiki.markdown
    ):
        raise KnowledgeError("WIKI_CONTENT_CHANGED", "页面段落或渲染快照发生变化")
    return root, wiki


def publication_view(operation: WikiPublication) -> dict[str, Any]:
    return {
        "operation_id": operation.id,
        "state": operation.state,
        "error": operation.error,
        "root_id": operation.root_id,
        "page_id": operation.document_id,
        "version_id": operation.version_id,
        "target_hash": operation.target_hash,
        "relative_path": operation.relative_path,
    }


def inspect_file(store: KnowledgeStore, project_id: str, page_id: str) -> dict[str, Any]:
    """Explicitly snapshot external edits without making them document evidence or write rights."""
    status = file_status(store.session, project_id, page_id)
    if status["state"] not in {"modified", "in_sync"}:
        raise KnowledgeError("WIKI_FILE_UNAVAILABLE", "文件不可读取为只读诊断快照")
    binding = store.session.get(WikiFileBinding, page_id)
    assert binding
    root = store.session.get(WikiWriteRoot, binding.root_id)
    assert root
    boundary = _boundary(root)
    data, _ = _read(boundary / binding.relative_path, boundary)
    if data is None:
        raise KnowledgeError("WIKI_FILE_UNAVAILABLE", "文件已不存在")
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise KnowledgeError("WIKI_FILE_ENCODING", "外部文件不是有效UTF-8") from error
    fingerprint = hashlib.sha256(data).hexdigest()
    observation = store.session.scalar(
        select(WikiFileObservation)
        .where(
            WikiFileObservation.document_id == page_id,
            WikiFileObservation.root_id == root.id,
            WikiFileObservation.sha256 == fingerprint,
        )
        .order_by(WikiFileObservation.created_at.desc())
        .limit(1)
    )
    if observation is None:
        observation = WikiFileObservation(
            id=str(uuid4()),
            document_id=page_id,
            root_id=root.id,
            sha256=fingerprint,
            text=text,
            created_at=now(),
        )
        store.session.add(observation)
        store.audit_event(
            project_id,
            "WIKI_FILE_OBSERVED",
            {"observation_id": observation.id, "page_id": page_id, "sha256": fingerprint},
            actor="user",
            trigger="wiki_file_inspect",
        )
    wiki = store.session.get(WikiVersion, binding.version_id)
    return {
        "observation_id": observation.id,
        "attribution": "external_user",
        "source_verified": False,
        "sha256": fingerprint,
        "text": text,
        "diff": "".join(
            difflib.unified_diff(
                (wiki.markdown if wiki else "").splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile="published.md",
                tofile="external.md",
            )
        ),
    }


@contextmanager
def _pin_directories(boundary: Path, folder: Path) -> Iterator[None]:
    """On Windows deny ancestor renames while publishing, closing junction replacement races."""
    handles: list[Any] = []
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            create = kernel.CreateFileW
            create.argtypes = [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HANDLE,
            ]
            create.restype = wintypes.HANDLE
            # FILE_SHARE_DELETE deliberately absent. Pin root ancestors and generated output dir.
            for directory in [*reversed(boundary.parents), boundary, folder]:
                handle = create(str(directory), 0x80, 3, None, 3, 0x02200000, None)
                if handle == wintypes.HANDLE(-1).value:
                    raise OSError(ctypes.get_last_error(), "Cannot pin publication directory")
                handles.append(handle)
                if unsafe_path(directory):
                    raise KnowledgeError("WIKI_UNSAFE_PATH", "发布目录不能经过重解析点")
        else:
            directory_flag = getattr(os, "O_DIRECTORY", None)
            nofollow_flag = getattr(os, "O_NOFOLLOW", None)
            if directory_flag is None or nofollow_flag is None:
                raise KnowledgeError("WIKI_UNSAFE_PATH", "当前平台无法安全打开受管目录")
            for directory in (boundary, folder):
                handles.append(os.open(directory, os.O_RDONLY | directory_flag | nofollow_flag))
        if not folder.resolve(strict=True).is_relative_to(boundary) or unsafe_path(folder):
            raise KnowledgeError("WIKI_UNSAFE_PATH", "受管目录已越过授权边界")
        yield
    finally:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            close = ctypes.windll.kernel32.CloseHandle
            close.argtypes, close.restype = [wintypes.HANDLE], wintypes.BOOL
            for handle in reversed(handles):
                close(handle)
        else:
            for handle in reversed(handles):
                os.close(handle)


class WikiPublisher:
    """The ledger commits before I/O; resume never asks a model or adopts arbitrary files."""

    def __init__(self, engine: Engine, fault: Callable[[str], None] | None = None):
        self.engine, self.fault = engine, fault or (lambda _: None)

    def publish(self, project_id: str, page_id: str, request: Any, key: str) -> dict[str, Any]:
        body = WikiPublishCommand.model_validate(request)
        fingerprint = digest({"project_id": project_id, "page_id": page_id, **body.model_dump()})
        operation_key = f"wiki-publish:{project_id}:{key}"
        with Session(self.engine) as session, session.begin():
            previous = session.scalar(
                select(WikiPublication).where(WikiPublication.key == operation_key)
            )
            if previous:
                if previous.request_hash != fingerprint:
                    raise KnowledgeError("IDEMPOTENCY_CONFLICT", "发布标识已用于不同目标")
                operation_id = previous.id
            else:
                root = session.get(WikiWriteRoot, body.root_id)
                wiki = session.get(WikiVersion, body.version_id)
                if not root or not wiki or wiki.content_hash != body.expected_content_hash:
                    raise KnowledgeError("WIKI_BASE_CONFLICT", "发布内容或授权不存在")
                binding = session.get(WikiFileBinding, page_id)
                expected = binding.sha256 if binding and binding.root_id == root.id else None
                if body.expected_target_hash != expected:
                    raise KnowledgeError("WIKI_FILE_CONFLICT", "必须明确匹配最后发布文件的哈希")
                operation = WikiPublication(
                    id=str(uuid4()),
                    project_id=project_id,
                    document_id=page_id,
                    version_id=body.version_id,
                    root_id=root.id,
                    root_revision=root.revision,
                    key=operation_key,
                    request_hash=fingerprint,
                    relative_path=_relative(project_id, page_id),
                    base_hash=expected,
                    target_hash=hashlib.sha256(wiki.markdown.encode()).hexdigest(),
                    stage_identity=None,
                    state="prepared",
                    error=None,
                    created_at=now(),
                    updated_at=now(),
                )
                _assert_valid(session, operation)
                session.add(operation)
                session.flush()
                operation_id = operation.id
        self.fault("prepared")
        return self.recover(project_id, operation_id)

    def recover(self, project_id: str, operation_id: str) -> dict[str, Any]:
        with Session(self.engine) as session, session.begin():
            operation = session.get(WikiPublication, operation_id)
            if not operation or operation.project_id != project_id:
                raise KnowledgeError("WIKI_PUBLICATION_NOT_FOUND", "发布操作不存在")
            root_id = operation.root_id
        locks = Path(str(self.engine.url.database)).parent / "wiki-publication-locks"
        locks.mkdir(exist_ok=True)
        try:
            with FileLock(str(locks / f"{root_id}.lock"), timeout=0):
                return self._recover_locked(project_id, operation_id)
        except Timeout as error:
            raise KnowledgeError(
                "WIKI_PUBLICATION_BUSY", "该目录有另一发布正在执行，请稍后重试"
            ) from error
        except (KnowledgeError, OSError) as error:
            code = (
                error.code
                if isinstance(error, KnowledgeError)
                else "WIKI_PERMISSION_DENIED"
                if isinstance(error, PermissionError)
                else "WIKI_WRITE_FAILED"
            )
            with Session(self.engine) as session, session.begin():
                operation = session.get(WikiPublication, operation_id)
                assert operation
                if operation.state != "succeeded":
                    # Keep the durable phase for crash recovery; expose a separate last error.
                    operation.error, operation.updated_at = code, now()
                result = publication_view(operation)
                result["state"] = (
                    "conflict"
                    if code
                    in {
                        "WIKI_FILE_CONFLICT",
                        "WIKI_PRIVATE_FILE",
                        "WIKI_ROOT_REVOKED",
                        "WIKI_VERSION_CONFLICT",
                        "WIKI_CONTENT_STALE",
                    }
                    else "failed"
                )
            return result

    def _recover_locked(self, project_id: str, operation_id: str) -> dict[str, Any]:
        with Session(self.engine) as session, session.begin():
            operation = session.get(WikiPublication, operation_id)
            assert operation and operation.project_id == project_id
            root, wiki = _assert_valid(session, operation)
            if operation.state == "succeeded":
                return publication_view(operation)
            boundary = _boundary(root)
            folder = boundary / _folder(project_id)
            folder.mkdir(exist_ok=True)
            if unsafe_path(folder):
                raise KnowledgeError("WIKI_UNSAFE_PATH", "受管子目录不能是符号链接或 junction")
            target = folder / Path(operation.relative_path).name
            stage = folder / f".stage-{operation.id}.tmp"
            data = wiki.markdown.encode("utf-8")
        with _pin_directories(boundary, folder):
            with Session(self.engine) as session, session.begin():
                operation = session.get(WikiPublication, operation_id)
                assert operation
                _assert_valid(session, operation)
                target_data, target_identity = _read(
                    target,
                    boundary,
                    operation.stage_identity
                    if operation.state in {"replacing", "replaced"}
                    else None,
                )
                actual = (
                    hashlib.sha256(target_data).hexdigest() if target_data is not None else None
                )
                already_replaced = bool(
                    operation.state in {"replacing", "replaced"}
                    and actual == operation.target_hash
                    and target_identity == operation.stage_identity
                )
                binding = session.get(WikiFileBinding, operation.document_id)
                if (
                    operation.base_hash == operation.target_hash
                    and actual == operation.target_hash
                    and binding
                    and binding.root_id == operation.root_id
                    and target_identity == {"device": binding.device, "inode": binding.inode}
                ):
                    binding.version_id, binding.updated_at = operation.version_id, now()
                    operation.state, operation.error, operation.updated_at = (
                        "succeeded",
                        None,
                        now(),
                    )
                    return publication_view(operation)
                if already_replaced and stage.exists():
                    stage_data, stage_identity = _read(stage, boundary, operation.stage_identity)
                    if stage_data != data or stage_identity != operation.stage_identity:
                        raise KnowledgeError(
                            "WIKI_STAGING_CONFLICT", "恢复时暂存文件身份或内容不匹配"
                        )
                    stage.unlink()
                if not already_replaced:
                    binding = session.get(WikiFileBinding, operation.document_id)
                    identity_matches = bool(
                        binding
                        and target_identity == {"device": binding.device, "inode": binding.inode}
                    )
                    if operation.base_hash is None and target_data is not None:
                        raise KnowledgeError(
                            "WIKI_PRIVATE_FILE", "同名文件未登记为本页受管文件，拒绝覆盖"
                        )
                    if operation.base_hash is not None and (
                        actual != operation.base_hash or not identity_matches
                    ):
                        raise KnowledgeError(
                            "WIKI_FILE_CONFLICT", "受管文件已被外部修改、替换或删除"
                        )
                    stage_data, stage_identity = _read(stage, boundary)
                    if stage_data is None:
                        descriptor = os.open(
                            stage,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                            0o600,
                        )
                        with os.fdopen(descriptor, "wb") as stream:
                            verify_open_note(stream, boundary)
                            stream.write(data)
                            stream.flush()
                            os.fsync(stream.fileno())
                            stage_identity = _identity(os.fstat(stream.fileno()))
                    elif hashlib.sha256(stage_data).hexdigest() != operation.target_hash:
                        raise KnowledgeError(
                            "WIKI_STAGING_CONFLICT", "暂存文件与发布账本不符，未覆盖"
                        )
                    if operation.stage_identity and operation.stage_identity != stage_identity:
                        raise KnowledgeError("WIKI_STAGING_CONFLICT", "发布暂存文件身份已被替换")
                    operation.stage_identity = stage_identity
                    operation.state, operation.error, operation.updated_at = "staged", None, now()
            self.fault("staged")
            with Session(self.engine) as session, session.begin():
                operation = session.get(WikiPublication, operation_id)
                assert operation
                _assert_valid(session, operation)
                if not already_replaced:
                    operation.state, operation.updated_at = "replacing", now()
            self.fault("replacing")
            # Hold the ordinary IMMEDIATE writer transaction over the final source/permission
            # check and rename, so source revocation cannot race the replacement in our database.
            with Session(self.engine) as session, session.begin():
                operation = session.get(WikiPublication, operation_id)
                assert operation
                _assert_valid(session, operation)
                if not already_replaced:
                    target_data, target_identity = _read(target, boundary)
                    actual = (
                        hashlib.sha256(target_data).hexdigest() if target_data is not None else None
                    )
                    binding = session.get(WikiFileBinding, operation.document_id)
                    if actual != operation.base_hash or (
                        operation.base_hash is not None
                        and (
                            not binding
                            or target_identity != {"device": binding.device, "inode": binding.inode}
                        )
                    ):
                        raise KnowledgeError("WIKI_FILE_CONFLICT", "目标在发布前发生外部变化")
                    stage_data, stage_identity = _read(stage, boundary)
                    if stage_data != data or stage_identity != operation.stage_identity:
                        raise KnowledgeError("WIKI_STAGING_CONFLICT", "发布前暂存内容或身份变化")
                    if operation.base_hash is None:
                        # An exclusive hard-link publishes a new file atomically without ever
                        # replacing a concurrently created private file (POSIX rename would).
                        if os.name == "nt":
                            # Windows rename is exclusive if the destination already exists.
                            os.rename(stage, target)
                        else:
                            os.link(stage, target)
                            stage.unlink()
                    else:
                        os.replace(stage, target)
                    operation.state, operation.updated_at = "replaced", now()
                    self.fault("replaced")
                written, identity = _read(target, boundary)
                if written != data or identity != operation.stage_identity:
                    raise KnowledgeError("WIKI_FILE_CONFLICT", "替换后的文件已改变，未确认发布")
                self.fault("before_confirm")
                binding = session.get(WikiFileBinding, operation.document_id)
                if not binding:
                    binding = WikiFileBinding(document_id=operation.document_id)
                    session.add(binding)
                assert identity
                binding.root_id, binding.relative_path = operation.root_id, operation.relative_path
                binding.version_id, binding.sha256 = operation.version_id, operation.target_hash
                binding.device, binding.inode = identity["device"], identity["inode"]
                binding.updated_at = now()
                operation.state, operation.error, operation.updated_at = "succeeded", None, now()
                KnowledgeStore(session).audit_event(
                    project_id,
                    "WIKI_PUBLISHED",
                    {
                        "operation_id": operation.id,
                        "page_id": operation.document_id,
                        "version_id": operation.version_id,
                    },
                    actor="user",
                    trigger="wiki_publish",
                )
                result = publication_view(operation)
            return result


def file_diagnostics(session: Session, project_id: str, page_id: str) -> list[dict[str, Any]]:
    """Lint hook: file identity/sync, section markers, and program-generated local links."""
    status = file_status(session, project_id, page_id)
    issues: list[dict[str, Any]] = []
    for operation in session.scalars(
        select(WikiPublication).where(
            WikiPublication.project_id == project_id,
            WikiPublication.document_id == page_id,
            WikiPublication.state != "succeeded",
        )
    ):
        issues.append(
            {
                "code": "WIKI_PUBLICATION_PENDING",
                "severity": "warning",
                "document_id": page_id,
                "source_id": operation.id,
                "details": {"state": operation.state, "last_error": operation.error},
            }
        )
    if status["state"] == "not_exported":
        return issues
    if status["state"] != "in_sync":
        issues.append(
            {
                "code": "WIKI_FILE_" + status["state"].upper(),
                "severity": "warning",
                "document_id": page_id,
                "source_id": page_id,
                "details": {"file_state": status["state"], "issues": status["issues"]},
            }
        )
    if status["state"] not in {"in_sync", "modified"}:
        return issues
    binding = session.get(WikiFileBinding, page_id)
    assert binding
    root = session.get(WikiWriteRoot, binding.root_id)
    assert root
    try:
        boundary = _boundary(root)
        data, _ = _read(boundary / binding.relative_path, boundary)
        if data is None:
            return issues
        text = data.decode("utf-8")
        expected = set(
            session.scalars(
                select(WikiSection.section_id).where(WikiSection.version_id == binding.version_id)
            )
        )
        actual = re.findall(r'<a id="section-([0-9a-f-]+)"></a>', text)
        if len(actual) != len(set(actual)) or set(actual) != expected:
            issues.append(
                {
                    "code": "WIKI_SECTION_MAPPING_INVALID",
                    "severity": "warning",
                    "document_id": page_id,
                    "source_id": page_id,
                    "details": {
                        "missing_count": len(expected - set(actual)),
                        "unexpected_count": len(set(actual) - expected),
                    },
                }
            )
        for target in re.findall(r"\[相关页面\]\((page-[0-9a-f-]+\.md)\)", text):
            target_id = target[5:-3]
            other = session.get(WikiFileBinding, target_id)
            if (
                not other
                or other.root_id != binding.root_id
                or file_status(session, project_id, target_id)["state"] != "in_sync"
            ):
                issues.append(
                    {
                        "code": "WIKI_LINK_BROKEN",
                        "severity": "warning",
                        "document_id": page_id,
                        "source_id": target_id,
                        "details": {"target_page_id": target_id},
                    }
                )
        anchors = set(re.findall(r'<a id="([a-z0-9-]+)"></a>', text))
        if any(anchor not in anchors for anchor in re.findall(r"\]\(#([a-z0-9-]+)\)", text)):
            issues.append(
                {
                    "code": "WIKI_REFERENCE_LINK_BROKEN",
                    "severity": "warning",
                    "document_id": page_id,
                    "source_id": page_id,
                    "details": {},
                }
            )
    except (KnowledgeError, OSError, UnicodeError):
        issues.append(
            {
                "code": "WIKI_FILE_UNAVAILABLE",
                "severity": "warning",
                "document_id": page_id,
                "source_id": page_id,
                "details": {},
            }
        )
    return issues
