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

import pymupdf


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
            source_fixture = (
                Path(__file__).resolve().parents[1] / "tests/fixtures/pdf/two-pages.pdf"
            )
            fixture = Path(directory) / "generated-fixture.pdf"
            with pymupdf.open(source_fixture) as document:
                document[-1].insert_text(
                    (40, 400),
                    "Our synthetic shared memory method improves task accuracy.",
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
            claim = next(n for n in knowledge["items"] if n["kind"] == "claim")
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
                left = next(n for n in knowledge["items"] if n["kind"] == kind)
                right = next(n for n in other_nodes if n["kind"] == kind)
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
            settings = request(port, model_route + "/models")
            assert settings["roles"] == roles and settings["profiles"] == [profile]
            assert request(port, f"/revisions/{revision_id}/chunks")["items"] == chunks
            assert request(port, f"/papers/{paper_id}")["sources"][0] == relocated
            assert request(port, graph_route + "/layout") == layout
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
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.executable.resolve()), ensure_ascii=False, indent=2))
