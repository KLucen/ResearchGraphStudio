"""Read-only source adapters. Private notes never become paper evidence or LLM input."""

import json
import os
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.knowledge_models import (
    Annotation,
    AuthorizedRoot,
    EvidenceSpan,
    NoteSnapshot,
    ZoteroLink,
)
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import AttachmentRevision, Paper, PaperSource, now


class LocalRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class ZoteroAdapter:
    base = "http://127.0.0.1:23119/api"

    @staticmethod
    def library(value: str) -> str:
        if not re.fullmatch(r"(?:users|groups)/[0-9]{1,16}", value):
            raise KnowledgeError("INVALID_LIBRARY", "Zotero library 必须为 users/0 或 groups/数字")
        return value

    @staticmethod
    def key(value: str) -> str:
        if not re.fullmatch(r"[A-Z0-9]{8}", value):
            raise KnowledgeError("INVALID_ZOTERO_KEY", "Zotero Key 必须为 8 位大写字母/数字")
        return value

    def get(self, route: str) -> Any:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), LocalRedirect())
        try:
            with opener.open(self.base + route, timeout=5) as response:
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise KnowledgeError("ZOTERO_RESPONSE_TOO_LARGE", "Zotero 响应超过限制")
            return json.loads(raw)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise KnowledgeError(
                "ZOTERO_UNAVAILABLE", "Zotero Local API 未启动、未授权或响应无效"
            ) from error

    def browse(self, library: str, kind: str, start: int = 0) -> list[dict[str, Any]]:
        route = f"/{self.library(library)}/{kind}?limit=50&start={start}"
        value = self.get(route)
        if not isinstance(value, list):
            raise KnowledgeError("ZOTERO_INVALID_RESPONSE", "Zotero 列表响应无效")
        return value

    def attachment_path(self, library: str, key: str) -> Path:
        route = f"/{self.library(library)}/items/{self.key(key)}/file/view"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), LocalRedirect())
        try:
            with opener.open(self.base + route, timeout=5):
                raise KnowledgeError("ZOTERO_FILE_UNAVAILABLE", "Zotero 未返回本地附件位置")
        except urllib.error.HTTPError as error:
            location = error.headers.get("Location", "")
            parsed = urllib.parse.urlsplit(location)
            if (
                error.code not in {301, 302, 303, 307, 308}
                or parsed.scheme != "file"
                or parsed.netloc not in {"", "localhost"}
            ):
                raise KnowledgeError(
                    "ZOTERO_FILE_UNAVAILABLE", "Zotero 附件未同步或无法定位"
                ) from None
            return Path(urllib.request.url2pathname(parsed.path))
        except (urllib.error.URLError, TimeoutError) as error:
            raise KnowledgeError("ZOTERO_UNAVAILABLE", "无法定位 Zotero 本地附件") from error

    def read_annotations(
        self, library: str, item_key: str, attachment_key: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]], Path]:
        prefix = f"/{self.library(library)}/items/"
        item = self.get(prefix + self.key(item_key))
        attachment = self.get(prefix + self.key(attachment_key))
        if attachment.get("data", {}).get("parentItem") != item_key:
            raise KnowledgeError("ZOTERO_PARENT_MISMATCH", "附件不属于所选文献条目")
        position = self.attachment_path(library, attachment_key)
        annotations: list[dict[str, Any]] = []
        for start in range(0, 10000, 100):
            page = self.get(prefix + attachment_key + f"/children?limit=100&start={start}")
            if not isinstance(page, list):
                raise KnowledgeError("ZOTERO_INVALID_RESPONSE", "Zotero 批注响应无效")
            annotations.extend(a for a in page if a.get("data", {}).get("itemType") == "annotation")
            if len(page) < 100:
                return item, annotations, position
        raise KnowledgeError("ZOTERO_TOO_MANY_ANNOTATIONS", "批注超过单次 10000 条限制")


class AnnotationImporter:
    def __init__(self, store: KnowledgeStore):
        self.store, self.session = store, store.session

    def apply(
        self,
        version_id: str,
        library: str,
        item_key: str,
        attachment_key: str,
        metadata: dict[str, Any],
        annotations: list[dict[str, Any]],
        source_path: Path,
    ) -> dict[str, int]:
        self.store.ensure_document(version_id)
        version = self.session.get(AttachmentRevision, version_id)
        assert version
        paper = self.session.get(Paper, version.paper_id)
        assert paper
        # Only a previously user-picked PDF can authorize an attachment identity.
        sources = self.session.scalars(
            select(PaperSource).where(
                PaperSource.paper_id == paper.id, PaperSource.revision_id == version_id
            )
        ).all()
        if not any(Path(s.path).resolve() == source_path.resolve() for s in sources):
            raise KnowledgeError(
                "ZOTERO_ATTACHMENT_NOT_AUTHORIZED",
                "请先用 PDF 选择器导入该 Zotero 附件，再关联批注",
            )
        import hashlib

        with source_path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != version.sha256:
            raise KnowledgeError("SOURCE_CHANGED", "Zotero 附件已变化，请先导入新版本")
        link = self.session.scalar(
            select(ZoteroLink).where(
                ZoteroLink.paper_id == paper.id,
                ZoteroLink.library_id == library,
                ZoteroLink.item_key == item_key,
                ZoteroLink.attachment_key == attachment_key,
            )
        )
        if link is None:
            link = ZoteroLink(
                id=str(uuid4()),
                paper_id=paper.id,
                document_version_id=version_id,
                library_id=library,
                item_key=item_key,
                attachment_key=attachment_key,
                metadata_snapshot=metadata,
            )
            self.session.add(link)
            self.session.flush()
        else:
            link.document_version_id, link.metadata_snapshot = version_id, metadata
        spans = self.session.scalars(
            select(EvidenceSpan).where(EvidenceSpan.document_version_id == version_id)
        ).all()
        added, unresolved = 0, 0
        for item in annotations:
            data = item.get("data", {})
            key = ZoteroAdapter.key(str(item.get("key", data.get("key", ""))))
            if data.get("parentItem") != attachment_key:
                raise KnowledgeError("ANNOTATION_PARENT_MISMATCH", "批注不属于当前附件")
            fingerprint = digest({"data": data, "version": version_id})
            if self.session.scalar(
                select(Annotation).where(
                    Annotation.link_id == link.id,
                    Annotation.annotation_key == key,
                    Annotation.source_hash == fingerprint,
                )
            ):
                continue
            try:
                position = json.loads(data.get("annotationPosition", "{}"))
            except (ValueError, TypeError):
                position = {}
            if not isinstance(position, dict):
                position = {}
            quote = str(data.get("annotationText", ""))
            page = position.get("pageIndex")
            matches = [
                s
                for s in spans
                if quote
                and quote in s.quote
                and s.quote.count(quote) == 1
                and type(page) is int
                and s.page_index == page
            ]
            # Annotation maps to the containing evidence block, never fabricates exact offsets.
            anchor = matches[0].id if len(matches) == 1 else None
            unresolved += int(anchor is None)
            self.session.add(
                Annotation(
                    id=str(uuid4()),
                    link_id=link.id,
                    document_version_id=version_id,
                    annotation_key=key,
                    annotation_type=str(data.get("annotationType", "unknown")),
                    text=quote,
                    comment=str(data.get("annotationComment", "")),
                    source_position=position,
                    source_hash=fingerprint,
                    anchor_status="block_matched" if anchor else "unresolved",
                    evidence_id=anchor,
                    created_at=now(),
                )
            )
            added += 1
        self.store.event(
            paper.project_id,
            "ANNOTATIONS_IMPORTED",
            {"link_id": link.id, "added": added, "unresolved": unresolved},
            actor="user",
            trigger="zotero_read",
        )
        return {"added": added, "unresolved": unresolved}


def unsafe_path(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def safe_root(path: Path) -> Path:
    if not path.is_absolute() or not path.is_dir():
        raise KnowledgeError("INVALID_ROOT", "请选择绝对路径的笔记目录")
    if any(unsafe_path(p) for p in [path, *path.parents]):
        raise KnowledgeError("UNSAFE_ROOT", "笔记目录不能经过链接或重解析点")
    return path.resolve(strict=True)


def verify_open_note(stream: BinaryIO, boundary: Path) -> None:
    """Validate the opened handle before reading, closing Windows junction swap races."""
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        get_path = ctypes.windll.kernel32.GetFinalPathNameByHandleW
        get_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        get_path.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        size = get_path(msvcrt.get_osfhandle(stream.fileno()), buffer, len(buffer), 0)
        if not 0 < size < len(buffer):
            raise KnowledgeError("UNSAFE_NOTE", "无法验证已打开笔记的真实路径")
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        actual = Path(value)
    elif Path("/proc/self/fd").exists():
        actual = Path(os.readlink(f"/proc/self/fd/{stream.fileno()}"))
    else:
        raise KnowledgeError("UNSAFE_NOTE", "此平台尚无经过验证的笔记文件句柄边界检查")
    if not actual.is_relative_to(boundary):
        raise KnowledgeError("UNSAFE_NOTE", "笔记文件句柄指向授权目录之外")


def file_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class ObsidianReader:
    def __init__(self, session: Session):
        self.session = session

    def scan(self, root_id: str) -> dict[str, int]:
        root = self.session.get(AuthorizedRoot, root_id)
        if root is None or not root.active:
            raise KnowledgeError("ROOT_NOT_AUTHORIZED", "笔记目录未授权或已撤销")
        boundary = safe_root(Path(root.path))
        added, skipped, visited, total_bytes = 0, 0, 0, 0
        store = KnowledgeStore(self.session)
        for folder, dirs, files in os.walk(boundary, followlinks=False):
            dirs[:] = [
                d for d in dirs if not d.startswith(".") and not unsafe_path(Path(folder) / d)
            ]
            for filename in files:
                path = Path(folder) / filename
                if path.suffix.lower() != ".md":
                    continue
                visited += 1
                if visited > 1000:
                    raise KnowledgeError(
                        "NOTES_LIMIT", "单次最多扫描 1000 份 Markdown，请缩小授权目录"
                    )
                if unsafe_path(path) or not path.resolve().is_relative_to(boundary):
                    skipped += 1
                    continue
                # Recheck each ancestor immediately before reading, including Windows junctions.
                if any(
                    unsafe_path(p)
                    for p in [path.parent, *path.parent.parents]
                    if p.is_relative_to(boundary)
                ):
                    raise KnowledgeError("UNSAFE_NOTE", "目录在扫描期间发生越权变化")
                try:
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
                        skipped += 1
                        continue
                    content = data.decode("utf-8-sig")
                except (OSError, UnicodeError):
                    skipped += 1
                    continue
                total_bytes += len(data)
                if total_bytes > 20_000_000:
                    raise KnowledgeError("NOTES_LIMIT", "单次笔记总量超过 20 MB")
                import hashlib

                fingerprint = hashlib.sha256(data).hexdigest()
                relative = path.relative_to(boundary).as_posix()
                if self.session.scalar(
                    select(NoteSnapshot).where(
                        NoteSnapshot.root_id == root_id,
                        NoteSnapshot.relative_path == relative,
                        NoteSnapshot.sha256 == fingerprint,
                    )
                ):
                    continue
                self.session.add(
                    NoteSnapshot(
                        id=str(uuid4()),
                        root_id=root_id,
                        relative_path=relative,
                        sha256=fingerprint,
                        text=content,
                        created_at=now(),
                    )
                )
                added += 1
        if added:
            store.audit_event(
                root.project_id,
                "NOTES_SNAPSHOTTED",
                {"root_id": root_id, "added": added},
                actor="user",
                trigger="authorized_notes_read",
            )
        return {"added": added, "skipped": skipped, "visited": visited}
