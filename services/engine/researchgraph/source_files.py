"""Local source checks; no knowledge graph or private-note behavior."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError
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
        current = Path(path).stat()
        if any(
            (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            for x in (after, current)
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
        managed=inspect_file(request["managed_path"], request["sha256"])
        if request.get("managed_path")
        else None,
    )
    (directory / "result.json").write_text(result.model_dump_json(), encoding="utf-8")


def publish_source_check(
    session: Session, job: Job, result: dict[str, Any]
) -> dict[str, str | bool]:
    assert job.payload and job.project_id
    source = session.get(PaperSource, job.payload["source_id"])
    if source is None or source.generation != job.payload["generation"]:
        raise KnowledgeError("SOURCE_CHANGED", "来源已更新，请刷新后重试")
    checked = SourceCheck.model_validate(result)
    if job.kind == "source_relocate":
        if checked.original.state != "available":
            raise KnowledgeError("SOURCE_UNAVAILABLE", "所选文件不可用或内容不同")
        old_path = source.path
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
            raise KnowledgeError("SOURCE_CONFLICT", "路径冲突：所选路径已登记到其他来源")
        source.path = job.payload["path"]
        source.generation += 1
    else:
        old_path = source.path
    source.last_check = checked.model_dump()
    event_payload = {
        "source_id": source.id,
        "revision_id": source.revision_id,
        "check": source.last_check,
    }
    if job.kind == "source_relocate":
        event_payload.update({"old_path": old_path, "new_path": source.path})
    session.add(
        Event(
            event_id=str(uuid4()),
            project_id=job.project_id,
            event_type="SOURCE_CHECKED" if job.kind == "source_check" else "SOURCE_RELOCATED",
            payload=event_payload,
            created_at=now(),
        )
    )
    return {
        "source_id": source.id,
        "original_state": checked.original.state,
        "managed_state": checked.managed.state if checked.managed else "not_managed",
    }
