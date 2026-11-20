"""Run the Lite sidecar smoke without a model, Node or Conda on PATH."""

import argparse
import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.error
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
                health["schema_version"] == "lite0018"
                and health["database"] == "ready"
                and health["fts5"]
            )
            try:
                request(base, token, "GET", "/settings/translation")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404, exc.code
            else:
                raise AssertionError("Retired translation API is still available")
            project = request(
                base,
                token,
                "POST",
                "/projects",
                {"name": "Lite smoke", "description": "synthetic"},
                "project-1",
            )
            fixture = (fixture or root / "tests" / "fixtures" / "pdf" / "two-pages.pdf").resolve()
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
            papers = request(base, token, "GET", f"/projects/{project['id']}/papers")
            paper_id = papers["items"][0]["id"]
            detail = request(base, token, "GET", f"/papers/{paper_id}")
            version = detail["revisions"][0]["id"]
            directory_start = time.perf_counter()
            directory = request(
                base, token, "GET", f"/revisions/{version}/sections?include_text=false"
            )
            directory_seconds = time.perf_counter() - directory_start
            assert directory["sections"] and all(
                row["text"] == "" and row["chunk_ids"] == [] for row in directory["sections"]
            )
            sections = request(base, token, "GET", f"/revisions/{version}/sections")
            section = next(
                item for item in sections["sections"] if not item["excluded"] and item["chunk_ids"]
            )
            preview = request(
                base,
                token,
                "GET",
                f"/revisions/{version}/sections?section_id={section['id']}",
            )
            assert preview["document_version_id"] == version and preview["sections"] == [section]
            scope = f"/papers/{paper_id}/sections/{section['id']}"
            paragraphs = request(
                base, token, "GET", f"{scope}/paragraphs?document_version_id={version}"
            )
            assert paragraphs["paragraphs"]
            assert all(
                item["text_en"] and item["text_hash"] and item["span_ids"]
                for item in paragraphs["paragraphs"]
            )
            state = request(
                base,
                token,
                "PUT",
                f"{scope}/reading-state",
                {
                    "document_version_id": version,
                    "progress": "READING",
                    "self_assessment": "PARTIAL",
                },
            )
            assert state["progress"] == "READING" and state["self_assessment"] == "PARTIAL"
            restored = request(
                base, token, "GET", f"{scope}/reading-state?document_version_id={version}"
            )
            assert restored["self_assessment"] == "PARTIAL"
            assert (
                request(base, token, "GET", f"{scope}/close-reading?document_version_id={version}")
                is None
            )
            request(base, token, "GET", f"/papers/{paper_id}/concept-understanding")
            usage = request(base, token, "GET", f"/projects/{project['id']}/lite/usage")
            assert (
                usage["calls"] == 0 and usage["input_tokens"] == 0 and usage["output_tokens"] == 0
            )
            report = {
                "schema_version": health["schema_version"],
                "project": project["id"],
                "pdf_job": job["id"],
                "model_calls": usage["calls"],
                "local_reading_paragraphs": len(paragraphs["paragraphs"]),
                "local_reading_state": restored["progress"],
                "qa_directory_sections": len(directory["sections"]),
                "qa_directory_seconds": round(directory_seconds, 6),
                "qa_lazy_preview_sections": len(preview["sections"]),
                "translation_available": False,
                "status": "passed",
            }
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
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.executable, args.source_python, fixture=args.fixture),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
