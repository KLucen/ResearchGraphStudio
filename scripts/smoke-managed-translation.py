"""Packaged-engine protocol probe with an actual owned synthetic server process.

This is not a real PDF translator. It returns the anonymous source fixture as
both outputs, exercises the proxy with a synthetic provider, and checks that
the owned server is stopped before COMPLETED and never restarted for a cache hit.
"""

import argparse
import importlib.util
import json
import socket
import tempfile
import threading
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "translation_smoke", Path(__file__).with_name("smoke-translation.py")
)
assert spec is not None and spec.loader is not None
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)

SYNTHETIC_SERVER = r"""
__version__ = "4.1.8"
import argparse, base64, json, os, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("--host")
p.add_argument("--port", type=int)
args, _ = p.parse_known_args()
task = {}
files = {}
def translate(body):
    global task, files
    try:
        payload = {"model": body["llm_api"]["model"],
                   "messages": [{"role": "user", "content": "Translate this synthetic sentence."}]}
        for _ in range(2):
            request = urllib.request.Request(
                body["llm_api"]["apiUrl"] + "/chat/completions",
                data=json.dumps(payload).encode(), headers={
                    "Authorization": "Bearer " + body["llm_api"]["apiKey"],
                    "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=10) as response:
                assert json.loads(response.read())["choices"][0]["message"]["content"]
        stem = body["fileName"].removesuffix(".pdf")
        names = [f"{stem}.no_watermark.zh-CN.{suffix}.pdf" for suffix in ("mono", "LR_dual")]
        files = dict.fromkeys(names, base64.b64decode(body["fileContent"], validate=True))
        task = {"taskId": "managed-synthetic", "active": False, "finished": True,
                "status": "完成", "progress": 100, "result": {"fileList": names}}
    except Exception:
        task = {"taskId": "managed-synthetic", "active": False, "status": "失败"}
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def reply(self, value, status=200):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.path == "/health": self.reply({"status": "ok", "version": __version__})
        elif self.path == "/api/tasks":
            self.reply({"status": "success", "tasks": [task] if task else []})
        elif self.path == "/api/history": self.reply({"status": "success", "history": []})
        elif self.path.startswith("/translatedFile/"):
            from urllib.parse import unquote
            content = files.get(unquote(self.path.rsplit("/", 1)[1]))
            if content is None: self.reply({}, 404); return
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else: self.reply({}, 404)
    def do_POST(self):
        global task
        if self.path != "/translate": self.reply({}, 404); return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        task = {"taskId": "managed-synthetic", "active": True, "progress": 0}
        threading.Thread(target=translate, args=(body,), daemon=True).start()
        self.reply({"status": "accepted", "taskId": "managed-synthetic"})
Path(__file__).with_name("started.json").write_text(json.dumps({"pid": os.getpid()}))
ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--executable", type=Path)
    group.add_argument("--source-python", type=Path)
    parser.add_argument("--runtime-python", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="rgs-managed-smoke-") as directory:
        server = Path(directory) / "server.py"
        server.write_text(SYNTHETIC_SERVER, encoding="utf-8")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        services = protocol.SyntheticServices()
        services.runtime_settings = {
            "enabled": True,
            "service_url": f"http://127.0.0.1:{port}",
            "launch_mode": "managed",
            "python_path": str(args.runtime_python.resolve()),
            "server_path": str(server),
        }
        thread = threading.Thread(target=services.server.serve_forever, daemon=True)
        thread.start()
        try:

            def verify(base: str, token: str, project: str, fixture: Path) -> dict:
                assert not server.with_name("started.json").exists()
                result = services.verify(base, token, project, fixture)
                assert server.with_name("started.json").is_file()
                # A live listener would fail the exclusive local bind. No
                # process-name killing or access to an existing service occurs.
                with socket.socket() as stopped:
                    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                        stopped.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    stopped.bind(("127.0.0.1", port))
                return {
                    **result,
                    "managed_server_started": True,
                    "managed_server_stopped_before_completed": True,
                }

            result = protocol.smoke.run(args.executable, args.source_python, after_import=verify)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            services.server.shutdown()
            services.server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
