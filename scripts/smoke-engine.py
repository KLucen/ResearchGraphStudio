"""Run the Lite sidecar smoke without a model, Node or Conda on PATH."""

import argparse
import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def request(base: str, token: str, method: str, path: str, body=None, key: str = "smoke-lite"):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Idempotency-Key", key)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read())


def run(
    executable: Path | None,
    source_python: Path | None = None,
    *,
    after_import=None,
    fixture: Path | None = None,
) -> dict[str, object]:
    if (executable is None) == (source_python is None):
        raise ValueError("choose exactly one packaged executable or source Python")
    root = Path(__file__).resolve().parents[1]
    token = secrets.token_urlsafe(48)
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
    if source_python:
        env["PYTHONPATH"] = str(root / "services" / "engine")
        command = [str(source_python), "-m", "researchgraph", "--data-dir"]
    else:
        command = [str(executable), "--data-dir"]
    with tempfile.TemporaryDirectory(prefix="researchgraph-lite-smoke-") as folder:
        data_dir = Path(folder)
        child = subprocess.Popen(
            command + [str(data_dir)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        try:
            assert child.stdin and child.stdout
            child.stdin.write(json.dumps({"token": token}) + "\n")
            child.stdin.flush()
            line = child.stdout.readline().strip()
            if not line.startswith("RGS_READY "):
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
                stderr = child.stderr.read(4000) if child.stderr else ""
                raise AssertionError(f"engine readiness failed: stdout={line!r}; stderr={stderr!r}")
            ready = json.loads(line[10:])
            base = f"http://127.0.0.1:{ready['port']}/api/v1"
            health = request(base, token, "GET", "/health")
            assert (
                health["schema_version"] == "lite0008"
                and health["database"] == "ready"
                and health["fts5"]
            )
            translation = request(base, token, "GET", "/settings/translation")
            assert translation["enabled"] is True and translation["launch_mode"] == "bundled"
            project = request(
                base,
                token,
                "POST",
                "/projects",
                {"name": "Lite smoke", "description": "synthetic"},
                "project-1",
            )
            fixture = fixture or root / "tests" / "fixtures" / "pdf" / "two-pages.pdf"
            job = request(
                base,
                token,
                "POST",
                f"/projects/{project['id']}/papers/import/pdf",
                {"path": str(fixture), "mode": "reference"},
                "import-1",
            )
            deadline = time.monotonic() + 30
            current = None
            while time.monotonic() < deadline:
                current = request(base, token, "GET", f"/jobs/{job['id']}")
                if current["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.1)
            assert current and current["status"] == "succeeded", current
            usage = request(base, token, "GET", f"/projects/{project['id']}/lite/usage")
            assert (
                usage["calls"] == 0 and usage["input_tokens"] == 0 and usage["output_tokens"] == 0
            )
            request(base, token, "GET", f"/projects/{project['id']}/papers")
            report = {
                "schema_version": health["schema_version"],
                "project": project["id"],
                "pdf_job": job["id"],
                "model_calls": usage["calls"],
                "translation_enabled": translation["enabled"],
                "status": "passed",
            }
            if after_import is not None:
                report["translation"] = after_import(base, token, project["id"], fixture)
            return report
        finally:
            if child.stdin and not child.stdin.closed:
                child.stdin.close()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--executable", type=Path)
    group.add_argument("--source-python", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.executable, args.source_python), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
