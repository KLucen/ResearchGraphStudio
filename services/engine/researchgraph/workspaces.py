"""Leased, flat workspaces; recovery never traverses or removes source/attachment files."""

import json
import logging
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from filelock import FileLock, Timeout

from researchgraph.schemas import WorkspaceCleanup

MARKER = "workspace.json"
FILES = {
    MARKER,
    "snapshot.pdf",
    "result.json",
    "error.txt",
    "request.json",
    "stage.json",
    "stage.tmp",
}


def plain(path: Path, *, directory: bool = False) -> bool:
    info = path.lstat()
    return (
        not stat.S_ISLNK(info.st_mode)
        and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        and (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
    )


def valid_root(root: Path) -> bool:
    return plain(root, directory=True) and root.resolve().parent == root.parent.resolve()


def owned(work: Path) -> bool:
    try:
        return (
            str(UUID(work.name)) == work.name
            and valid_root(work.parent)
            and plain(work, directory=True)
            and work.resolve().parent == work.parent.resolve()
            and plain(work / MARKER)
            and (work / MARKER).stat().st_size < 1024
            and json.loads((work / MARKER).read_text(encoding="utf-8"))
            == {"format": 1, "workspace_id": work.name}
        )
    except (OSError, ValueError):
        return False


def lease(work: Path) -> FileLock:
    # Keep the zero-byte lease's identity stable for a child that starts late.
    # Only the payload directory is reclaimed; these files are never traversed.
    lock_path = work.with_suffix(".lock")
    try:
        if not plain(lock_path) or lock_path.lstat().st_nlink != 1:
            raise OSError("临时任务租约不是普通文件")
    except FileNotFoundError:
        pass
    return FileLock(lock_path, timeout=0, preserve_lock_file=True, fallback_to_soft=False)


def create_workspace(data: Path) -> Path:
    root = data / "import-work"
    root.mkdir(exist_ok=True)
    if not valid_root(root):
        raise ValueError("临时任务目录不是普通应用目录，请检查数据目录")
    work = root / str(uuid4())
    work.mkdir()
    (work / MARKER).write_text(
        json.dumps({"format": 1, "workspace_id": work.name}), encoding="utf-8"
    )
    return work


@contextmanager
def worker_workspace(work: Path) -> Iterator[None]:
    # Validate again after acquiring: recovery may have won the race with a
    # child that was spawned before the previous engine died but started late.
    if not owned(work):
        raise ValueError("临时任务目录已失效")
    with lease(work):
        if not owned(work):
            raise ValueError("临时任务目录已失效")
        yield


def clean_workspace(work: Path) -> str:
    if not owned(work):
        return "retained"
    try:
        with lease(work):
            if not owned(work):
                return "retained"
            files = list(work.iterdir())
            if any(item.name not in FILES or not plain(item) for item in files):
                return "retained"
            # No recursive deletion. Remove the ownership marker last so a
            # partial permission failure can be retried at the next startup.
            for item in files:
                if item.name != MARKER:
                    item.unlink()
            (work / MARKER).unlink()
            try:
                work.rmdir()
            except OSError:
                # Keep a retryable marker if only removal of the empty directory failed.
                with (work / MARKER).open("x", encoding="utf-8") as marker:
                    json.dump({"format": 1, "workspace_id": work.name}, marker)
                raise
        return "removed"
    except Timeout:
        return "busy"
    except OSError:
        return "errors"


def recover_workspaces(data: Path) -> WorkspaceCleanup:
    report = WorkspaceCleanup()
    root = data / "import-work"
    try:
        try:
            root.lstat()
        except FileNotFoundError:
            return report
        if not valid_root(root):
            report.retained = 1
        else:
            for work in root.iterdir():
                # Stable lease files contain no PDF/text data and remain in place.
                if work.suffix == ".lock" and plain(work):
                    continue
                outcome = clean_workspace(work)
                setattr(report, outcome, getattr(report, outcome) + 1)
    except OSError:
        report.errors += 1
    if report.busy or report.retained or report.errors:
        logging.getLogger(__name__).warning("Temporary workspace recovery: %s", report.model_dump())
    return report


def report_stage(work: Path, stage: str) -> None:
    try:
        temporary = work / "stage.tmp"
        temporary.write_text(json.dumps({"stage": stage}), encoding="utf-8")
        temporary.replace(work / "stage.json")
    except OSError:
        # Progress is advisory. A brief sharing violation must not fail the PDF job.
        pass


def read_stage(work: Path, kind: str) -> str | None:
    try:
        with (work / "stage.json").open(encoding="utf-8") as stream:
            payload = json.loads(stream.read(256))
        stage = payload.get("stage") if isinstance(payload, dict) else None
        valid = {"reading", "parsing"} if kind == "pdf_import" else {"checking"}
        return stage if isinstance(stage, str) and stage in valid else None
    except (OSError, ValueError):
        return None
