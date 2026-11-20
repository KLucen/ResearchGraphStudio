"""Exercise real sidecar A02/A03 HTTP transport against an isolated SSE fixture.

All model traffic goes to a server bound to 127.0.0.1. The fixed usage values
are synthetic test data, never measurements of a real model or translation
quality. No API key or OS credential is read, created, or changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MODEL = "synthetic-section-reading"
SYNTHETIC_USAGE = {"prompt_tokens": 23, "completion_tokens": 41, "total_tokens": 64}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(base: str, token: str, method: str, path: str, body: Any = None) -> Any:
    if urlsplit(base).hostname != "127.0.0.1":
        raise ValueError("Smoke requests must stay on loopback")
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Idempotency-Key", secrets.token_hex(12))
    with OPENER.open(req, timeout=20) as response:
        return json.loads(response.read())


def make_pdf(path: Path) -> str:
    """Write a tiny, wholly invented PDF with no third-party PDF dependency."""
    lines = [
        (18, 740, "Synthetic Reading Study"),
        (14, 700, "1 Introduction"),
        (11, 665, "We propose a shared memory method for a synthetic study."),
        (11, 625, "The method records two observations and preserves uncertainty."),
        (11, 585, "No real experimental findings are asserted in this test document."),
    ]
    stream = "\n".join(
        f"BT /F1 {size} Tf 60 {y} Td ({text}) Tj ET" for size, y, text in lines
    ).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    start_xref = len(content)
    content.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{start_xref}\n%%EOF\n".encode()
    )
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


class SyntheticProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.errors: list[str] = []
        self.metadata_requests = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"

    def __enter__(self) -> SyntheticProvider:
        self.thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: Any) -> None:
                pass

            def send_body(self, code: int, body: bytes, content_type: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()

            def do_GET(self) -> None:
                if self.path != "/v1/models" or self.client_address[0] != "127.0.0.1":
                    self.send_body(404, b"{}", "application/json")
                    return
                fixture.metadata_requests += 1
                self.send_body(
                    200,
                    json.dumps(
                        {
                            "data": [
                                {"id": MODEL, "context_window": 32768, "max_output_tokens": 8192}
                            ]
                        }
                    ).encode(),
                    "application/json",
                )

            def do_POST(self) -> None:
                try:
                    assert self.path == "/v1/chat/completions"
                    assert self.client_address[0] == "127.0.0.1"
                    assert not self.headers.get("Authorization"), "Synthetic provider needs no key"
                    size = int(self.headers.get("Content-Length", "0"))
                    assert 0 < size <= 2_000_000
                    body = json.loads(self.rfile.read(size))
                    result, kind = fixture.respond(body)
                    fixture.calls.append(kind)
                    raw = json.dumps(result, ensure_ascii=False)
                    events = []
                    for start in range(0, len(raw), 83):
                        events.append(
                            {
                                "id": "synthetic-stream",
                                "object": "chat.completion.chunk",
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": raw[start : start + 83]},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                        )
                    events.append(
                        {
                            "id": "synthetic-stream",
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                            "usage": SYNTHETIC_USAGE,
                        }
                    )
                    sse = "".join(
                        "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                        for event in events
                    )
                    self.send_body(200, (sse + "data: [DONE]\n\n").encode(), "text/event-stream")
                except Exception as exc:
                    fixture.errors.append(f"{type(exc).__name__}: {exc}")
                    self.send_body(
                        400, b'{"error":"synthetic fixture assertion failed"}', "application/json"
                    )

        return Handler

    def respond(self, body: dict[str, Any]) -> tuple[dict[str, Any], str]:
        assert body.get("model") == MODEL
        assert body.get("stream") is True
        assert body.get("stream_options", {}).get("include_usage") is True
        assert not body.get("tools")
        messages = body["messages"]
        assert len(messages) == 2 and messages[0]["role"] == "system"
        wrapper = json.loads(messages[1]["content"])
        data, schema = wrapper["untrusted_source_data"], wrapper["output_schema"]
        assert set(data) <= {
            "paper_title",
            "section_title",
            "section_path",
            "range_label",
            "scope",
            "paragraphs",
            "allowed_graph_nodes",
            "task",
            "key_points",
            "self_assessment",
            "user_explanation",
        }
        paragraphs = data["paragraphs"]
        assert paragraphs and all(set(p) == {"paragraph_id", "text_en"} for p in paragraphs)
        assert len({p["paragraph_id"] for p in paragraphs}) == len(paragraphs)
        assert all(
            "text_en" not in item.get("properties", {}) for item in schema.get("$defs", {}).values()
        )
        if schema["title"] == "SectionReadingAnalysis":
            assert "不重复输出英文全文" in messages[0]["content"]
            assert data["allowed_graph_nodes"] == []
            result = {
                "schema_version": "section_reading_analysis.v1",
                "paragraphs": [
                    {
                        "paragraph_id": p["paragraph_id"],
                        "translation_zh": (
                            "这是匿名合成文档的中文测试译文；方法采用共享记忆并保留不确定性。"
                        ),
                        "paragraph_function": "EXPLAIN_METHOD",
                        "logic_role_zh": "说明当前测试范围中的方法和限定条件。",
                        "critical_note_zh": "本例仅验证程序流程，不代表真实论文结论。",
                        "reading_question_zh": None,
                        "highlights": [
                            {"type": "METHOD", "quote_en": p["text_en"][:20], "occurrence_index": 0}
                        ],
                        "related_graph_node_ids": [],
                    }
                    for p in paragraphs
                ],
                "section_argument": {
                    "logic_chain_zh": ["提出合成研究场景。", "描述方法并保留不确定性。"],
                    "core_claim_zh": "当前范围介绍合成测试方法。",
                    "strong_point_zh": None,
                    "question_to_verify_zh": "实际实验依据仍需查看真实材料。",
                },
            }
            assert all("text_en" not in p for p in result["paragraphs"])
            return result, "A02"
        assert schema["title"] == "UnderstandingCheck"
        assert data["self_assessment"] == "PARTIAL" and data["user_explanation"]
        return {
            "check_result": "ADEQUATE",
            "correct_points_zh": ["复述保留了方法与不确定性。"],
            "missing_or_mistaken_zh": [],
            "feedback_zh": "合成理解检查通过；这不是实际科学质量评估。",
            "follow_up_question_zh": "该方法依赖什么条件？",
        }, "A03"


def wait_job(base: str, token: str, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = request(base, token, "GET", f"/jobs/{job_id}")
        if result["status"] not in {"queued", "running"}:
            assert result["status"] == "succeeded", result
            return result
        time.sleep(0.1)
    raise AssertionError("Synthetic sidecar job did not finish within 45 seconds")


def run(executable: Path | None, source_python: Path | None) -> dict[str, Any]:
    if (executable is None) == (source_python is None):
        raise ValueError("Choose exactly one packaged executable or source Python")
    root = Path(__file__).resolve().parents[1]
    token = secrets.token_urlsafe(48)
    env = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA")
        if key in os.environ
    }
    env["PATH"] = str(Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32")
    if source_python is not None:
        env["PYTHONPATH"] = str(root / "services" / "engine")
        command = [str(source_python), "-m", "researchgraph", "--data-dir"]
    else:
        command = [str(executable), "--data-dir"]
    with (
        tempfile.TemporaryDirectory(prefix="rgs-section-reading-smoke-") as folder,
        SyntheticProvider() as provider,
    ):
        isolated = Path(folder)
        pdf = isolated / "anonymous-synthetic.pdf"
        pdf_hash = make_pdf(pdf)
        output: queue.Queue[str] = queue.Queue()
        with (isolated / "synthetic-sidecar-stderr.log").open("w+", encoding="utf-8") as stderr:
            child = subprocess.Popen(
                command + [str(isolated / "data")],
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
                base = f"http://127.0.0.1:{ready['port']}/api/v1"
                report = exercise(base, token, provider, pdf)
                assert hashlib.sha256(pdf.read_bytes()).hexdigest() == pdf_hash
                report["anonymous_pdf_unchanged"] = True
                report["sidecar"] = "packaged" if executable else "source"
                return report
            except Exception:
                if provider.errors:
                    print(
                        json.dumps(
                            {"synthetic_provider_errors": provider.errors}, ensure_ascii=False
                        )
                    )
                stderr.flush()
                raise
            finally:
                if child.stdin is not None and not child.stdin.closed:
                    child.stdin.close()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)


def exercise(base: str, token: str, provider: SyntheticProvider, pdf: Path) -> dict[str, Any]:
    health = request(base, token, "GET", "/health")
    assert health["schema_version"] == "lite0018" and health["database"] == "ready"
    project = request(
        base,
        token,
        "POST",
        "/projects",
        {"name": "Anonymous section reading smoke", "description": "synthetic"},
    )
    imported = request(
        base,
        token,
        "POST",
        f"/projects/{project['id']}/papers/import/pdf",
        {"path": str(pdf), "mode": "reference"},
    )
    wait_job(base, token, imported["id"])
    papers = request(base, token, "GET", f"/projects/{project['id']}/papers")
    paper_id = papers["items"][0]["id"]
    detail = request(base, token, "GET", f"/papers/{paper_id}")
    version = detail["revisions"][0]["id"]
    sections = request(base, token, "GET", f"/revisions/{version}/sections")["sections"]
    section = max(
        (item for item in sections if not item["excluded"] and item["chunk_ids"]),
        key=lambda item: len(item["chunk_ids"]),
    )
    scope = f"/papers/{paper_id}/sections/{section['id']}"
    local = request(base, token, "GET", f"{scope}/paragraphs?document_version_id={version}")
    paragraph_ids = [p["paragraph_id"] for p in local["paragraphs"]]
    assert paragraph_ids
    usage_url = f"/projects/{project['id']}/lite/usage"
    assert not provider.calls and request(base, token, "GET", usage_url)["calls"] == 0
    request(
        base,
        token,
        "PUT",
        f"{scope}/reading-state",
        {"document_version_id": version, "progress": "READING", "self_assessment": "PARTIAL"},
    )
    connection = request(
        base,
        token,
        "POST",
        "/settings/connections",
        {
            "name": "Loopback synthetic SSE fixture",
            "provider": "local",
            "base_url": provider.base_url,
        },
    )
    assert connection["has_api_key"] is False
    profile = request(
        base,
        token,
        "POST",
        "/settings/models",
        {
            "name": "Synthetic section smoke",
            "connection_id": connection["id"],
            "model": MODEL,
            "parameters": {"timeout_seconds": 20},
        },
    )
    assert profile["has_api_key"] is False
    request(base, token, "POST", "/settings/model-roles", {"extraction": profile["id"]})
    body = {"document_version_id": version, "paragraph_ids": paragraph_ids, "allow_network": True}
    generated = request(base, token, "POST", f"{scope}/close-reading/generate", body)
    wait_job(base, token, generated["job_id"])
    completed = request(base, token, "GET", f"{scope}/close-reading?result_id={generated['id']}")
    assert completed["status"] == "COMPLETED" and not completed["missing_paragraph_ids"]
    analysis = completed["analysis"]
    assert [p["paragraph_id"] for p in analysis["paragraphs"]] == paragraph_ids
    assert all(
        p["translation_zh"] and p["logic_role_zh"] and "text_en" not in p
        for p in analysis["paragraphs"]
    )
    assert analysis["section_argument"] and provider.calls == ["A02"]
    assert completed["usage"]["input_tokens"] == 23 and completed["usage"]["output_tokens"] == 41
    cached = request(base, token, "POST", f"{scope}/close-reading/generate", body)
    assert cached["cache_hit"] is True and cached["status"] == "COMPLETED"
    assert provider.calls == ["A02"]
    after_cache = request(base, token, "GET", usage_url)
    assert after_cache["calls"] == 1 and after_cache["cache_hits"] >= 1
    check = request(
        base,
        token,
        "POST",
        f"{scope}/understanding-check",
        {**body, "user_explanation": "该合成方法使用共享记忆协同，并保留不确定性。"},
    )
    wait_job(base, token, check["job_id"])
    checked = request(base, token, "GET", f"{scope}/understanding-check?result_id={check['id']}")
    assert checked["status"] == "COMPLETED" and checked["check"]["check_result"] == "ADEQUATE"
    state = request(base, token, "GET", f"{scope}/reading-state?document_version_id={version}")
    assert state["self_assessment"] == "PARTIAL"
    final = request(base, token, "GET", usage_url)
    assert provider.calls == ["A02", "A03"] and not provider.errors
    assert (
        final["calls"],
        final["input_tokens"],
        final["output_tokens"],
        final["total_tokens"],
    ) == (2, 46, 82, 128)
    assert (
        final["retry_count"] == 0
        and final["cost_known"] is False
        and final["cost_estimate"] is None
    )
    return {
        "status": "passed",
        "schema_version": health["schema_version"],
        "usage_kind": "synthetic loopback Chat Completions SSE fixture; not real model usage",
        "real_model_calls": 0,
        "local_import_and_paragraph_calls": 0,
        "paragraph_count": len(paragraph_ids),
        "a02_calls": 1,
        "a02_cache_extra_calls": 0,
        "a03_calls": 1,
        "self_assessment_preserved": state["self_assessment"],
        "synthetic_provider_calls": len(provider.calls),
        "synthetic_metadata_requests": provider.metadata_requests,
        "synthetic_input_tokens": final["input_tokens"],
        "synthetic_output_tokens": final["output_tokens"],
        "synthetic_total_tokens": final["total_tokens"],
        "cache_hits": final["cache_hits"],
        "cost": None,
        "cost_known": False,
        "non_loopback_requests": 0,
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
