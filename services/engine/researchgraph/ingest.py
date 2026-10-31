"""Bounded, cancellable PDF parsing in a separate process, with atomic DB publication."""

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.models import AttachmentRevision, Chunk, Event, Job, Paper, PaperSource, now
from researchgraph.source_files import MAX_BYTES, publish_source_check
from researchgraph.workspaces import clean_workspace, create_workspace, read_stage, report_stage

MAX_PAGES = 300
MAX_TEXT = 2_000_000


def parse_pdf(path: str, directory: str) -> None:
    # Imported only in the child: MuPDF objects never cross threads/processes.
    import pymupdf

    work = Path(directory)
    try:
        report_stage(work, "reading")
        source = Path(path)
        if not source.is_absolute() or source.suffix.lower() != ".pdf" or not source.is_file():
            raise ValueError("请选择可读取的本地 PDF 文件")
        with source.open("rb") as stream:
            content = stream.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError("PDF 超过本阶段 50 MiB 限制")
        if not content.startswith(b"%PDF-"):
            raise ValueError("文件不是有效 PDF")
        digest = hashlib.sha256(content).hexdigest()
        chunks: list[dict[str, Any]] = []
        warnings = ["阅读顺序和图表/公式未作语义校验，请对照原文核查。"]
        characters = 0
        report_stage(work, "parsing")
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise ValueError("加密 PDF 暂不支持，请使用已解密的副本")
            if not 0 < document.page_count <= MAX_PAGES:
                raise ValueError("PDF 页数必须为 1–300")
            for page in document:
                blocks = page.get_text("blocks", sort=True)
                text_blocks = [block for block in blocks if block[6] == 0 and block[4].strip()]
                if not text_blocks:
                    warnings.append(f"PDF 第 {page.number + 1} 页无可提取文本，可能需要 OCR。")
                for index, block in enumerate(text_blocks):
                    characters += len(block[4])
                    if characters > MAX_TEXT:
                        raise ValueError("提取文本超过本阶段 200 万字符限制")
                    chunks.append(
                        {
                            "page_index": page.number,
                            "page_label": page.get_label(),
                            "block_index": index,
                            "text": block[4],
                            "bbox": list(block[:4]),
                        }
                    )
            result = {
                "sha256": digest,
                "parser_version": f"pymupdf/{pymupdf.VersionBind};blocks-v1",
                "page_count": document.page_count,
                "warnings": warnings,
                "chunks": chunks,
            }
        # Snapshot matches exactly the bytes parsed, even if the original changes later.
        (work / "snapshot.pdf").write_bytes(content)
        (work / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except Exception as error:
        message = (
            str(error) if isinstance(error, ValueError) else "PDF 损坏或无法读取，请检查原文件"
        )
        (work / "error.txt").write_text(message, encoding="utf-8")


def publish_pdf(
    session: Session, job: Job, result: dict[str, Any], work: Path, data: Path
) -> dict[str, str | bool]:
    assert job.payload is not None and job.project_id is not None
    path, mode = job.payload["path"], job.payload["mode"]
    # Existing source identity wins over content deduplication, preserving revisions.
    source = session.scalar(
        select(PaperSource)
        .join(Paper)
        .where(
            Paper.project_id == job.project_id,
            PaperSource.path == path,
        )
    )
    revision = session.scalar(
        select(AttachmentRevision)
        .join(Paper)
        .where(
            Paper.project_id == job.project_id,
            AttachmentRevision.sha256 == result["sha256"],
        )
    )
    paper_id = source.paper_id if source else revision.paper_id if revision else None
    paper = session.get(Paper, paper_id) if paper_id else None
    if paper is None:
        paper = Paper(
            id=str(uuid4()), project_id=job.project_id, title=Path(path).stem, created_at=now()
        )
        session.add(paper)
        session.flush()
    revision = session.scalar(
        select(AttachmentRevision).where(
            AttachmentRevision.paper_id == paper.id,
            AttachmentRevision.sha256 == result["sha256"],
        )
    )
    reused = revision is not None
    if revision is None:
        revision = AttachmentRevision(
            id=str(uuid4()),
            paper_id=paper.id,
            created_at=now(),
            **{key: result[key] for key in ("sha256", "parser_version", "page_count", "warnings")},
        )
        session.add(revision)
        session.flush()
        session.add_all(
            Chunk(id=str(uuid4()), revision_id=revision.id, **block) for block in result["chunks"]
        )
    managed_path = None
    if mode == "managed":
        destination = data / "attachments" / (result["sha256"] + ".pdf")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # A failed DB commit can leave an unreferenced cache, never a broken referenced file.
        (work / "snapshot.pdf").replace(destination)
        managed_path = str(destination)
    source = session.scalar(
        select(PaperSource).where(
            PaperSource.paper_id == paper.id,
            PaperSource.path == path,
            PaperSource.mode == mode,
        )
    )
    if source is None:
        source = PaperSource(id=str(uuid4()), paper_id=paper.id, path=path, mode=mode)
        session.add(source)
    source.revision_id, source.managed_path = revision.id, managed_path
    source.generation = (source.generation or 0) + 1
    source.last_check = None
    session.add(
        Event(
            event_id=str(uuid4()),
            project_id=job.project_id,
            event_type="PDF_IMPORTED",
            payload={
                "paper_id": paper.id,
                "revision_id": revision.id,
                "reused": reused,
                "job_id": job.id,
            },
            created_at=now(),
        )
    )
    return {"paper_id": paper.id, "revision_id": revision.id, "reused": reused}


async def run_file_job(engine: Engine, job_id: str, data: Path) -> None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        assert job and job.payload
        payload, kind = job.payload, job.kind
    work = create_workspace(data)
    command = [sys.executable]
    child_environment = os.environ.copy()
    if not getattr(sys, "frozen", False):
        command += ["-m", "researchgraph"]
        child_environment["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    if kind == "pdf_import":
        command += ["--parse-pdf", payload["path"]]
    else:
        request_file = work / "request.json"
        request_file.write_text(json.dumps(payload), encoding="utf-8")
        command += ["--check-source", str(request_file)]
    command += ["--output-dir", str(work)]
    process = None
    try:
        # An explicit worker CLI avoids frozen multiprocessing bootstrap and keeps
        # the host's private stdin pipe out of parsing children.
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=child_environment,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        deadline = time.monotonic() + 120
        while process.poll() is None:
            with Session(engine) as session:
                current = session.get(Job, job_id)
                if current is None or current.status != "running":
                    return
                stage = read_stage(work, kind)
                if stage and current.stage != stage:
                    current.stage, current.updated_at = stage, now()
                    session.commit()
            if time.monotonic() > deadline:
                raise ValueError("文件处理超时（120 秒），请检查文件或连接")
            await asyncio.sleep(0.1)
        if (work / "error.txt").exists():
            raise ValueError((work / "error.txt").read_text(encoding="utf-8"))
        if process.returncode != 0 or not (work / "result.json").exists():
            raise ValueError("文件处理进程异常退出，可重试或检查原文件")
        result = json.loads((work / "result.json").read_text(encoding="utf-8"))
        with Session(engine) as session, session.begin():
            current = session.get(Job, job_id)
            if current is None or current.status != "running":
                return
            current.stage, current.updated_at = "saving", now()
        with Session(engine) as session, session.begin():
            current = session.get(Job, job_id)
            if current and current.status == "running":
                current.result = (
                    publish_pdf(session, current, result, work, data)
                    if kind == "pdf_import"
                    else publish_source_check(session, current, result)
                )
                current.status, current.updated_at = "succeeded", now()
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        outcome = clean_workspace(work)
        if outcome != "removed":
            # A failed cleanup must not change an already committed job result.
            logging.getLogger(__name__).warning("Deferred temporary workspace cleanup: %s", outcome)
