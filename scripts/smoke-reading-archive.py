"""Verify persisted local reading archives with a real, isolated sidecar.

Only a freshly generated anonymous PDF and a temporary database are used. No
Provider is configured or called. The same archive must remain readable while
a SQLite writer is active and after restart when the test source is absent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections import deque
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
DATABASE_NAME = "researchgraph-lite.sqlite3"


def request(base: str, token: str, method: str, path: str, body: Any = None) -> Any:
    if urlsplit(base).hostname != "127.0.0.1":
        raise ValueError("Smoke requests must stay on loopback")
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=payload, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Idempotency-Key", secrets.token_hex(16))
    with OPENER.open(req, timeout=20) as response:
        return json.loads(response.read())


def make_pdf(path: Path) -> str:
    """Create a fully invented, text-only PDF using the Python standard library."""
    lines = [
        (18, 740, "Anonymous Reading Archive Study"),
        (14, 700, "1 Introduction"),
        (11, 665, "We describe an invented method for checking a local reading archive."),
        (11, 625, "The paragraph remains readable after its temporary PDF is unavailable."),
        (14, 580, "2 Methods"),
        (11, 545, "No scientific findings or private source documents are used in this test."),
    ]
    stream = "\n".join(
        f"BT /F1 {size} Tf 60 {y} Td ({text}) Tj ET" for size, y, text in lines
    ).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(content)
    content.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


class EngineProcess:
    """Drain both child pipes continuously and retain only bounded diagnostics."""

    def __init__(self, command: list[str], env: dict[str, str], data: Path) -> None:
        self.token = secrets.token_urlsafe(48)
        self.base = ""
        self.ready: queue.Queue[str | None] = queue.Queue(maxsize=1)
        self.output: deque[str] = deque(maxlen=32)
        self.errors: deque[str] = deque(maxlen=32)
        self.child = subprocess.Popen(
            command + ["--data-dir", str(data)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.threads = [
            threading.Thread(target=self._stdout, daemon=True),
            threading.Thread(target=self._stderr, daemon=True),
        ]

    def _signal(self, value: str | None) -> None:
        try:
            self.ready.put_nowait(value)
        except queue.Full:
            pass

    def _stdout(self) -> None:
        assert self.child.stdout is not None
        try:
            while chunk := self.child.stdout.readline(8192):
                if chunk.startswith("RGS_READY "):
                    self._signal(chunk[10:].strip())
                else:
                    self.output.append(chunk)
        finally:
            self._signal(None)

    def _stderr(self) -> None:
        assert self.child.stderr is not None
        while chunk := self.child.stderr.read(4096):
            self.errors.append(chunk)

    def __enter__(self) -> EngineProcess:
        for thread in self.threads:
            thread.start()
        try:
            assert self.child.stdin is not None
            self.child.stdin.write(json.dumps({"token": self.token}) + "\n")
            self.child.stdin.flush()
            try:
                ready = self.ready.get(timeout=40)
            except queue.Empty as error:
                raise AssertionError("Engine readiness timed out") from error
            if ready is None:
                raise AssertionError("Engine exited before readiness")
            port = json.loads(ready)["port"]
            assert type(port) is int and 0 < port < 65536
            self.base = f"http://127.0.0.1:{port}/api/v1"
            return self
        except BaseException:
            self.close()
            diagnostics = "".join(self.errors)[-4000:]
            if diagnostics:
                print(diagnostics, file=sys.stderr)
            raise

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def close(self) -> None:
        if self.child.stdin is not None and not self.child.stdin.closed:
            try:
                self.child.stdin.close()
            except OSError:
                pass
        try:
            self.child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.wait(timeout=5)
        for thread in self.threads:
            if thread.ident is not None:
                thread.join(timeout=5)
        for stream in (self.child.stdout, self.child.stderr):
            if stream is not None:
                stream.close()

    def call(self, method: str, path: str, body: Any = None) -> Any:
        return request(self.base, self.token, method, path, body)


def local_snapshot(database: Path, revision: str) -> dict[str, Any]:
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        archives = connection.execute(
            "SELECT id, projection_version, source_hash, projection_hash, data, created_at, "
            "updated_at FROM lite_reading_documents WHERE document_version_id=? ORDER BY id",
            (revision,),
        ).fetchall()
        return {
            "archives": archives,
            "jobs": connection.execute("SELECT count(*) FROM jobs").fetchone()[0],
            "usage_rows": connection.execute("SELECT count(*) FROM lite_token_usage").fetchone()[0],
            "cache_rows": connection.execute("SELECT count(*) FROM lite_cache_entries").fetchone()[
                0
            ],
        }


def wait_job(engine: EngineProcess, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = engine.call("GET", f"/jobs/{job_id}")
        if job["status"] not in {"queued", "running"}:
            assert job["status"] == "succeeded", job
            return job
        time.sleep(0.1)
    raise AssertionError("Anonymous PDF import did not finish within 60 seconds")


def assert_zero_usage(value: dict[str, Any]) -> None:
    assert value["calls"] == 0, value
    assert value["input_tokens"] == value["output_tokens"] == value["total_tokens"] == 0, value


def run(executable: Path | None, source_python: Path | None = None) -> dict[str, Any]:
    if (executable is None) == (source_python is None):
        raise ValueError("Choose exactly one packaged executable or source Python")
    target = source_python if source_python is not None else executable
    assert target is not None and target.is_file(), "Engine executable/Python does not exist"
    root = Path(__file__).resolve().parents[1]
    env = {
        key: os.environ[key]
        for key in (
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
        )
        if key in os.environ
    }
    env["PATH"] = str(Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if source_python is not None:
        env["PYTHONPATH"] = str(root / "services" / "engine")
        command = [str(source_python.resolve()), "-m", "researchgraph"]
    else:
        command = [str(target.resolve())]
    with tempfile.TemporaryDirectory(prefix="researchgraph-reading-archive-smoke-") as temporary:
        work = Path(temporary)
        data = work / "isolated-data"
        pdf = work / "anonymous-source.pdf"
        digest = make_pdf(pdf)
        database = data / DATABASE_NAME
        with EngineProcess(command, env, data) as engine:
            health = engine.call("GET", "/health")
            assert health["database"] == "ready"
            project_id = engine.call("POST", "/projects", {"name": "Archive smoke fixture"})["id"]
            imported = engine.call(
                "POST",
                f"/projects/{project_id}/papers/import/pdf",
                {"path": str(pdf), "mode": "reference"},
            )
            result = wait_job(engine, imported["id"])["result"]
            paper_id, revision = result["paper_id"], result["revision_id"]
            before = local_snapshot(database, revision)
            assert before["archives"] == []
            document_path = f"/papers/{paper_id}/reading-document?document_version_id={revision}"
            document = engine.call("GET", document_path)
            assert document["source_hash"] == digest
            paragraphs = [unit for unit in document["units"] if unit["kind"] == "paragraph"]
            assert paragraphs and all(unit["sources"] for unit in paragraphs)
            archived = local_snapshot(database, revision)
            assert len(archived["archives"]) == 1
            assert archived["usage_rows"] == archived["cache_rows"] == 0
            assert archived["jobs"] == 1
            assert json.loads(archived["archives"][0][4])["view"] == document
            paths = [
                document_path,
                f"/papers/{paper_id}/reading-notes?document_version_id={revision}",
                "/jobs",
                f"/jobs/{imported['id']}",
                f"/projects/{project_id}/jobs",
                "/lite/usage",
                f"/projects/{project_id}/lite/usage",
            ]
            responses = {path: engine.call("GET", path) for path in paths}
            assert responses[paths[1]] is None
            assert_zero_usage(responses["/lite/usage"])
            with closing(sqlite3.connect(database, isolation_level=None, timeout=5)) as writer:
                writer.execute("BEGIN IMMEDIATE")
                try:
                    writer.execute(
                        "UPDATE projects SET name='Uncommitted smoke task' WHERE id=?",
                        (project_id,),
                    )
                    for path in paths:
                        assert engine.call("GET", path) == responses[path], path
                    assert local_snapshot(database, revision) == archived
                finally:
                    writer.rollback()
            assert local_snapshot(database, revision) == archived
        # The only deleted source was created by make_pdf in this TemporaryDirectory.
        # Application data persists for the second isolated sidecar process.
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == digest
        pdf.unlink()
        assert not pdf.exists()
        with EngineProcess(command, env, data) as restarted:
            restored = restarted.call("GET", document_path)
            assert restored == document
            assert restarted.call("GET", paths[1]) is None
            assert_zero_usage(restarted.call("GET", "/lite/usage"))
            assert local_snapshot(database, revision) == archived
        return {
            "status": "passed",
            "target": "source_python" if source_python is not None else "packaged_executable",
            "schema_version": health["schema_version"],
            "projection_version": document["projection_version"],
            "projection_hash": document["projection_hash"],
            "paragraph_count": len(paragraphs),
            "cold_archive_persisted": True,
            "held_writer_read_routes": len(paths),
            "held_writer_responses_unchanged": True,
            "archive_bytes_and_updated_at_unchanged": True,
            "restarted_without_source": True,
            "restarted_content_unchanged": True,
            "model_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "usage_rows": 0,
            "new_model_jobs": 0,
            "private_sources_touched": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--executable", type=Path)
    target.add_argument("--source-python", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.executable, args.source_python)
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
