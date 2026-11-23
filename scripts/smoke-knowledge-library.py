"""Exercise K1-K3 through real sidecar HTTP and an anonymous loopback SSE fixture.

Only 127.0.0.1 receives model requests. Synthetic usage verifies bookkeeping,
not scientific correctness or actual token measurement. All data is temporary.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import queue
import secrets
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

REPORT_DETAIL = {
    "source_zh": "新增匿名论文明确描述了用于合成任务的共享记忆方法。",
    "target_zh": "较早的匿名论文也介绍共享记忆方法，使用该论文自身摘录作为依据。",
    "comparison_zh": "两个摘录都说明共享记忆方法的目标用途，可在这一维度并列阅读。",
    "conditions_zh": "合成正文不包含可核对的实验数据、指标或基线，证据限于方法用途。",
    "follow_up_zh": "若后续获得完整实验材料，可逐项核查任务输入与测量条件。",
}


def harness() -> Any:
    spec = importlib.util.spec_from_file_location(
        "knowledge_smoke_harness", Path(__file__).with_name("smoke-section-reading.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Synthetic sidecar harness is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def sidecar(command: list[str], folder: Path, token: str, env: dict[str, str]):
    output: queue.Queue[str] = queue.Queue()
    with (folder / "sidecar-stderr.log").open("a+", encoding="utf-8") as stderr:
        child = subprocess.Popen(
            command + [str(folder / "data")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            env=env,
            text=True,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        try:
            assert child.stdin is not None and child.stdout is not None
            threading.Thread(
                target=lambda: output.put(child.stdout.readline()), daemon=True
            ).start()
            child.stdin.write(json.dumps({"token": token}) + "\n")
            child.stdin.flush()
            try:
                line = output.get(timeout=45).strip()
            except queue.Empty:
                raise AssertionError("Sidecar startup exceeded 45 seconds") from None
            assert line.startswith("RGS_READY "), line
            ready = json.loads(line[10:])
            yield f"http://127.0.0.1:{ready['port']}/api/v1"
        finally:
            if child.stdin is not None and not child.stdin.closed:
                child.stdin.close()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


def run(executable: Path | None, source_python: Path | None) -> dict[str, Any]:
    if (executable is None) == (source_python is None):
        raise ValueError("Choose one packaged executable or source Python")
    shared = harness()

    class KnowledgeProvider(shared.SyntheticProvider):
        def respond(self, body: dict[str, Any]) -> tuple[dict[str, Any], str]:
            assert body.get("model") == shared.MODEL and body.get("stream") is True
            assert body.get("stream_options", {}).get("include_usage") is True
            assert not body.get("tools")
            wrapper = json.loads(body["messages"][1]["content"])
            data, schema = wrapper["untrusted_source_data"], wrapper["output_schema"]
            if schema["properties"]["schema_version"]["const"] == "paper-knowledge-1":
                assert "All supplied paper titles" in body["messages"][0]["content"]
                assert set(schema["$defs"]["KnowledgeExcerptRef"]["properties"]) == {"excerpt_id"}
                assert all("text" not in source for source in data["sources"])
                excerpt = next(
                    quote
                    for source in data["sources"]
                    for quote in source["excerpts"]
                    if "shared memory method" in quote["text"]
                )
                return {
                    "schema_version": "paper-knowledge-1",
                    "paper_card": {
                        "research_question": "",
                        "motivation": "",
                        "method_summary": "合成文档描述共享记忆方法。",
                        "contributions": [],
                        "main_findings": [],
                        "limitations": ["仅供软件回归，非真实科学结果。"],
                    },
                    "graph": {
                        "nodes": [
                            {
                                "id": "n1",
                                "type": "METHOD",
                                "label_zh": "合成共享记忆方法",
                                "label_en": "Shared memory method",
                                "description_zh": "合成文档描述的方法。",
                                "basis": "EXPLICIT",
                                "source_refs": [{"excerpt_id": excerpt["excerpt_id"]}],
                            }
                        ],
                        "edges": [],
                    },
                }, "knowledge_extract"
            assert schema["properties"]["schema_version"]["const"] == "knowledge-connections-3"
            assert len(data["candidates"]) == 1
            assert "connection_contract" not in data
            source, target = data["source"], data["candidates"][0]
            left = next(n for n in source["content"]["graph"]["nodes"] if n["type"] == "METHOD")
            right = next(n for n in target["content"]["graph"]["nodes"] if n["type"] == "METHOD")
            return {
                "schema_version": "knowledge-connections-3",
                "relations": [
                    {
                        "ref": "r1",
                        "target_ref": target["ref"],
                        "source_node_id": left["id"],
                        "target_node_id": right["id"],
                        "type": "RELATED_METHOD",
                        "explanation_zh": "双方合成材料都描述共享记忆方法。",
                        "limitations_zh": "这是软件夹具，不据此推断实验优劣或作者继承关系。",
                        "source_ref_ids": [left["source_refs"][0]["source_id"]],
                        "target_ref_ids": [right["source_refs"][0]["source_id"]],
                        "detail": REPORT_DETAIL,
                    }
                ],
                "summary": [
                    {"text_zh": "两篇合成文档的方法存在可回查的联系。", "relation_refs": ["r1"]}
                ],
                "no_relation_reason_zh": None,
            }, "knowledge_connect"

    root = Path(__file__).resolve().parents[1]
    env = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA")
        if key in os.environ
    }
    env["PATH"] = str(Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32")
    if source_python:
        env["PYTHONPATH"] = str(root / "services" / "engine")
        command = [str(source_python), "-m", "researchgraph", "--data-dir"]
    else:
        command = [str(executable), "--data-dir"]
    token = secrets.token_urlsafe(48)
    request = shared.request
    with (
        tempfile.TemporaryDirectory(prefix="rgs-knowledge-smoke-") as folder,
        KnowledgeProvider() as provider,
    ):
        isolated = Path(folder)
        pdfs = [isolated / "anonymous-a.pdf", isolated / "anonymous-b.pdf"]
        shared.make_pdf(pdfs[0])
        pdfs[1].write_bytes(pdfs[0].read_bytes().replace(b"Reading Study", b"Reading Trial"))
        hashes = [hashlib.sha256(pdf.read_bytes()).hexdigest() for pdf in pdfs]
        assert hashes[0] != hashes[1]

        def wait_for_report(base: str, expected: str) -> dict[str, Any]:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                items = request(base, token, "GET", "/knowledge/reports")["items"]
                matching = [item for item in items if item["status"] == expected]
                if matching:
                    return matching[0]
                time.sleep(0.1)
            runs = request(base, token, "GET", "/knowledge/runs")
            raise AssertionError(
                f"Knowledge report {expected} missing: {runs}; provider={provider.errors}"
            )

        with sidecar(command, isolated, token, env) as base:
            assert request(base, token, "GET", "/health")["schema_version"] == "lite0020"
            project = request(base, token, "POST", "/projects", {"name": "Anonymous K1-K3 smoke"})
            connection = request(
                base,
                token,
                "POST",
                "/settings/connections",
                {
                    "name": "Loopback knowledge fixture",
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
                    "name": "Synthetic knowledge model",
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
                {"knowledge_extract": profile["id"], "knowledge_connect": profile["id"]},
            )
            request(
                base,
                token,
                "PATCH",
                "/knowledge/library",
                {
                    "auto_collect": True,
                    "auto_connect": True,
                    "allow_network": True,
                    "max_input_tokens": None,
                    "max_output_tokens": None,
                    "max_requests_per_run": None,
                    "total_request_limit": 3,
                },
            )
            for index, pdf in enumerate(pdfs):
                imported = request(
                    base,
                    token,
                    "POST",
                    f"/projects/{project['id']}/papers/import/pdf",
                    {"path": str(pdf), "mode": "reference"},
                )
                shared.wait_job(base, token, imported["id"])
                report = wait_for_report(base, "no_candidates" if index == 0 else "completed")
            assert len(report["relations"]) == 1 and len(report["summary"]) == 1
            relation = report["relations"][0]
            assert relation["explanation_zh"] == "双方合成材料都描述共享记忆方法。"
            assert relation["detail"] == REPORT_DETAIL
            for side in ("source", "target"):
                assert relation[side + "_refs"]
                for ref in relation[side + "_refs"]:
                    assert ref["quote"] in ref["source"]["text"]
            assert (
                report["coverage"]["eligible"]
                == report["coverage"]["selected"]
                == report["coverage"]["compared"]
                == 1
            )
            library = request(base, token, "GET", "/knowledge/papers")
            assert library["total"] == 2
            for paper in library["items"]:
                assert paper["current_version"]["evidence_status"] == "grounded"
                assert paper["current_version"]["source_kind"] == "local_revision"
            before = list(provider.calls)
            for path in (
                "/knowledge/library",
                "/knowledge/papers",
                "/knowledge/reports",
                "/knowledge/reports/" + report["id"],
                "/knowledge/export",
                "/knowledge/runs",
            ):
                request(base, token, "GET", path)
            settings = request(base, token, "GET", "/knowledge/library")["settings"]
            for name in ("max_input_tokens", "max_output_tokens", "max_requests_per_run"):
                assert settings[name] is None
            assert settings["total_request_limit"] == 3
            usage = request(base, token, "GET", "/knowledge/usage")
            assert (
                provider.calls
                == before
                == ["knowledge_extract", "knowledge_extract", "knowledge_connect"]
            )
            assert not provider.errors
            assert (
                usage["calls"],
                usage["input_tokens"],
                usage["output_tokens"],
                usage["total_tokens"],
            ) == (3, 69, 123, 192), usage
            request(
                base,
                token,
                "PATCH",
                "/knowledge/reports/" + report["id"],
                {"read": True, "note": "synthetic private note"},
            )

        with sidecar(command, isolated, token, env) as base:
            assert request(base, token, "GET", "/knowledge/library")["settings"] == settings
            restored = request(base, token, "GET", "/knowledge/reports/" + report["id"])
            assert restored["relations"] == report["relations"] and restored["read"] is True
            assert restored["note"] == "synthetic private note" and not restored["stale"]
            assert request(base, token, "GET", "/knowledge/papers")["total"] == 2
            assert request(base, token, "GET", "/knowledge/usage")["calls"] == 3
            assert provider.calls == before and not provider.errors
        assert [hashlib.sha256(pdf.read_bytes()).hexdigest() for pdf in pdfs] == hashes
        return {
            "status": "passed",
            "sidecar": "packaged" if executable else "source",
            "schema_version": "lite0020",
            "real_model_calls": 0,
            "non_loopback_requests": 0,
            "synthetic_extract_requests": 2,
            "synthetic_connect_requests": 1,
            "automatic_no_candidate_reports": 1,
            "saved_grounded_papers": 2,
            "bidirectional_grounded_relations": len(report["relations"]),
            "detailed_report_saved_and_reloaded": True,
            "get_extra_requests": 0,
            "restart_extra_requests": 0,
            "unlimited_budgets_persisted": True,
            "finite_cumulative_request_limit": 3,
            "synthetic_input_tokens": 69,
            "synthetic_output_tokens": 123,
            "synthetic_total_tokens": 192,
            "usage_kind": "synthetic SSE fixture; not actual model usage",
            "cost_known": False,
            "anonymous_pdfs_unchanged": True,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--executable", type=Path)
    target.add_argument("--source-python", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.executable, args.source_python), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
