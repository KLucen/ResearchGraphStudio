"""Exercise the distributed engine with no Conda/Python/Node on its PATH."""

import argparse
import json
import os
import queue
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


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

        def request(port, path, method="GET", body=None, authorized=True):
            headers = {"Content-Type": "application/json", "Idempotency-Key": "smoke-request-001"}
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

        process, port = start()
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
        finally:
            process.stdin.close()
            try:
                assert process.wait(timeout=10) == 0
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        process, port = start()
        try:
            assert request(port, "/projects")["items"] == [project]
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
