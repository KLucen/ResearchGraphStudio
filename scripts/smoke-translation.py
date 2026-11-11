"""Packaged bridge smoke with synthetic HTTP services; never a real translation.

Uses an anonymous PDF fixture and a local fake provider. Generated artifacts
deliberately reuse that fixture: this checks wiring and accounting, not layout
or translation quality. No saved user configuration or credential is read.
"""

import argparse
import base64
import importlib.util
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "lite_smoke", Path(__file__).with_name("smoke-engine.py")
)
assert spec and spec.loader
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SyntheticServices:
    def __init__(self) -> None:
        self.calls = 0
        self.uploads = 0
        self.task: dict | None = None
        self.files: dict[str, bytes] = {}
        state = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                pass

            def reply(self, value, status=200) -> None:
                raw = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                if self.path == "/health":
                    self.reply({"status": "ok", "version": "4.1.8"})
                elif self.path == "/api/tasks":
                    self.reply({"status": "success", "tasks": [state.task] if state.task else []})
                elif self.path == "/api/history":
                    self.reply({"status": "success", "history": []})
                elif self.path.startswith("/translatedFile/"):
                    content = state.files.get(self.path.removeprefix("/translatedFile/"))
                    if content is None:
                        self.reply({}, 404)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    self.reply({}, 404)

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/v1/chat/completions":
                    state.calls += 1
                    self.reply(
                        {
                            "model": "synthetic-translator",
                            "choices": [
                                {
                                    "finish_reason": "stop",
                                    "message": {"role": "assistant", "content": "合成译文"},
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 17,
                                "completion_tokens": 7,
                                "total_tokens": 24,
                            },
                        }
                    )
                elif self.path == "/translate":
                    state.uploads += 1
                    assert body["ignoreCache"] is True and body["engine"] == "pdf2zh_next"
                    assert body["mono"] and body["dual"] and body["asyncJob"]
                    assert body["llm_api"]["apiUrl"].startswith("http://127.0.0.1:")
                    state.task = {"taskId": "synthetic-task", "active": True, "progress": 0}
                    threading.Thread(target=state.finish, args=(body,), daemon=True).start()
                    self.reply({"status": "accepted", "taskId": "synthetic-task"})
                else:
                    self.reply({}, 404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def finish(self, body: dict) -> None:
        try:
            payload = {
                "model": body["llm_api"]["model"],
                "messages": [{"role": "user", "content": "Translate this synthetic sentence."}],
            }
            for _ in range(2):
                request = urllib.request.Request(
                    body["llm_api"]["apiUrl"] + "/chat/completions",
                    data=json.dumps(payload).encode(),
                    headers={
                        "Authorization": "Bearer " + body["llm_api"]["apiKey"],
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    assert json.loads(response.read())["choices"][0]["message"]["content"]
            stem = body["fileName"].removesuffix(".pdf")
            files = [f"{stem}.no_watermark.zh-CN.{suffix}.pdf" for suffix in ("mono", "LR_dual")]
            content = base64.b64decode(body["fileContent"], validate=True)
            self.files = dict.fromkeys(files, content)
            self.task = {
                "taskId": "synthetic-task",
                "active": False,
                "finished": True,
                "status": "完成",
                "progress": 100,
                "result": {"fileList": files},
            }
        except Exception:
            self.task = {"taskId": "synthetic-task", "active": False, "status": "失败"}

    def verify(self, base: str, token: str, project: str, _fixture: Path) -> dict:
        def api(method: str, path: str, body=None, key="translation-smoke"):
            return smoke.request(base, token, method, path, body, key)

        profile = api(
            "POST",
            "/settings/models",
            {
                "name": "Synthetic translation",
                "provider": "compatible",
                "base_url": self.url + "/v1",
                "model": "synthetic-translator",
            },
        )
        runtime_settings = getattr(self, "runtime_settings", None)
        api(
            "PUT",
            "/settings/translation",
            runtime_settings or {"enabled": True, "service_url": self.url, "launch_mode": "manual"},
        )
        paper = api("GET", f"/projects/{project}/papers")["items"][0]
        revision = api("GET", f"/papers/{paper['id']}")["revisions"][0]
        path = f"/papers/{paper['id']}/translations"
        body = {"document_version_id": revision["id"], "profile_id": profile["id"]}
        prepared = api("POST", path + "/prepare", body)
        assert prepared["service_ready"] and self.calls == self.uploads == 0
        created = api(
            "POST",
            path,
            {
                **body,
                "expected_fingerprint": prepared["prepare_fingerprint"],
                "allow_network": True,
                "exclusive_service": True,
            },
        )
        deadline = time.monotonic() + 30
        while True:
            record = api("GET", path + "/" + created["id"])
            if record["status"] not in {"PENDING", "RUNNING"}:
                break
            assert time.monotonic() < deadline, "Synthetic translation timed out"
            time.sleep(0.1)
        assert record["status"] == "COMPLETED", record.get("error_code")
        assert {artifact["kind"] for artifact in record["artifacts"]} == {"mono", "dual"}
        assert record["usage"]["calls"] == self.calls == 1
        expected_uploads = 0 if runtime_settings else 1
        assert self.uploads == expected_uploads
        assert record["usage"]["input_tokens"] == 17
        assert record["usage"]["output_tokens"] == 7
        assert record["usage"]["cost_known"] is False
        for kind in ("mono", "dual"):
            artifact = api("GET", f"/translations/{created['id']}/artifacts/{kind}")
            assert artifact["translation_id"] == created["id"]
        prepared = api("POST", path + "/prepare", body)
        cached = api(
            "POST",
            path,
            {**body, "expected_fingerprint": prepared["prepare_fingerprint"]},
            "translation-cache",
        )
        assert cached["cache_hit"] and cached["usage"]["calls"] == 0
        assert self.calls == 1 and self.uploads == expected_uploads
        usage = api("GET", f"/projects/{project}/lite/usage")
        assert usage["calls"] == 1 and usage["cache_hits"] == 2
        return {
            "status": "passed",
            "synthetic_provider_calls": self.calls,
            "synthetic_input_tokens": 17,
            "synthetic_output_tokens": 7,
            "cache_hits": usage["cache_hits"],
            "real_model_calls": 0,
            "real_pdf_translation": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--executable", type=Path)
    group.add_argument("--source-python", type=Path)
    args = parser.parse_args()
    services = SyntheticServices()
    thread = threading.Thread(target=services.server.serve_forever, daemon=True)
    thread.start()
    try:
        result = smoke.run(args.executable, args.source_python, after_import=services.verify)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        services.server.shutdown()
        services.server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
