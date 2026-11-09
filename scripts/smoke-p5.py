"""P5 production HTTP/SSE transport smoke using synthetic, temporary, offline sources only."""

import argparse
import hashlib
import json
import os
import queue
import secrets
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymupdf


class P5ProtocolStub:
    """Exactly one request per bundled P09/P10/P11 prompt, no credential or external API."""

    model = "synthetic-p5-protocol-only"

    def __init__(self):
        self.calls = {"P09": 0, "P10": 0, "P11": 0}
        self.errors = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format, *_args):
                pass

            def send(self, payload, content_type, status=200):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                try:
                    assert self.path == "/v1/chat/completions"
                    assert not self.headers.get("Authorization"), "No fixture credentials allowed"
                    length = int(self.headers["Content-Length"])
                    assert 0 < length < 4_000_000
                    body = json.loads(self.rfile.read(length))
                    assert body["model"] == owner.model and body["stream"] is True
                    assert body["response_format"] == {"type": "json_object"}
                    supplied = json.loads(body["messages"][1]["content"])
                    data = supplied["untrusted_source_data"]
                    context = data["evidence_context"]
                    assert len(context["scope_versions"]) == 2, "Full selected paper scope required"
                    references = [r for r in context["references"] if r["type"] == "chunk"]
                    direct = next(r for r in references if "shared memory" in r["quote"].lower())
                    assert any("scope a" in r["quote"].lower() for r in references)
                    assert any("scope b" in r["quote"].lower() for r in references)
                    kind = (
                        "P11"
                        if "affected_sections" in data
                        else "P09"
                        if "deterministic_diagnostics" in data
                        else "P10"
                    )
                    assert owner.calls[kind] == 0, "No repeated synthetic requests allowed"
                    owner.calls[kind] += 1
                    passage = {
                        "heading": "适用条件与限制",
                        "text": "合成论文报告共享记忆方法改善任务准确率；只适用于所述条件。",
                        "attribution": "model_synthesis",
                        "source_refs": [direct["ref"]],
                        "limitations": ["仅为合成协议验收，不代表科学质量"],
                        "conditions": [
                            {
                                "dimension": "适用条件",
                                "state": "unknown",
                                "value": None,
                                "unit": None,
                            }
                        ],
                    }
                    if kind == "P09":
                        assert data["deterministic_diagnostics"]["status"] == "completed"
                        assert "repair_plan" not in json.dumps(data, ensure_ascii=False), (
                            "Presentation repair plans must never become model input"
                        )
                        output = {
                            "issues": [
                                {
                                    "code": "insufficient_context",
                                    "severity": "info",
                                    "affected_refs": [direct["ref"]],
                                    "evidence_refs": [direct["ref"]],
                                    "rationale": "合成材料不能支持范围外结论。",
                                    "suggested_action": "保留条件与限制，不自动修改科学知识。",
                                    "uncertainty": "语义正确性未由此协议验收证明",
                                }
                            ],
                            "limitations": ["仅核对传输与引用绑定"],
                        }
                    elif kind == "P10":
                        output = {
                            "title": "合成跨篇阅读整理",
                            "passages": [
                                passage,
                                {
                                    **passage,
                                    "heading": "独立保留段落",
                                    "text": "未受影响段落保持原样。",
                                },
                            ],
                            "coverage_gaps": ["未验证真实论文科学准确率"],
                        }
                    else:
                        assert len(data["affected_sections"]) == 1
                        output = {
                            "edits": [
                                {
                                    "op": "replace",
                                    "section_ref": data["affected_sections"][0]["section_ref"],
                                    "passage": {
                                        **passage,
                                        "text": passage["text"] + " 更新补充：不外推。",
                                    },
                                }
                            ],
                            "coverage_gaps": ["仅更新用户所选的一段"],
                        }
                    content = json.dumps(output, ensure_ascii=False)
                    middle = len(content) // 2
                    events = [
                        {"choices": [{"index": 0, "delta": {"content": part}}]}
                        for part in (content[:middle], content[middle:])
                    ]
                    events.extend(
                        [
                            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                            {
                                "choices": [],
                                "usage": {
                                    "prompt_tokens": 121,
                                    "completion_tokens": 37,
                                    "total_tokens": 158,
                                },
                            },
                        ]
                    )
                    stream = "".join("data: " + json.dumps(e) + "\n\n" for e in events)
                    self.send(
                        (stream + "data: [DONE]\n\n").encode(), "text/event-stream; charset=utf-8"
                    )
                except Exception as error:
                    owner.errors.append(type(error).__name__ + ": " + str(error))
                    self.send(
                        b'{"error":"synthetic P5 protocol assertion failed"}',
                        "application/json",
                        500,
                    )

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/v1"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def run(executable: Path | None, *, source_python: Path | None = None):
    if (executable is None) == (source_python is None):
        raise ValueError("Choose exactly one executable or source Python")
    minimal_env = {
        k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if k in os.environ
    }
    minimal_env["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")
    if source_python:
        minimal_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "services/engine")
    token = secrets.token_urlsafe(48)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with (
        P5ProtocolStub() as stub,
        tempfile.TemporaryDirectory(prefix="ResearchGraph P5 中文 ") as directory,
    ):
        boundary = Path(directory)
        data = boundary / "engine data"
        vault = boundary / "isolated vault"
        vault.mkdir()
        private = vault / "private.md"
        private.write_bytes("私人笔记原字节，仅为隔离合成资料。\n".encode())
        private_bytes = private.read_bytes()

        def start():
            command = (
                [str(source_python), "-m", "researchgraph"] if source_python else [str(executable)]
            )
            process = subprocess.Popen(
                [*command, "--data-dir", str(data)],
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
            ready = queue.Queue()

            def read():
                for line in process.stdout:
                    if line.startswith("RGS_READY "):
                        ready.put(json.loads(line[len("RGS_READY ") :]))
                        break

            threading.Thread(target=read, daemon=True).start()
            try:
                port = ready.get(timeout=45)["port"]
            except queue.Empty:
                process.kill()
                _, stderr = process.communicate()
                raise RuntimeError("P5 engine startup failed: " + stderr[-2000:]) from None
            return process, port

        def stop(process):
            process.stdin.close()
            try:
                assert process.wait(timeout=15) == 0
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)

        def request(
            path,
            method="GET",
            body=None,
            *,
            key="p5-smoke-read",
            native=False,
            expected_error=None,
        ):
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
                "Idempotency-Key": key,
            }
            if native:
                headers["X-ResearchGraph-Native-Token"] = token
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/v1{path}",
                data=json.dumps(body).encode() if body is not None else None,
                method=method,
                headers=headers,
            )
            try:
                with opener.open(req, timeout=20) as response:
                    assert expected_error is None, "Expected authorization refusal"
                    return json.load(response)
            except urllib.error.HTTPError as error:
                payload = json.load(error)
                if expected_error:
                    assert payload["error"]["code"] == expected_error, payload
                    return payload
                raise AssertionError(
                    {"status": error.code, "path": path, "error": payload}
                ) from None

        def completed(job):
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                value = request("/jobs/" + job["id"])
                if value["status"] not in {"queued", "running"}:
                    assert value["status"] == "succeeded", {
                        "job": value,
                        "stub_errors": stub.errors,
                    }
                    return value
                time.sleep(0.1)
            raise AssertionError("P5 job did not finish within bounded smoke deadline")

        process, port = start()
        try:
            assert request("/health")["schema_version"] == "0022"
            project = request(
                "/projects",
                "POST",
                {
                    "name": "P5合成隔离验收",
                    "description": "Offline protocol only",
                    "experience_mode": "legacy",
                },
                key="p5-smoke-project",
            )
            project_id = project["id"]
            base = f"/projects/{project_id}"
            papers = []
            fixtures = {}
            for letter in ("A", "B"):
                path = boundary / ("synthetic-" + letter + ".pdf")
                with pymupdf.open() as document:
                    page = document.new_page()
                    page.insert_text((40, 50), "Synthetic Scope " + letter)
                    page.insert_text(
                        (40, 100), "Our synthetic shared memory method improves task accuracy."
                    )
                    page.insert_text(
                        (40, 150), "This result applies only under the stated conditions."
                    )
                    document.save(path)
                fixtures[path] = path.read_bytes()
                job = completed(
                    request(
                        base + "/papers/import/pdf",
                        "POST",
                        {"path": str(path), "mode": "managed"},
                        key="p5-import-" + letter,
                    )
                )
                papers.append(job["result"]["paper_id"])
            profile = request(
                "/settings/models",
                "POST",
                {
                    "name": "Synthetic P5 loopback protocol",
                    "provider": "local",
                    "base_url": stub.base_url,
                    "model": stub.model,
                    "parameters": {"timeout_seconds": 15, "json_mode": True},
                },
                key="p5-smoke-model",
            )
            assert not profile["has_api_key"]
            request(
                "/settings/model-roles",
                "POST",
                {"extraction": profile["id"], "reasoning": profile["id"]},
                key="p5-smoke-roles",
            )
            graph = request(base + "/graph/projection", "POST", {})
            lint_scope = {"paper_ids": papers, "document_ids": [], "include_personal": False}
            report = request(base + "/lint/runs", "POST", lint_scope, key="p5-lint-01")
            for index in range(20):
                if report["status"] not in {"queued", "running"}:
                    break
                report = request(
                    base + "/lint/runs/" + report["id"] + "/advance",
                    "POST",
                    {"max_items": 100},
                    key=f"p5-lint-advance-{index}",
                )
            assert report["status"] == "completed", report
            lint_issues = request(base + "/lint/runs/" + report["id"] + "/issues")["items"]
            assert lint_issues, "Synthetic sources must exercise the issue response"
            assert all(issue["repair_plan"]["steps"] for issue in lint_issues)
            assert all(
                not step["automated"]
                for issue in lint_issues
                for step in issue["repair_plan"]["steps"]
            )
            assert sum(stub.calls.values()) == 0

            def workflow(kind, key, **extra):
                body = {
                    "kind": kind,
                    "personal_sources": {
                        "version": "p5-personal-sources-1",
                        "note_ids": [],
                        "annotation_ids": [],
                        "external_version_ids": [],
                    },
                    "query": {
                        "project_id": project_id,
                        "question": "核对合成方法的条件、限制与支撑",
                        "paper_ids": papers,
                        "include_personal": False,
                        "purpose": "model",
                    },
                    **extra,
                }
                prepared = request(base + "/workflows/prepare", "POST", body, key=key + "-prepare")
                assert prepared["status"] == "prepared", prepared
                route = base + "/workflows/" + prepared["id"]
                completed(
                    request(
                        route + "/generate",
                        "POST",
                        {"allow_network": True, "continue_requested": False},
                        key=key + "-generate",
                    )
                )
                value = request(route)
                assert value["status"] == "succeeded" and value["request_count"] == 1, value
                assert value["model_runs"][0]["usage"]["total_tokens"] == 158
                return route, value

            _, semantic = workflow("lint_semantic", "p5-smoke-p09", lint_run_id=report["id"])
            assert semantic["result"]["suggestions"][0]["kind"] == "model_suggestion"
            route, synthesis = workflow("wiki_synthesis", "p5-smoke-p10")
            assert len(synthesis["result"]["draft"]["passages"]) == 2
            assert list(vault.rglob("*.md")) == [private]
            assert private.read_bytes() == private_bytes
            draft = request(route + "/materialize", "POST", {}, key="p5-wiki-01")
            assert draft["state"] == "draft" and draft["file"]["state"] == "not_exported"
            page_route = base + "/wiki/pages/" + draft["page_id"]

            def save(value, key):
                saved = request(
                    page_route + "/save",
                    "POST",
                    {
                        "version_id": value["version_id"],
                        "expected_head_version_id": value["head_version_id"],
                        "expected_content_hash": value["content_hash"],
                    },
                    key=key,
                )
                assert saved["state"] == "saved" and saved["content_state"] == "valid", saved
                return saved

            saved = save(draft, "p5-smoke-save")
            assert list(vault.rglob("*.md")) == [private]
            root = request(
                base + "/wiki/roots",
                "POST",
                {"path": str(vault)},
                native=True,
                key="p5-smoke-native-root",
            )

            def publish(value, target_hash, key):
                return request(
                    page_route + "/publish",
                    "POST",
                    {
                        "root_id": root["root_id"],
                        "version_id": value["version_id"],
                        "expected_content_hash": value["content_hash"],
                        "expected_target_hash": target_hash,
                    },
                    key=key,
                )

            publication = publish(saved, None, "p5-smoke-publish")
            assert publication["state"] == "succeeded", publication
            target = vault / publication["relative_path"]
            assert (
                target.is_file()
                and hashlib.sha256(target.read_bytes()).hexdigest() == publication["target_hash"]
            )
            assert private.read_bytes() == private_bytes
            untouched = saved["sections"][1]
            delta_route, delta = workflow(
                "wiki_delta",
                "p5-smoke-p11",
                page_id=saved["page_id"],
                base_version_id=saved["version_id"],
                affected_section_ids=[saved["sections"][0]["section_id"]],
            )
            assert len(delta["result"]["patch"]["operations"]) == 1
            updated = request(delta_route + "/materialize", "POST", {}, key="p5-delta-01")
            assert "更新补充" in updated["sections"][0]["text"] and "更新补充" in updated["diff"]
            assert {k: v for k, v in updated["sections"][1].items() if k != "passage_id"} == {
                k: v for k, v in untouched.items() if k != "passage_id"
            }
            updated = save(updated, "p5-smoke-delta-save")
            published = publish(updated, publication["target_hash"], "p5-smoke-update-export")
            assert published["state"] == "succeeded", published
            external_bytes = target.read_bytes() + "\n外部个人修改，必须保留。\n".encode()
            target.write_bytes(external_bytes)
            current = request(page_route)
            assert current["file"]["state"] == "modified" and current["content_state"] == "valid"
            observed = request(page_route + "/inspect-file", "POST", {}, key="p5-smoke-inspect")
            assert observed["source_verified"] is False and "外部个人修改" in observed["diff"]
            conflict = publish(updated, published["target_hash"], "p5-smoke-protect-external")
            assert conflict["state"] == "conflict", conflict
            assert target.read_bytes() == external_bytes and private.read_bytes() == private_bytes
            assert request(base + "/graph/projection", "POST", {}) == graph
            assert stub.calls == {"P09": 1, "P10": 1, "P11": 1} and not stub.errors

            # Explicitly registered external text is a separate personal source. Its
            # metadata, purpose grant and frozen selection never grant Wiki write access.
            reading_root = request(
                "/integrations/obsidian/roots",
                "POST",
                {"project_id": project_id, "path": str(vault)},
                key="p5-read-root",
            )
            external_base = base + "/external-documents"
            preview = request(
                external_base + "/preview?include_personal=true",
                "POST",
                {"root_id": reading_root["id"], "relative_path": "private.md"},
            )
            assert preview["source_verified"] is False
            external = request(
                external_base + "?include_personal=true",
                "POST",
                {
                    "root_id": reading_root["id"],
                    "relative_path": "private.md",
                    "expected_sha256": preview["sha256"],
                    "title": "独立个人来源",
                    "attribution": "user_view",
                },
                key="p5-external-register",
            )
            assert (
                external["source_verified"] is False and external["content_state"] == "unverified"
            )
            external_id = external["document_id"]
            assert request(external_base)["items"] == []
            request(
                external_base + "/" + external_id + "?include_personal=true&purpose=model",
                expected_error="EXTERNAL_SOURCE_NOT_AUTHORIZED",
            )
            permission_path = "/integrations/obsidian/" + reading_root["id"] + "/query-permissions"
            request(
                permission_path,
                "PUT",
                {"allow_local": True, "allow_model": True},
                key="p5-external-allow",
            )
            selected_external = request(
                base + "/workflows/prepare",
                "POST",
                {
                    "kind": "wiki_synthesis",
                    "query": {
                        "project_id": project_id,
                        "question": "区分个人观点与论文证据",
                        "paper_ids": papers,
                        "include_personal": True,
                        "purpose": "model",
                    },
                    "personal_sources": {
                        "version": "p5-personal-sources-1",
                        "note_ids": [],
                        "annotation_ids": [],
                        "external_version_ids": [external["version_id"]],
                    },
                },
                key="p5-external-prepare",
            )
            assert (
                selected_external["status"] == "prepared"
                and selected_external["request_count"] == 0
            )
            request(
                permission_path,
                "PUT",
                {"allow_local": False, "allow_model": False},
                key="p5-external-revoke",
            )
            assert request(external_base + "?include_personal=true")["items"] == []
            assert external_id not in str(request(base + "/lint/documents?include_personal=true"))
            invalidated = request(base + "/workflows/" + selected_external["id"])
            assert invalidated["error_code"] and invalidated["result"] is None
            assert private.read_bytes() == private_bytes
            assert request(base + "/graph/projection", "POST", {}) == graph
            assert stub.calls == {"P09": 1, "P10": 1, "P11": 1} and not stub.errors
        finally:
            stop(process)

        process, port = start()
        try:
            assert request(page_route)["saved_version_id"] == updated["version_id"]
            assert request(page_route)["file"]["state"] == "modified"
            assert request(route)["result"] == synthesis["result"]
            restored_delta = request(delta_route)
            assert restored_delta["result"] == delta["result"], {
                key: restored_delta[key]
                for key in ("status", "historical_status", "error_code", "error")
            }
            assert request(base + "/lint/runs/" + report["id"])["processed"] == report["total"]
            assert request(external_base + "?include_personal=true")["items"] == []
            revoked_workflow = request(base + "/workflows/" + selected_external["id"])
            assert revoked_workflow["error_code"] and revoked_workflow["result"] is None
            assert target.read_bytes() == external_bytes and private.read_bytes() == private_bytes
            assert all(path.read_bytes() == original for path, original in fixtures.items())
            recovered = request(
                base + "/wiki/publications/" + conflict["operation_id"] + "/recover",
                "POST",
                {},
                key="p5-smoke-recover-conflict",
            )
            assert recovered["state"] == "conflict" and target.read_bytes() == external_bytes
            assert stub.calls == {"P09": 1, "P10": 1, "P11": 1} and not stub.errors
        finally:
            stop(process)
        with closing(sqlite3.connect(data / "researchgraph.sqlite3")) as connection:
            assert connection.execute("SELECT count(*) FROM p5_model_runs").fetchone()[0] == 3
            assert connection.execute("SELECT count(*) FROM model_runs").fetchone()[0] == 0
    return {
        "packaged_engine": "not_tested_source_mode" if source_python else "passed",
        "source_engine": "passed" if source_python else "not_used",
        "p09_p10_p11_configured_http_sse": "passed",
        "stub_requests_by_prompt": stub.calls,
        "model_request_ledger": 3,
        "lint_http_batch_size": 100,
        "lint_read_only_repair_plans_excluded_from_model_input": "passed",
        "complete_two_paper_raw_scope": "passed",
        "lint_synthesis_materialize_save_publish": "passed",
        "selected_section_delta_diff_untouched_section": "passed",
        "native_token_output_authorization": "passed_api_boundary_not_native_dialog",
        "external_edit_conflict_snapshot_restart_recovery": "passed",
        "external_registration_selection_purpose_revocation": "passed_zero_extra_model_slots",
        "source_private_files_science_graph_preserved": "passed",
        "developer_tools_removed_from_child_path": True,
        "real_model_scientific_quality": "not_tested_synthetic_protocol_only",
        "real_model_requests": 0,
        "user_native_feedback_clean_machine": "not_tested",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--executable", type=Path)
    target.add_argument("--source-python", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.executable.resolve() if args.executable else None,
                source_python=args.source_python.resolve() if args.source_python else None,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
