"""Offline, checksummed snapshots of one Lite database and its managed PDFs."""

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from filelock import FileLock, Timeout
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from researchgraph.source_files import MAX_BYTES
from researchgraph.storage import DATABASE_NAME, SCHEMA_HEAD
from researchgraph.workspaces import native_file_path as backup_file_path
from researchgraph.workspaces import plain

MAX_MANIFEST = 16 * 1024 * 1024
MANIFEST = "workspace-backup.json"


class WorkspaceBackupError(ValueError):
    pass


class FileReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=1)


class WorkspaceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    format_version: int
    schema_version: str
    database: FileReceipt
    attachments: list[FileReceipt]


def _readonly(path: Path) -> sqlite3.Connection:
    if not plain(path):
        raise WorkspaceBackupError("数据文件必须是普通文件")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)


def _validate_database(db: sqlite3.Connection) -> str:
    version = db.execute("SELECT version_num FROM alembic_version").fetchall()
    if version != [(SCHEMA_HEAD,)]:
        raise WorkspaceBackupError("备份与当前应用数据库版本不匹配")
    if db.execute(
        "SELECT 1 FROM sqlite_schema WHERE type IN ('trigger','view') LIMIT 1"
    ).fetchone():
        raise WorkspaceBackupError("备份数据库包含应用不支持的触发器或视图")
    if (
        db.execute("PRAGMA quick_check").fetchone() != ("ok",)
        or db.execute("PRAGMA foreign_key_check").fetchone()
    ):
        raise WorkspaceBackupError("备份数据库的完整性检查未通过")
    return SCHEMA_HEAD


def _receipt(
    source: Path, destination: Path | None = None, *, max_bytes: int | None = None
) -> FileReceipt:
    if not plain(source):
        raise WorkspaceBackupError("备份只接受普通文件")
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as input_file:
        if destination is None:
            size = input_file.seek(0, 2)
            input_file.seek(0)
            return FileReceipt(
                size=size, sha256=hashlib.file_digest(input_file, "sha256").hexdigest()
            )
        with destination.open("xb") as output_file:
            while block := input_file.read(1024 * 1024):
                digest.update(block)
                size += len(block)
                if max_bytes is not None and size > max_bytes:
                    raise WorkspaceBackupError("备份文件在复制期间变大")
                output_file.write(block)
    return FileReceipt(size=size, sha256=digest.hexdigest())


def _managed_references(db: sqlite3.Connection) -> list[tuple[str, str, str]]:
    return [
        (source_id, path, sha)
        for source_id, path, sha in db.execute(
            """SELECT s.id, s.managed_path, r.sha256 FROM paper_sources s
               JOIN attachment_revisions r ON r.id = s.revision_id
               WHERE s.managed_path IS NOT NULL AND s.managed_path != ''"""
        )
    ]


def _external_count(db: sqlite3.Connection) -> int:
    return int(
        db.execute(
            "SELECT count(*) FROM paper_sources WHERE managed_path IS NULL OR managed_path = ''"
        ).fetchone()[0]
    )


def export_workspace(data_dir: Path, directory: Path) -> dict[str, object]:
    """Write into a new sibling of a temporary folder, never into the live workspace."""
    if not backup_file_path(directory).is_dir() or directory.resolve().is_relative_to(
        data_dir.resolve()
    ):
        raise WorkspaceBackupError("请选择应用数据目录以外的备份文件夹")
    if not data_dir.is_dir():
        raise WorkspaceBackupError("当前工作区尚未初始化")
    try:
        with FileLock(data_dir / "engine.lock", timeout=0):
            with TemporaryDirectory(
                prefix=".researchgraph-writing-", dir=backup_file_path(directory)
            ) as name:
                staging = Path(name)
                database = staging / DATABASE_NAME
                with closing(_readonly(data_dir / DATABASE_NAME)) as source:
                    if source.execute(
                        "SELECT 1 FROM jobs WHERE status IN ('running','queued') LIMIT 1"
                    ).fetchone():
                        raise WorkspaceBackupError("请先等待当前任务结束，再创建完整备份")
                    with closing(sqlite3.connect(database)) as target:
                        source.backup(target, pages=128)
                        schema = _validate_database(target)
                        managed = _managed_references(target)
                        external = _external_count(target)

                attachment_root = data_dir / "attachments"
                if managed and not plain(backup_file_path(attachment_root), directory=True):
                    raise WorkspaceBackupError("受管 PDF 目录不可用，无法完成备份")
                cached: dict[str, FileReceipt] = {}
                (staging / "attachments").mkdir()
                for _, original, sha in managed:
                    path = Path(original)
                    filename = f"{sha}.pdf"
                    if (
                        not path.is_absolute()
                        or path.name != filename
                        or path.parent.resolve() != attachment_root.resolve()
                    ):
                        raise WorkspaceBackupError("发现不在受管目录内的 PDF，已停止备份")
                    if sha in cached:
                        continue
                    path = backup_file_path(path)
                    if not plain(path) or path.stat().st_size > MAX_BYTES:
                        raise WorkspaceBackupError("有受管 PDF 缺失或超出大小限制，无法完成备份")
                    receipt = _receipt(
                        path, staging / "attachments" / filename, max_bytes=MAX_BYTES
                    )
                    if receipt.sha256 != sha or receipt.size > MAX_BYTES:
                        raise WorkspaceBackupError("受管 PDF 与已登记指纹不一致")
                    cached[sha] = receipt
                manifest = WorkspaceManifest(
                    format_version=1,
                    schema_version=schema,
                    database=_receipt(database),
                    attachments=sorted(cached.values(), key=lambda item: item.sha256),
                )
                payload = manifest.model_dump_json()
                if len(payload.encode()) > MAX_MANIFEST:
                    raise WorkspaceBackupError("受管文件数量超出备份格式容量")
                (staging / MANIFEST).write_text(payload, encoding="utf-8")
                published = directory / f"ResearchGraph-backup-{uuid4()}"
                staging.rename(backup_file_path(published))
                return {
                    "path": str(published),
                    "managed_files": len(cached),
                    "external_sources": external,
                }
    except Timeout:
        raise WorkspaceBackupError("本地引擎仍在运行，无法执行离线备份") from None


def restore_workspace(source: Path, destination: Path) -> dict[str, object]:
    """Verify and restore into a new workspace. Retain the backup and previous workspace."""
    source = backup_file_path(source)
    if backup_file_path(destination).exists() or not plain(source, directory=True):
        raise WorkspaceBackupError("请选择有效备份文件夹并使用新的恢复目录")
    manifest_file = source / MANIFEST
    if not plain(manifest_file):
        raise WorkspaceBackupError("未找到有效的工作区备份清单")
    with manifest_file.open("rb") as stream:
        payload = stream.read(MAX_MANIFEST + 1)
    if len(payload) > MAX_MANIFEST:
        raise WorkspaceBackupError("备份清单过大")
    try:
        manifest = WorkspaceManifest.model_validate_json(payload)
    except ValidationError:
        raise WorkspaceBackupError("备份清单格式无效") from None
    if manifest.format_version != 1 or manifest.schema_version != SCHEMA_HEAD:
        raise WorkspaceBackupError("备份格式或数据库版本与当前应用不匹配")
    entries = {item.sha256: item for item in manifest.attachments}
    if len(entries) != len(manifest.attachments) or any(
        item.size > MAX_BYTES for item in entries.values()
    ):
        raise WorkspaceBackupError("备份附件清单无效")
    if entries and not plain(source / "attachments", directory=True):
        raise WorkspaceBackupError("备份附件目录无效")

    with TemporaryDirectory(
        prefix=".researchgraph-restoring-", dir=backup_file_path(destination.parent)
    ) as name:
        staging = Path(name)
        database = staging / DATABASE_NAME
        expected_file = source / DATABASE_NAME
        if not plain(expected_file) or expected_file.stat().st_size != manifest.database.size:
            raise WorkspaceBackupError("备份数据库大小不匹配")
        if _receipt(expected_file, database, max_bytes=manifest.database.size) != manifest.database:
            raise WorkspaceBackupError("备份数据库指纹不匹配")
        (staging / "attachments").mkdir()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("PRAGMA trusted_schema=OFF")
            _validate_database(db)
            managed = _managed_references(db)
            if set(entries) != {sha for _, _, sha in managed}:
                raise WorkspaceBackupError("备份附件与数据库引用不匹配")
            for sha, receipt in entries.items():
                filename = f"{sha}.pdf"
                path = source / "attachments" / filename
                if not plain(path) or path.stat().st_size != receipt.size:
                    raise WorkspaceBackupError("备份 PDF 缺失或大小不匹配")
                if (
                    _receipt(path, staging / "attachments" / filename, max_bytes=receipt.size)
                    != receipt
                ):
                    raise WorkspaceBackupError("备份 PDF 指纹不匹配")
            for source_id, old_path, sha in managed:
                new_path = str(destination.resolve() / "attachments" / f"{sha}.pdf")
                db.execute(
                    """UPDATE paper_sources SET managed_path = ?,
                       path = CASE WHEN path = ? THEN ? ELSE path END WHERE id = ?""",
                    (new_path, old_path, new_path, source_id),
                )
            external = _external_count(db)
            # A backup contains authorization history. Opening a copy must not act on it.
            db.execute(
                """UPDATE knowledge_libraries SET settings_json = json_set(settings_json,
                   '$.auto_collect', json('false'), '$.auto_connect', json('false'),
                   '$.allow_network', json('false'))"""
            )
            for table in ("knowledge_collection_events", "knowledge_analysis_events"):
                db.execute(
                    f"UPDATE {table} SET state = 'revoked', reason = 'RESTORED_NETWORK_DISABLED' "
                    "WHERE state = 'pending'"
                )
            db.execute(
                """UPDATE jobs SET status = 'interrupted', error = '从备份恢复，需重新确认任务'
                   WHERE status IN ('queued', 'running')"""
            )
            _validate_database(db)
        staging.rename(backup_file_path(destination))
    return {"path": str(destination), "managed_files": len(entries), "external_sources": external}
