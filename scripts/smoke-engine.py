"""Exercise the distributed engine with no Conda/Python/Node on its PATH."""

import argparse
import json
import os
import queue
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4


def run(executable: Path) -> dict[str, object]:
    minimal_env = {
        k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if k in os.environ
    }
    minimal_env["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")
    token = secrets.token_urlsafe(48)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix="ResearchGraph 中文路径 ") as directory:
        data = Path(directory) / "project data"

        def start():
            process = subprocess.Popen(
                [str(executable), "--data-dir", str(data)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=minimal_env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            process.stdin.write(json.dumps({"token": token}) + "\n")
            process.stdin.flush()
            messages = queue.Queue()

            def read():
                for line in process.stdout:
                    if line.startswith("RGS_READY "):
                        messages.put(json.loads(line[len("RGS_READY ") :]))
                        break

            threading.Thread(target=read, daemon=True).start()
            try:
                ready = messages.get(timeout=45)
            except queue.Empty:
                process.kill()
                _, stderr = process.communicate()
                raise RuntimeError("Packaged engine not ready: " + stderr[-4000:]) from None
            return process, ready["port"]

        def request(port, path, method="GET", body=None, authorized=True, key="smoke-request-001"):
            headers = {"Content-Type": "application/json", "Idempotency-Key": key}
            if authorized:
                headers["Authorization"] = "Bearer " + token
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/v1{path}",
                data=json.dumps(body).encode() if body is not None else None,
                method=method,
                headers=headers,
            )
            with opener.open(req, timeout=5) as response:
                return json.load(response)

        def completed(port, job):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                job = request(port, "/jobs/" + job["id"])
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.1)
            assert job["status"] == "succeeded", job
            return job

        process, port = start()
        forced_shutdown = False
        try:
            assert request(port, "/health")["database"] == "ready"
            try:
                request(port, "/health", authorized=False)
                raise AssertionError("Unauthenticated request succeeded")
            except urllib.error.HTTPError as error:
                assert error.code == 401
            project = request(
                port, "/projects", "POST", {"name": "中文项目", "description": "Smoke"}
            )
            assert (
                request(port, "/projects", "POST", {"name": "中文项目", "description": "Smoke"})
                == project
            )
            job = request(port, "/jobs", "POST", {"kind": "diagnostics"})
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                job = request(port, "/jobs/" + job["id"])
                if job["status"] == "succeeded":
                    break
                time.sleep(0.1)
            assert job["status"] == "succeeded", job
            fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/pdf/two-pages.pdf"
            original = Path(directory) / "original.pdf"
            shutil.copyfile(fixture, original)
            pdf = request(
                port,
                f"/projects/{project['id']}/papers/import/pdf",
                "POST",
                {"path": str(original), "mode": "managed"},
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                pdf = request(port, "/jobs/" + pdf["id"])
                if pdf["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.1)
            assert pdf["status"] == "succeeded", pdf
            revision_id = pdf["result"]["revision_id"]
            chunks = request(port, f"/revisions/{revision_id}/chunks")["items"]
            assert {chunk["page_index"] for chunk in chunks} == {0, 1}
            assert any("72%" in chunk["text"] for chunk in chunks)
            paper_id = pdf["result"]["paper_id"]
            source = request(port, f"/papers/{paper_id}")["sources"][0]
            moved = Path(directory) / "relocated.pdf"
            original.rename(moved)
            check = completed(
                port,
                request(
                    port,
                    f"/sources/{source['id']}/check",
                    "POST",
                    {"expected_generation": source["generation"]},
                    key="source-check",
                ),
            )
            assert check["result"]["original_state"] == "missing"
            assert check["result"]["managed_state"] == "available"
            completed(
                port,
                request(
                    port,
                    f"/sources/{source['id']}/relocate",
                    "POST",
                    {"expected_generation": source["generation"], "path": str(moved)},
                    key="source-relocate",
                ),
            )
            relocated = request(port, f"/papers/{paper_id}")["sources"][0]
            # Windows TEMP may use an 8.3 alias (e.g. RUNNER~1). The API stores
            # resolved paths, so compare canonical names, then verify file identity.
            assert relocated["path"] == str(moved.resolve()), relocated
            assert Path(relocated["path"]).samefile(moved), relocated
            assert relocated["revision_id"] == revision_id, relocated
            assert relocated["last_check"]["original"]["state"] == "available"
            history = request(port, f"/projects/{project['id']}/jobs?limit=2")
            older = request(
                port, f"/projects/{project['id']}/jobs?limit=2&cursor={history['next_cursor']}"
            )
            assert len(history["items"]) == 2 and len(older["items"]) == 1
            assert older["items"][0]["id"] == pdf["id"]
            assert all(j["stage"] == "saving" for j in history["items"] + older["items"])
            orphan = data / "import-work" / str(uuid4())
            orphan.mkdir()
            (orphan / "workspace.json").write_text(
                json.dumps({"format": 1, "workspace_id": orphan.name}), encoding="utf-8"
            )
            (orphan / "snapshot.pdf").write_bytes(b"Synthetic abandoned staging data")
            managed_files = {p.name: p.read_bytes() for p in (data / "attachments").glob("*.pdf")}
            process.kill()
            process.wait(timeout=10)
            forced_shutdown = True
        finally:
            process.stdin.close()
            try:
                if not forced_shutdown:
                    assert process.wait(timeout=10) == 0
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        process, port = start()
        try:
            assert request(port, "/health")["temporary_files"]["removed"] == 1
            assert not orphan.exists()
            assert {
                p.name: p.read_bytes() for p in (data / "attachments").glob("*.pdf")
            } == managed_files
            assert moved.read_bytes() == fixture.read_bytes()
            assert request(port, "/projects")["items"] == [project]
            assert request(port, f"/revisions/{revision_id}/chunks")["items"] == chunks
            assert request(port, f"/papers/{paper_id}")["sources"][0] == relocated
        finally:
            process.stdin.close()
            try:
                assert process.wait(timeout=10) == 0
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    return {
        "packaged_engine": "passed",
        "authentication": "passed",
        "idempotency": "passed",
        "diagnostic_job": "passed",
        "pdf_import_and_restart": "passed",
        "source_check_relocate_restart": "passed",
        "job_history_and_stages": "passed",
        "forced_exit_workspace_recovery": "passed",
        "source_and_managed_files_preserved": "passed",
        "restart_persistence": "passed",
        "stdin_eof_exit": "passed",
        "unicode_space_path": "passed",
        "developer_tools_removed_from_child_path": True,
        "clean_windows_machine": "not_tested",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.executable.resolve()), ensure_ascii=False, indent=2))
