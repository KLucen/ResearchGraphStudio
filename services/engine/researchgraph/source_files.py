"""Explicit, read-only source observations; relocation never replaces parsed history."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from researchgraph.models import Event, Job, Paper, PaperSource, now
from researchgraph.schemas import FileCheck, SourceCheck
from researchgraph.workspaces import report_stage

MAX_BYTES = 50 * 1024 * 1024


def inspect_file(path: str, expected_hash: str) -> FileCheck:
    try:
        with Path(path).open("rb") as stream:
            before = os.fstat(stream.fileno())
            content = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(content) > MAX_BYTES:
            return FileCheck(state="too_large", observed_sha256=None)
        try:
            current = Path(path).stat()
        except OSError:
            return FileCheck(state="unstable", observed_sha256=None)
        if any(
            (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            for item in (after, current)
        ):
            return FileCheck(state="unstable", observed_sha256=None)
        digest = hashlib.sha256(content).hexdigest()
        return FileCheck(
            state="available" if digest == expected_hash else "changed", observed_sha256=digest
        )
    except (FileNotFoundError, NotADirectoryError):
        return FileCheck(state="missing", observed_sha256=None)
    except OSError:
        return FileCheck(state="unreadable", observed_sha256=None)


def check_source_file(request_file: Path, directory: Path) -> None:
    report_stage(directory, "checking")
    request = json.loads(request_file.read_text(encoding="utf-8"))
    result = SourceCheck(
        checked_at=now(),
        original=inspect_file(request["path"], request["sha256"]),
        managed=(
            inspect_file(request["managed_path"], request["sha256"])
            if request["managed_path"]
            else None
        ),
    )
    (directory / "result.json").write_text(result.model_dump_json(), encoding="utf-8")


def publish_source_check(
    session: Session, job: Job, result: dict[str, Any]
) -> dict[str, str | bool]:
    assert job.payload and job.project_id
    source = session.get(PaperSource, job.payload["source_id"])
    if source is None or source.generation != job.payload["generation"]:
        raise ValueError("来源已更新，本次结果未应用；请刷新后重新操作")
    checked = SourceCheck.model_validate(result)
    event_type = "SOURCE_CHECKED"
    event_payload: dict[str, Any] = {"source_id": source.id, "job_id": job.id}
    if job.kind == "source_relocate":
        if checked.original.state != "available":
            raise ValueError("所选文件不可用或内容不同，不能重定位；原来源和历史保持不变")
        # A path may already belong to another paper, or to this paper in the same mode.
        conflict = session.scalar(
            select(PaperSource)
            .join(Paper)
            .where(
                Paper.project_id == job.project_id,
                PaperSource.path == job.payload["path"],
                PaperSource.id != source.id,
                or_(PaperSource.paper_id != source.paper_id, PaperSource.mode == source.mode),
            )
        )
        if conflict:
            raise ValueError("所选路径已登记到其他来源，请选择未冲突的文件")
        event_type = "SOURCE_RELOCATED"
        event_payload.update(old_path=source.path, new_path=job.payload["path"])
        source.path = job.payload["path"]
        source.generation += 1
    source.last_check = checked.model_dump()
    event_payload.update(revision_id=source.revision_id, check=source.last_check)
    session.add(
        Event(
            event_id=str(uuid4()),
            project_id=job.project_id,
            event_type=event_type,
            payload=event_payload,
            created_at=now(),
        )
    )
    return {
        "source_id": source.id,
        "original_state": checked.original.state,
        "managed_state": checked.managed.state if checked.managed else "not_managed",
    }
