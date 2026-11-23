"""Verify public knowledge failure diagnostics using isolated loopback HTTP only."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any


def run(executable: Path | None, source_python: Path | None) -> dict[str, Any]:
    if (executable is None) == (source_python is None):
        raise ValueError("Choose one packaged executable or source Python")
    spec = importlib.util.spec_from_file_location(
        "diagnostic_smoke_harness", Path(__file__).with_name("smoke-knowledge-library.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Knowledge smoke harness is missing")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    shared = helper.harness()
    sentinel = "synthetic-private-model-body-never-for-public-routes"

    class FailureProvider(shared.SyntheticProvider):
        mode = "client"

        def _handler(self) -> Any:
            parent = super()._handler()
            fixture = self

            class Handler(parent):
                def handle(self) -> None:
                    try:
                        super().handle()
                    except (ConnectionAbortedError, ConnectionResetError):
                        # The client closes rejected HTTP responses without reading
                        # their private body; a reset of the keep-alive fixture is normal.
                        pass

                def do_POST(self) -> None:
                    if fixture.mode == "schema":
                        super().do_POST()
                        return
                    assert self.path == "/v1/chat/completions"
                    assert self.client_address[0] == "127.0.0.1"
                    assert not self.headers.get("Authorization")
                    body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    assert body["model"] == shared.MODEL
                    fixture.calls.append("rejected")
                    self.send_body(
                        400, json.dumps({"error": sentinel}).encode(), "application/json"
                    )

            return Handler

        def respond(self, body: dict[str, Any]) -> tuple[dict[str, Any], str]:
            assert body["model"] == shared.MODEL
            return {
                "schema_version": "paper-knowledge-1",
                "paper_card": {sentinel: sentinel},
                "graph": {"nodes": [], "edges": []},
            }, "invalid_schema"

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
    results = []
    for mode in ("client", "schema"):
        with (
            tempfile.TemporaryDirectory(prefix="rgs-knowledge-diagnostic-") as folder,
            FailureProvider() as provider,
        ):
            provider.mode = mode
            isolated = Path(folder)
            token = secrets.token_urlsafe(48)
            pdf = isolated / "anonymous.pdf"
            original_sha = shared.make_pdf(pdf)
            with helper.sidecar(command, isolated, token, env) as base:
                project = request(
                    base, token, "POST", "/projects", {"name": "Anonymous diagnostic"}
                )
                connection = request(
                    base,
                    token,
                    "POST",
                    "/settings/connections",
                    {
                        "name": "Loopback diagnostic",
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
                        "name": "Synthetic failure",
                        "connection_id": connection["id"],
                        "model": shared.MODEL,
                        "parameters": {"timeout_seconds": 20},
                    },
                )
                request(
                    base,
                    token,
                    "POST",
                    "/settings/model-roles",
                    {"knowledge_extract": profile["id"]},
                )
                request(
                    base,
                    token,
                    "PATCH",
                    "/knowledge/library",
                    {"auto_collect": True, "allow_network": True, "total_request_limit": 1},
                )
                imported = request(
                    base,
                    token,
                    "POST",
                    f"/projects/{project['id']}/papers/import/pdf",
                    {"path": str(pdf), "mode": "reference"},
                )
                shared.wait_job(base, token, imported["id"])
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    runs = request(base, token, "GET", "/knowledge/runs")["items"]
                    if runs and runs[0]["status"] == "failed":
                        break
                    time.sleep(0.1)
                else:
                    raise AssertionError("Synthetic knowledge failure did not finish")
                job_id = runs[0]["job_id"]
                expected = (
                    "KNOWLEDGE_PROVIDER_CLIENT"
                    if mode == "client"
                    else "KNOWLEDGE_RESPONSE_SCHEMA_INVALID"
                )
                views = [
                    request(base, token, "GET", "/jobs/" + job_id),
                    next(j for j in request(base, token, "GET", "/jobs") if j["id"] == job_id),
                    next(
                        j
                        for j in request(base, token, "GET", f"/projects/{project['id']}/jobs")[
                            "items"
                        ]
                        if j["id"] == job_id
                    ),
                ]
                for view in views:
                    diagnostic = view["result"]["knowledge_diagnostic"]
                    assert diagnostic["code"] == expected, diagnostic
                    assert diagnostic["request_sent"] is True
                    assert diagnostic["raw_available"] is (mode == "schema")
                    assert diagnostic["summary"] and diagnostic["action"]
                    assert sentinel not in json.dumps(view, ensure_ascii=False)
                assert len(provider.calls) == 1 and not provider.errors
                before = views[0]["result"]["knowledge_diagnostic"]
            with helper.sidecar(command, isolated, token, env) as base:
                after = request(base, token, "GET", "/jobs/" + job_id)
                assert after["result"]["knowledge_diagnostic"] == before
                assert len(provider.calls) == 1 and not provider.errors
            assert hashlib.sha256(pdf.read_bytes()).hexdigest() == original_sha
            results.append(
                {
                    "mode": mode,
                    "code": expected,
                    "synthetic_requests": 1,
                    "restart_extra_requests": 0,
                }
            )
    return {"status": "passed", "real_model_calls": 0, "non_loopback_requests": 0, "cases": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--executable", type=Path)
    target.add_argument("--source-python", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.executable, args.source_python), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
