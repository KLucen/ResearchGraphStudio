"""Run the actual bundled layout engine against a synthetic loopback provider.

No real model or personal data is used. This checks CLI/runtime integration and
PDF output selection, not scientific translation quality. Synthetic usage values
are test fixtures, not measurements of provider tokenization.
"""

import argparse
import importlib.util
import json
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError

import pymupdf

spec = importlib.util.spec_from_file_location(
    "lite_smoke", Path(__file__).with_name("smoke-engine.py")
)
assert spec and spec.loader
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SyntheticProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.request_fields: list[list[str]] = []
        self.optional_fields_seen: list[list[str]] = []
        self.rejected_calls = 0
        state = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                assert self.path == "/v1/chat/completions"
                assert body["model"] in {
                    "synthetic-bundled-translator",
                    "synthetic-rejected-translator",
                }
                state.calls += 1
                state.request_fields.append(sorted(body))
                optional = sorted({"temperature", "top_p", "reasoning_effort"} & body.keys())
                if optional:
                    state.optional_fields_seen.append(optional)
                if optional or body["model"] == "synthetic-rejected-translator":
                    state.rejected_calls += 1
                    # The local proxy must classify the HTTP status without
                    # forwarding this deliberately private synthetic body.
                    self.respond(
                        400,
                        {"error": {"message": "synthetic-private-provider-diagnostic"}},
                    )
                    return
                raw = json.dumps(
                    {
                        "id": "synthetic",
                        "object": "chat.completion",
                        "created": 0,
                        "model": body["model"],
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {
                                    "role": "assistant",
                                    "content": "这是本地合成翻译测试，仅用于验证排版流程。",
                                },
                            }
                        ],
                        "usage": {"prompt_tokens": 17, "completion_tokens": 7, "total_tokens": 24},
                    },
                    ensure_ascii=False,
                ).encode()
                self.respond(200, raw)

            def respond(self, status, value):
                raw = value if isinstance(value, bytes) else json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def verify(self, base: str, token: str, project: str, _fixture: Path) -> dict:
        def api(method, path, body=None, key="bundled-smoke"):
            return smoke.request(base, token, method, path, body, key)

        settings = api("GET", "/settings/translation")
        assert settings["enabled"] and settings["launch_mode"] == "bundled"
        health = api("POST", "/settings/translation/check", {})
        assert health["available"], health
        profile = api(
            "POST",
            "/settings/models",
            {
                "name": "Synthetic bundled translation",
                "provider": "compatible",
                "base_url": self.url,
                "model": "synthetic-bundled-translator",
                "parameters": {
                    "temperature": 0.2,
                    "top_p": 0.8,
                    "reasoning_effort": "high",
                },
            },
        )
        paper = api("GET", f"/projects/{project}/papers")["items"][0]
        revision = api("GET", f"/papers/{paper['id']}")["revisions"][0]
        path = f"/papers/{paper['id']}/translations"
        results = []
        for mode in ("mono", "dual"):
            body = {
                "document_version_id": revision["id"],
                "profile_id": profile["id"],
                "output_mode": mode,
                "max_calls": 100,
            }
            prepared = api("POST", path + "/prepare", body)
            assert prepared["service_ready"] and not prepared["cache_hit"], prepared
            before = self.calls
            started = time.monotonic()
            created = api(
                "POST",
                path,
                {
                    **body,
                    "expected_fingerprint": prepared["prepare_fingerprint"],
                    "allow_network": True,
                    "exclusive_service": True,
                },
                f"bundled-{mode}",
            )
            while True:
                record = api("GET", path + "/" + created["id"])
                if record["status"] not in {"PENDING", "RUNNING"}:
                    break
                assert time.monotonic() - started < 600, "Bundled engine timed out"
                time.sleep(0.25)
            assert record["status"] == "COMPLETED", record
            assert record["launch_mode"] == "bundled" and record["output_mode"] == mode
            assert {a["kind"] for a in record["artifacts"]} == {mode}, record
            assert self.calls > before and record["usage"]["calls"] == self.calls - before
            artifact = api("GET", f"/translations/{created['id']}/artifacts/{mode}")
            assert artifact["size_bytes"] > 100 and artifact["page_count"] >= 2
            with pymupdf.open(artifact["path"]) as generated:
                width = generated[0].rect.width
                assert width > 1000 if mode == "dual" else 500 < width < 700
                assert "本地合成翻译测试" in "".join(page.get_text() for page in generated)
            prepared = api("POST", path + "/prepare", body)
            assert prepared["cache_hit"]
            cache_before = self.calls
            cached = api(
                "POST",
                path,
                {**body, "expected_fingerprint": prepared["prepare_fingerprint"]},
                f"cache-{mode}",
            )
            assert cached["cache_hit"] and cached["usage"]["calls"] == 0
            assert self.calls == cache_before
            results.append(
                {
                    "mode": mode,
                    "status": record["status"],
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "artifact": {k: v for k, v in artifact.items() if k != "path"},
                    "synthetic_usage": record["usage"],
                }
            )
        assert not self.optional_fields_seen, self.optional_fields_seen
        assert self.rejected_calls == 0

        # Use a distinct frozen model identity to avoid the successful whole-
        # document cache. One rejected provider call must fail the task without
        # publishing an original-text fallback PDF or automatically retrying.
        rejected_profile = api(
            "POST",
            "/settings/models",
            {
                "name": "Synthetic rejected translation",
                "provider": "compatible",
                "base_url": self.url,
                "model": "synthetic-rejected-translator",
                "parameters": {
                    "temperature": 0.2,
                    "top_p": 0.8,
                    "reasoning_effort": "high",
                },
            },
            "rejected-profile",
        )
        rejected_body = {
            "document_version_id": revision["id"],
            "profile_id": rejected_profile["id"],
            "output_mode": "mono",
            "max_calls": 100,
        }
        prepared = api("POST", path + "/prepare", rejected_body)
        assert prepared["service_ready"] and not prepared["cache_hit"]
        before = self.calls
        started = time.monotonic()
        created = api(
            "POST",
            path,
            {
                **rejected_body,
                "expected_fingerprint": prepared["prepare_fingerprint"],
                "allow_network": True,
                "exclusive_service": True,
            },
            "bundled-provider-rejected",
        )
        while True:
            record = api("GET", path + "/" + created["id"])
            if record["status"] not in {"PENDING", "RUNNING"}:
                break
            assert time.monotonic() - started < 600, "Rejected task timed out"
            time.sleep(0.25)
        assert record["status"] == "FAILED", record
        assert record["error_code"] == "TRANSLATION_PROVIDER_REQUEST_REJECTED", record
        assert "模型服务拒绝" in record["error"]
        assert "synthetic-private-provider-diagnostic" not in json.dumps(record)
        assert not record["artifacts"]
        assert record["usage"]["calls"] == self.calls - before == 1
        assert record["usage"]["retry_count"] == 0
        assert self.rejected_calls == 1 and not self.optional_fields_seen
        for mode in ("mono", "dual"):
            try:
                api("GET", f"/translations/{created['id']}/artifacts/{mode}")
            except HTTPError as error:
                assert error.code in {404, 409}
            else:
                raise AssertionError("Failed translation published a PDF")
        # Polling a failed task is read-only and cannot restart the CLI or model.
        assert api("GET", path + "/" + created["id"])["status"] == "FAILED"
        assert self.calls - before == 1
        return {
            "status": "passed",
            "actual_layout_engine": "pdf2zh-next-2.10.2",
            "real_model_calls": 0,
            "synthetic_provider_calls": self.calls,
            "profile_parameters_suppressed": True,
            "request_fields": sorted({tuple(fields) for fields in self.request_fields}),
            "quality_verified": False,
            "results": results,
            "provider_rejection": {
                "status": record["status"],
                "error_code": record["error_code"],
                "synthetic_provider_calls": self.calls - before,
                "artifacts": record["artifacts"],
                "elapsed_seconds": round(time.monotonic() - started, 3),
            },
        }


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--executable", type=Path)
    group.add_argument("--source-python", type=Path)
    args = parser.parse_args()
    provider = SyntheticProvider()
    thread = threading.Thread(target=provider.server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="rgs-layout-fixture-") as folder:
            fixture = Path(folder) / "synthetic-article.pdf"
            with pymupdf.open() as document:
                for number in range(2):
                    page = document.new_page()
                    page.insert_text((50, 50), "Synthetic Layout Study", fontsize=18)
                    paragraph = (
                        "This anonymous article evaluates local document processing. "
                        "The example is synthetic and contains no personal research data. "
                        "We compare document layouts and verify that the original source "
                        "remains unchanged. The experiment reports no scientific findings. "
                        "All translation responses come from a local test provider. "
                        "The generated Chinese text is used only to exercise the PDF writer."
                    )
                    page.insert_textbox(
                        pymupdf.Rect(50, 85, 545, 780),
                        f"{number + 1}. Local processing\n\n" + "\n\n".join([paragraph] * 8),
                        fontsize=11,
                        fontname="helv",
                    )
                document.save(fixture)
            result = smoke.run(
                args.executable, args.source_python, after_import=provider.verify, fixture=fixture
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        provider.server.shutdown()
        provider.server.server_close()
        thread.join(5)


if __name__ == "__main__":
    main()
