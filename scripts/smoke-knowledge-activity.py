"""Use real loopback SSE to finish after the old deadline, without any paid model."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Any


def run(executable: Path | None, source_python: Path | None) -> dict[str, Any]:
    if (executable is None) == (source_python is None):
        raise ValueError("Choose packaged executable or source Python")
    spec = importlib.util.spec_from_file_location(
        "activity_smoke_harness", Path(__file__).with_name("smoke-knowledge-library.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Knowledge smoke harness is missing")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    shared = helper.harness()

    class ActiveProvider(shared.SyntheticProvider):
        def _handler(self) -> Any:
            parent = super()._handler()
            fixture = self

            class Handler(parent):
                def do_POST(self) -> None:
                    try:
                        assert self.path == "/v1/chat/completions"
                        assert self.client_address[0] == "127.0.0.1"
                        assert not self.headers.get("Authorization")
                        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                        assert body["model"] == shared.MODEL and body["stream"] is True
                        data = json.loads(body["messages"][1]["content"])["untrusted_source_data"]
                        excerpt = data["sources"][0]["excerpts"][0]
                        payload = {
                            "schema_version": "paper-knowledge-1",
                            "paper_card": {
                                "research_question": "",
                                "motivation": "",
                                "method_summary": "合成方法",
                                "contributions": [],
                                "main_findings": [],
                                "limitations": [],
                            },
                            "graph": {
                                "nodes": [
                                    {
                                        "id": "n1",
                                        "type": "METHOD",
                                        "label_zh": "合成方法",
                                        "label_en": None,
                                        "description_zh": "合成软件夹具，不是真实科学结论。",
                                        "basis": "EXPLICIT",
                                        "source_refs": [{"excerpt_id": excerpt["excerpt_id"]}],
                                    }
                                ],
                                "edges": [],
                            },
                        }
                        fixture.calls.append("knowledge_extract")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.close_connection = True

                        def emit(delta: dict[str, Any], finish: str | None = None) -> None:
                            event = {
                                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]
                            }
                            self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                            self.wfile.flush()

                        emit({"reasoning_content": "synthetic public reasoning increment"})
                        for _ in range(6):
                            time.sleep(2)
                            emit({"reasoning_content": "synthetic public reasoning increment"})
                        emit({"content": json.dumps(payload, ensure_ascii=False)})
                        emit({}, "stop")
                        self.wfile.write(b"data: [DONE]\n\n")
                        self.wfile.flush()
                    except Exception as error:
                        fixture.errors.append(type(error).__name__)

            return Handler

    root = Path(__file__).resolve().parents[1]
    env = {
        name: os.environ[name]
        for name in (
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
        )
        if name in os.environ
    }
    env["PATH"] = str(Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32")
    if source_python:
        env["PYTHONPATH"] = str(root / "services/engine")
        command = [str(source_python), "-m", "researchgraph", "--data-dir"]
    else:
        command = [str(executable), "--data-dir"]
    request = shared.request
    with (
        tempfile.TemporaryDirectory(prefix="rgs-active-stream-") as folder,
        ActiveProvider() as provider,
    ):
        isolated, token = Path(folder), secrets.token_urlsafe(48)
        pdf = isolated / "anonymous.pdf"
        shared.make_pdf(pdf)
        with helper.sidecar(command, isolated, token, env) as base:
            project = request(base, token, "POST", "/projects", {"name": "Anonymous active stream"})
            connection = request(
                base,
                token,
                "POST",
                "/settings/connections",
                {
                    "name": "Loopback activity",
                    "provider": "local",
                    "base_url": provider.base_url,
                },
            )
            profile = request(
                base,
                token,
                "POST",
                "/settings/models",
                {
                    "name": "Synthetic live stream",
                    "connection_id": connection["id"],
                    "model": shared.MODEL,
                    "parameters": {"timeout_seconds": 5},
                },
            )
            request(
                base, token, "POST", "/settings/model-roles", {"knowledge_extract": profile["id"]}
            )
            request(
                base,
                token,
                "PATCH",
                "/knowledge/library",
                {
                    "auto_collect": True,
                    "allow_network": True,
                    "total_request_limit": 1,
                },
            )
            imported = request(
                base,
                token,
                "POST",
                f"/projects/{project['id']}/papers/import/pdf",
                {
                    "path": str(pdf),
                    "mode": "reference",
                },
            )
            shared.wait_job(base, token, imported["id"])
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                runs = request(base, token, "GET", "/knowledge/runs")["items"]
                if runs and runs[0]["status"] in {"succeeded", "failed"}:
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("Knowledge activity task did not finish")
            assert runs[0]["status"] == "succeeded", runs[0]
            assert request(base, token, "GET", "/knowledge/papers")["total"] == 1
            job_id = runs[0]["job_id"]
            with closing(
                sqlite3.connect(
                    (isolated / "data/researchgraph-lite.sqlite3").as_uri() + "?mode=ro", uri=True
                )
            ) as db:
                db.execute("PRAGMA query_only=ON")
                snapshot, metadata = db.execute(
                    "SELECT model_snapshot,request_metadata FROM knowledge_extraction_runs "
                    "WHERE job_id=?",
                    (job_id,),
                ).fetchone()
            frozen = json.loads(snapshot)["parameters"]
            assert json.loads(metadata)["request_contract"]["prompt_version"] == (
                "paper-knowledge-extract-3"
            )
            actual = json.loads(metadata)["provider"]
            assert frozen["text_timeout_policy"] == "activity" and frozen["timeout_seconds"] == 5
            assert actual["elapsed_seconds"] > 10 and actual["total_timeout_seconds"] is None
            assert actual["reasoning_characters"] > 0 and actual["content_characters"] > 0
            assert len(provider.calls) == 1 and not provider.errors
        with helper.sidecar(command, isolated, token, env) as base:
            assert request(base, token, "GET", "/jobs/" + job_id)["status"] == "succeeded"
            assert request(base, token, "GET", "/knowledge/papers")["total"] == 1
            assert len(provider.calls) == 1 and not provider.errors
        return {
            "status": "passed",
            "real_model_calls": 0,
            "non_loopback_requests": 0,
            "synthetic_requests": 1,
            "timeout_policy": frozen["text_timeout_policy"],
            "idle_timeout_seconds": 5,
            "previous_total_seconds": 10,
            "observed_elapsed_seconds": actual["elapsed_seconds"],
            "reasoning_characters": actual["reasoning_characters"],
            "content_characters": actual["content_characters"],
            "restart_extra_requests": 0,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--executable", type=Path)
    group.add_argument("--source-python", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.executable, args.source_python), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
