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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pymupdf


class QueryProtocolStub:
    """Parent-owned loopback SSE protocol fixture, never a real model service.

    The distributed engine uses its ordinary ConfiguredProvider HTTP path. No
    provider injection, production Mock switch, credential, or external API is used.
    """

    model = "synthetic-p07-protocol-only"

    def __init__(self) -> None:
        self.calls = 0
        self.errors: list[str] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format, *_args):
                pass

            def send(self, payload: bytes, content_type: str, status: int = 200):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                if self.path != "/v1/models":
                    self.send(b"{}", "application/json", 404)
                    return
                self.send(json.dumps({"data": [{"id": owner.model}]}).encode(), "application/json")

            def do_POST(self):
                try:
                    assert self.path == "/v1/chat/completions", "Unexpected model route"
                    assert not self.headers.get("Authorization"), "Fixture must use no credentials"
                    length = int(self.headers["Content-Length"])
                    assert 0 < length < 2_000_000, "Unexpected model request size"
                    body = json.loads(self.rfile.read(length))
                    owner.calls += 1
                    assert body["model"] == owner.model and body["stream"] is True
                    assert body["response_format"] == {"type": "json_object"}
                    data = json.loads(body["messages"][1]["content"])
                    inputs = data["untrusted_source_data"]
                    context = inputs["evidence_context"]
                    assert len(inputs["input_context_hash"]) == 64
                    assert "source_refs" in json.dumps(data["output_schema"])
                    reference = next(
                        ref
                        for ref in context["references"]
                        if ref["type"] == "chunk" and "shared memory" in ref["quote"].lower()
                    )
                    content = json.dumps(
                        {
                            "passages": [
                                {
                                    "text": "合成原文报告共享记忆方法改善任务准确率。",
                                    "attribution": "model_synthesis",
                                    "source_refs": [reference["ref"]],
                                    "limitations": ["合成协议验收，不是科学质量验证"],
                                }
                            ],
                            "limitations": ["仅引用这次请求提供的合成原文"],
                        },
                        ensure_ascii=False,
                    )
                    middle = len(content) // 2
                    events = [
                        {"choices": [{"index": 0, "delta": {"content": part}}]}
                        for part in (content[:middle], content[middle:])
                    ]
                    events.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
                    events.append(
                        {
                            "choices": [],
                            "usage": {
                                "prompt_tokens": 121,
                                "completion_tokens": 37,
                                "total_tokens": 158,
                            },
                        }
                    )
                    stream = (
                        "".join(
                            "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                            for event in events
                        )
                        + "data: [DONE]\n\n"
                    )
                    self.send(stream.encode("utf-8"), "text/event-stream; charset=utf-8")
                except Exception as error:
                    owner.errors.append(type(error).__name__ + ": " + str(error))
                    self.send(
                        b'{"error":"synthetic protocol assertion failed"}', "application/json", 500
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


def run(executable: Path | None, *, source_python: Path | None = None) -> dict[str, object]:
    if (executable is None) == (source_python is None):
        raise ValueError("Choose exactly one packaged executable or source Python")
    minimal_env = {
        k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if k in os.environ
    }
    minimal_env["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")
    token = secrets.token_urlsafe(48)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    if source_python:
        # Source mode is explicitly distinct from frozen-runtime acceptance.
        minimal_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "services/engine")
    with (
        QueryProtocolStub() as endpoint,
        tempfile.TemporaryDirectory(prefix="ResearchGraph 中文路径 ") as directory,
    ):
        data = Path(directory) / "project data"

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
            if path.endswith("/projection") and body is not None:
                body = {"include_test_data": True, **body}
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
            project_body = {
                "name": "中文项目",
                "description": "Smoke",
                "experience_mode": "legacy",
            }
            project = request(port, "/projects", "POST", project_body)
            assert request(port, "/projects", "POST", project_body) == project
            job = request(port, "/jobs", "POST", {"kind": "diagnostics"})
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                job = request(port, "/jobs/" + job["id"])
                if job["status"] == "succeeded":
                    break
                time.sleep(0.1)
            assert job["status"] == "succeeded", job
            source_fixture = (
                Path(__file__).resolve().parents[1] / "tests/fixtures/pdf/two-pages.pdf"
            )
            fixture = Path(directory) / "generated-fixture.pdf"
            shared_statement = "Our synthetic shared memory method improves task accuracy."
            with pymupdf.open(source_fixture) as document:
                document[-1].insert_text(
                    (40, 400),
                    shared_statement,
                    fontsize=8,
                )
                document.save(fixture)
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
            # Project model settings and role selection must work in the frozen runtime.
            model_route = "/settings"
            profile = request(
                port,
                model_route + "/models",
                "POST",
                {"name": "Offline acceptance", "provider": "mock", "model": "mock"},
            )
            assert not profile["has_api_key"] and "credential_ref" not in profile
            roles = {"extraction": profile["id"], "reasoning": profile["id"]}
            assert request(port, model_route + "/model-roles", "POST", roles)["roles"] == roles
            connection = request(port, model_route + f"/models/{profile['id']}/test", "POST")
            assert connection["connected"] and connection["valid_json"] and connection["mock"]
            # P2 packaged runtime: prompts must be bundled and writes must survive restart.
            extraction = completed(
                port,
                request(
                    port,
                    "/knowledge/extract",
                    "POST",
                    {
                        "document_version_id": revision_id,
                        "provider": "mock",
                        "pipeline": "legacy-v2",
                    },
                    key="extract-smoke",
                ),
            )
            assert extraction["result"]["provider"] == "mock"
            knowledge = request(port, f"/revisions/{revision_id}/knowledge")
            claim = next(
                n
                for n in knowledge["items"]
                if n["kind"] == "claim" and n["text"].strip() == shared_statement
            )
            detail = request(port, f"/knowledge/nodes/{claim['id']}")
            assert detail["evidence"] and detail["model_run"]["raw_output"]
            assert request(port, f"/evidence/{detail['evidence'][0]['id']}/preview")[
                "data_url"
            ].startswith("data:image/png;base64,")
            # A second synthetic source checks all P3 prompts in the frozen executable.
            other_pdf = Path(directory) / "comparison.pdf"
            other_pdf.write_bytes(fixture.read_bytes() + b"\n% Second synthetic source\n")
            second_import = completed(
                port,
                request(
                    port,
                    f"/projects/{project['id']}/papers/import/pdf",
                    "POST",
                    {"path": str(other_pdf), "mode": "managed"},
                    key="p3-import",
                ),
            )
            other_version = second_import["result"]["revision_id"]
            completed(
                port,
                request(
                    port,
                    "/knowledge/extract",
                    "POST",
                    {
                        "document_version_id": other_version,
                        "provider": "mock",
                        "pipeline": "legacy-v2",
                    },
                    key="p3-extract",
                ),
            )
            other_nodes = request(port, f"/revisions/{other_version}/knowledge")["items"]
            proposals = []
            for workflow, kind in (("relations", "claim"), ("alignments", "method")):
                # Extraction order follows evidence IDs, not PDF text order. Pair the
                # explicit shared fixture instead of unrelated first rows (NO_DECISION).
                left, right = [
                    next(
                        n
                        for n in nodes
                        if n["kind"] == kind and n["text"].strip() == shared_statement
                    )
                    for nodes in (knowledge["items"], other_nodes)
                ]
                inferred = completed(
                    port,
                    request(
                        port,
                        f"/knowledge/{workflow}/infer",
                        "POST",
                        {"source_id": left["id"], "target_id": right["id"], "provider": "mock"},
                        key="p3-" + workflow,
                    ),
                )
                proposal_id = inferred["result"]["proposal_id"]
                assert proposal_id, {"workflow": workflow, "result": inferred["result"]}
                proposal_detail = request(port, f"/knowledge/{workflow}/{proposal_id}")
                assert proposal_detail["proposal"]["review_status"] == "proposed"
                assert all(r["status"] == "succeeded" for r in proposal_detail["runs"])
                review = request(
                    port,
                    "/knowledge/semantic-reviews",
                    "POST",
                    {
                        "kind": "relation" if kind == "claim" else "alignment",
                        "proposal_id": proposal_id,
                        "expected_revision": 1,
                        "action": "accept",
                        "reason": "Synthetic packaged workflow check only",
                    },
                    key="p3-review-" + kind,
                )
                assert review["review_status"] == "accepted"
                proposals.append((workflow, proposal_id))
            graph = request(
                port, f"/graph/subgraph?project_id={project['id']}&focus_id={claim['id']}"
            )
            assert len(graph["relations"]) == 1
            # P3 writes advanced graph revision; P2 review must use the current revision.
            knowledge["graph_revision"] = graph["graph_revision"]
            reviewed = request(
                port,
                "/knowledge/reviews",
                "POST",
                {
                    "node_id": claim["id"],
                    "expected_revision": claim["revision"],
                    "expected_graph_revision": knowledge["graph_revision"],
                    "action": "reject",
                    "reason": "Mock output checked in packaged smoke",
                },
                key="review-smoke",
            )
            assert reviewed["review_status"] == "rejected"
            completed(
                port,
                request(
                    port,
                    "/knowledge/extract",
                    "POST",
                    {
                        "document_version_id": revision_id,
                        "provider": "mock",
                        "pipeline": "legacy-v2",
                    },
                    key="extract-repeat",
                ),
            )
            assert len(request(port, f"/revisions/{revision_id}/knowledge")["items"]) == len(
                knowledge["items"]
            )
            unified_body = {
                "document_version_id": other_version,
                "pipeline": "unified-v3",
                "provider": "mock",
            }
            unified = completed(
                port, request(port, "/knowledge/extract", "POST", unified_body, key="v3-extract")
            )
            assert unified["result"]["pipeline"] == "unified-v3"
            graph_route = f"/projects/{project['id']}/graph"
            projection = request(port, graph_route + "/projection", "POST", {})
            assert projection["nodes"] and all("payload" not in n for n in projection["nodes"])
            visible = next(n for n in projection["nodes"] if n["kind"] == "Method")
            node_detail = request(port, graph_route + "/nodes/" + visible["id"])
            assert node_detail["evidence"]
            layout_body = {
                "expected_version": 0,
                "positions": [{"node_id": visible["id"], "x": 44, "y": -17, "pinned": True}],
                "zoom": 0.8,
                "pan_x": 4,
                "pan_y": 8,
            }
            layout = request(port, graph_route + "/layout", "POST", layout_body)
            assert (
                request(port, graph_route + "/projection", "POST", {})["graph_revision"]
                == projection["graph_revision"]
            )
            translated = completed(
                port,
                request(
                    port,
                    graph_route + "/translate",
                    "POST",
                    {"provider": "mock", "node_ids": [visible["id"]]},
                    key="v3-translate",
                ),
            )
            assert translated["status"] == "succeeded"
            repeated = completed(
                port, request(port, "/knowledge/extract", "POST", unified_body, key="v3-repeat")
            )
            assert repeated["result"]["model_calls"] == 0
            reading_job = completed(
                port,
                request(
                    port,
                    "/knowledge/extract",
                    "POST",
                    {
                        "document_version_id": other_version,
                        "pipeline": "paper-reading-v1",
                        "provider": "mock",
                        "allow_network": False,
                    },
                    key="reading-extract",
                ),
            )
            assert reading_job["status"] == "succeeded", reading_job
            assert reading_job["result"]["ranking_protocol"] == "reading-ranking-keyed-1"
            assert (
                reading_job["result"]["ranking_completed_claims"]
                == reading_job["result"]["ranking_total_claims"]
                > 0
            )
            backbone = request(
                port,
                graph_route + "/projection",
                "POST",
                {
                    "view": "paper_backbone",
                    "kinds": ["Paper", "Claim", "Method"],
                },
            )
            assert backbone["contract_version"] == "reading-projection-2.0"
            assert any(e["relation"] == "HAS_CORE_CLAIM" for e in backbone["edges"])
            assert all(
                e["relation"] in {"HAS_CORE_CLAIM", "UNIT_MEMBER"}
                for e in backbone["edges"]
                if e["epistemic_status"] == "navigation"
            )
            assert all(
                e["relation"] == "HAS_CORE_CLAIM"
                for e in backbone["edges"]
                if next(n for n in backbone["nodes"] if n["id"] == e["source"])["kind"] == "Paper"
            )
            reading_paper = next(n["paper_id"] for n in backbone["nodes"] if n["kind"] == "Claim")
            reading_selection = request(port, f"/papers/{reading_paper}/graph-selection")
            # Q01-Q04 are local foundations: raw source retrieval and versioned
            # context work even when all model-derived fixture nodes are excluded.
            query_body = {"project_id": project["id"], "question": "shared memory"}
            query_route = f"/projects/{project['id']}/query"
            query_before = request(port, graph_route + "/projection", "POST", {})
            prepared = request(
                port, query_route + "/prepare", "POST", query_body, key="query-foundation-smoke"
            )
            assert prepared["status"] == "prepared", prepared
            assert prepared["snapshot"]["context"]["references"]
            assert prepared["snapshot"]["model"] is None  # Mock is not a production role.
            assert not prepared["snapshot"]["prompt"]["generation_enabled"]
            assert (
                request(
                    port, query_route + "/prepare", "POST", query_body, key="query-foundation-smoke"
                )
                == prepared
            )
            assert request(
                port, query_route + "/runs/" + prepared["query_id"] + "/validate", "POST"
            )["valid"]
            assert request(port, graph_route + "/projection", "POST", {}) == query_before
            # Q05/Q07: parent-owned synthetic HTTP/SSE endpoint exercises the
            # actual configured-provider transport and bundled P07 prompt. This
            # is offline protocol acceptance, never real-model quality evidence.
            query_profile = request(
                port,
                model_route + "/models",
                "POST",
                {
                    "name": "Synthetic loopback protocol acceptance",
                    "provider": "local",
                    "base_url": endpoint.base_url,
                    "model": endpoint.model,
                    "parameters": {"timeout_seconds": 15, "json_mode": True},
                },
                key="query-local-profile",
            )
            assert not query_profile["has_api_key"]
            roles["reasoning"] = query_profile["id"]
            assert (
                request(port, model_route + "/model-roles", "POST", roles, key="query-local-role")[
                    "roles"
                ]
                == roles
            )
            generation_body = {**query_body, "purpose": "model", "include_personal": False}
            query_prepared = request(
                port,
                query_route + "/prepare",
                "POST",
                generation_body,
                key="query-p07-prepare",
            )
            assert query_prepared["status"] == "prepared", query_prepared
            assert query_prepared["snapshot"]["model"]["provider"] == "local"
            assert query_prepared["presentation"]["references"]
            assert all(
                view["title"] and view["original"]
                for view in query_prepared["presentation"]["references"].values()
                if view["paper_id"]
            )
            assert endpoint.calls == 0
            query_run_route = query_route + "/runs/" + query_prepared["query_id"]
            generated = completed(
                port,
                request(
                    port,
                    query_run_route + "/generate",
                    "POST",
                    {"allow_network": True, "continue_requested": False},
                    key="query-p07-generate",
                ),
            )
            answer_view = request(port, query_run_route + "/answer")
            assert answer_view["status"] == "succeeded", answer_view
            answer = answer_view["answer"]
            assert answer["status"] == "validated" and answer["passages"]
            assert answer["passages"][0]["attribution"] == "model_synthesis"
            assert answer_view["request_count"] == endpoint.calls == 1, endpoint.errors
            assert answer_view["model_runs"][0]["usage"]["total_tokens"] == 158
            assert answer_view["model_runs"][0]["finish_reason"] == "stop"
            assert request(port, graph_route + "/projection", "POST", {}) == query_before
            replayed = request(
                port,
                query_run_route + "/generate",
                "POST",
                {"allow_network": True, "continue_requested": True},
                key="query-p07-completed-replay",
            )
            assert replayed["id"] == generated["id"] and endpoint.calls == 1
            save_body = {
                "source_query_id": query_prepared["query_id"],
                "answer_version_id": answer["answer_version_id"],
                "selected_passage_refs": [answer["passages"][0]["local_ref"]],
                "expected_input_hash": answer["input_hash"],
                "kind": "synthesis",
                "target_document_id": None,
                "base_version_id": None,
            }
            query_saved = request(
                port, query_run_route + "/save", "POST", save_body, key="query-p07-save"
            )
            assert query_saved["content_state"] == "valid"
            assert query_saved["passages"][0]["dependencies"]
            assert (
                request(port, query_run_route + "/save", "POST", save_body, key="query-p07-save")
                == query_saved
            )
            assert len(request(port, query_route + "/saved")["items"]) == 1
            derived = request(port, query_route + "/derived-graph")
            assert any(node.get("saved_id") == query_saved["saved_id"] for node in derived["nodes"])
            assert derived["edges"] and all(
                edge["relation"] == "DERIVED_FROM"
                and edge["epistemic_status"] == "derived_reference"
                for edge in derived["edges"]
            )
            after_save = request(port, graph_route + "/projection", "POST", {})
            assert after_save["nodes"] == query_before["nodes"]
            assert after_save["edges"] == query_before["edges"]
            saved_route = query_route + "/saved/" + query_saved["saved_id"]
            annotation_body = {
                "annotation": "个人阅读批注：核对方法条件；不是论文作者结论。",
                "expected_revision": query_saved["metadata_revision"],
            }
            query_saved = request(
                port,
                saved_route + "/annotation",
                "PUT",
                annotation_body,
                key="query-saved-annotation",
            )
            assert query_saved["annotation"] == annotation_body["annotation"]
            assert query_saved["metadata_revision"] == 1
            assert request(port, graph_route + "/projection", "POST", {}) == after_save
            assert endpoint.calls == 1 and not endpoint.errors
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
            assert request(port, query_route + "/runs/" + prepared["query_id"]) == prepared
            settings = request(port, model_route + "/models")
            assert settings["roles"] == roles
            assert {row["id"] for row in settings["profiles"]} == {
                profile["id"],
                query_profile["id"],
            }
            assert request(port, query_run_route + "/answer") == answer_view
            assert request(port, query_route + "/saved")["items"] == [query_saved]
            assert request(port, query_route + "/saved/" + query_saved["saved_id"]) == query_saved
            assert request(port, query_route + "/derived-graph") == derived
            assert (
                request(
                    port,
                    query_run_route + "/generate",
                    "POST",
                    {"allow_network": True, "continue_requested": True},
                    key="query-p07-restart-replay",
                )["id"]
                == generated["id"]
            )
            assert (
                request(port, query_run_route + "/save", "POST", save_body, key="query-p07-save")
                == query_saved
            )
            assert endpoint.calls == 1 and not endpoint.errors
            assert request(port, f"/revisions/{revision_id}/chunks")["items"] == chunks
            assert request(port, f"/papers/{paper_id}")["sources"][0] == relocated
            assert request(port, graph_route + "/layout") == layout
            assert request(port, f"/papers/{reading_paper}/graph-selection") == reading_selection
            assert (
                request(port, graph_route + "/nodes/" + visible["id"])["display"][
                    "translation_status"
                ]
                == "machine_unreviewed"
            )
            persisted = request(port, f"/knowledge/nodes/{claim['id']}")
            assert persisted["node"]["review_status"] == "rejected"
            assert len(persisted["reviews"]) == 1 and persisted["model_run"]["raw_output"]
            for workflow, proposal_id in proposals:
                persisted_proposal = request(port, f"/knowledge/{workflow}/{proposal_id}")
                assert persisted_proposal["proposal"]["review_status"] == "accepted"
                assert len(persisted_proposal["reviews"]) == 1
                assert persisted_proposal["proposal"]["stale"] == (workflow == "relations")
            removed = request(
                port,
                saved_route + "/remove",
                "POST",
                {"expected_revision": query_saved["metadata_revision"]},
                key="query-saved-remove",
            )
            assert removed["removed_at"] and removed["metadata_revision"] == 2
            assert request(port, query_route + "/saved")["items"] == []
            assert request(port, query_route + "/derived-graph") == {"nodes": [], "edges": []}
            assert request(port, graph_route + "/projection", "POST", {}) == after_save
            assert request(port, query_run_route + "/answer") == answer_view
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
            assert request(port, query_route + "/saved")["items"] == []
            assert request(port, query_route + "/derived-graph") == {"nodes": [], "edges": []}
            assert request(port, query_run_route + "/answer") == answer_view
            assert request(port, graph_route + "/projection", "POST", {}) == after_save
            assert endpoint.calls == 1 and not endpoint.errors
        finally:
            process.stdin.close()
            try:
                assert process.wait(timeout=10) == 0
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    return {
        "packaged_engine": "not_tested_source_mode" if source_python else "passed",
        "source_engine": "passed" if source_python else "not_used",
        "query_p07_configured_sse_protocol_stub_save_restart": "passed",
        "query_readable_sources_annotation_remove_restart": "passed",
        "query_protocol_stub_calls": endpoint.calls,
        "query_real_model_quality": "not_tested_offline_protocol_stub_only",
        "query_local_context_replay_idempotency_restart_no_science_write": "passed",
        "reading_pipeline_backbone_selection_restart": "passed",
        "keyed_ranking_protocol_complete": "passed",
        "unified_projection_translation_layout_restart": "passed",
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
        "knowledge_extraction_review_preview_restart": "passed",
        "global_model_settings_roles_mock_connection_restart": "passed",
        "p03_p04_p05_graph_review_restart_and_stale_source": "passed",
        "clean_windows_machine": "not_tested",
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
