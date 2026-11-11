"""Synthetic PDFs and a fake CLI only: no upstream engine or model is invoked."""

import base64
import json
import os
import subprocess
import threading
import time
import tomllib
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from fastapi.testclient import TestClient
from researchgraph import translation_bundled as bundled
from researchgraph.core import KnowledgeError

SERVICE_TOKEN = "synthetic_service_ticket_1234567890"
PROXY_TOKEN = "synthetic_proxy_ticket_1234567890"


def _pdf():
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "A synthetic translation fixture.")
        return document.tobytes()


def _bundle(tmp_path):
    directory = tmp_path / "bundle with 空格"
    directory.mkdir()
    for name in bundled.BUNDLED_REQUIRED_FILES:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic local resource")
    (directory / "runtime-manifest.json").write_text(
        json.dumps(
            {
                "format": 1,
                "engine_id": bundled.BUNDLED_ENGINE_ID,
                "pdf2zh_next": "2.10.2",
                "babeldoc": "0.7.1",
            }
        ),
        encoding="utf-8",
    )
    return directory


def _request(mode="both"):
    return {
        "fileName": f"rg-{uuid4()}.pdf",
        "fileContent": base64.b64encode(_pdf()).decode(),
        "asyncJob": True,
        "engine": "pdf2zh_next",
        "next_service": "openai",
        "sourceLang": "en",
        "targetLang": "zh-CN",
        "mono": mode in {"mono", "both"},
        "dual": mode in {"dual", "both"},
        "noMono": mode == "dual",
        "noDual": mode == "mono",
        "dualMode": "LR",
        "noWatermark": True,
        "qps": 1,
        "poolSize": 1,
        "disableGlossary": True,
        "ignoreCache": True,
        "llm_api": {
            "apiKey": PROXY_TOKEN,
            "apiUrl": "http://127.0.0.1:54321/v1",
            "model": 'synthetic/model"quoted',
            "extraData": {
                "openai_timeout": 120,
                "openai_enable_json_mode": False,
                "openai_send_temprature": False,
                "openai_send_reasoning_effort": False,
            },
        },
    }


class _FakeProcess:
    pid = 2_000_000_000

    def __init__(self, *, mode):
        self.mode = mode
        self.stopped = threading.Event()
        if mode != "hang":
            self.stopped.set()

    def wait(self, timeout=None):
        if not self.stopped.wait(timeout):
            raise subprocess.TimeoutExpired("synthetic", timeout)
        return 7 if self.mode == "nonzero" else 0

    def poll(self):
        return self.wait() if self.stopped.is_set() else None

    def kill(self):
        self.stopped.set()


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = _bundle(tmp_path)
    work = tmp_path / "tasks"
    work.mkdir()
    cache = tmp_path / "shared runtime cache"
    monkeypatch.setenv("RGS_TRANSLATION_CACHE", str(cache))
    monkeypatch.setenv("SYNTHETIC_API_KEY", "must-never-reach-cli")
    monkeypatch.setenv("OPENAI_API_KEY", "must-never-reach-cli")
    monkeypatch.setenv("PYTHONPATH", "must-never-reach-cli")
    monkeypatch.setenv("HTTPS_PROXY", "http://private-proxy.invalid")
    calls = []

    def spawn(argv, cwd, env):
        configuration = Path(argv[argv.index("--config-file") + 1])
        output = Path(argv[argv.index("--output") + 1])
        stem = Path(argv[1]).stem
        process = _FakeProcess(mode=spawn.mode)
        calls.append(
            {
                "argv": argv,
                "cwd": cwd,
                "env": env,
                "process": process,
                "configuration": configuration,
                "config": tomllib.loads(configuration.read_text()),
                "input": Path(argv[1]),
                "input_content": Path(argv[1]).read_bytes(),
            }
        )
        if spawn.mode != "missing":
            for kind in ("mono", "dual"):
                if f"--no-{kind}" not in argv:
                    content = b"not a PDF" if spawn.mode == "corrupt" else _pdf()
                    (output / f"{stem}.no_watermark.zh-CN.{kind}.pdf").write_bytes(content)
        return process

    spawn.mode = "success"
    monkeypatch.setattr(bundled, "_spawn_cli", spawn)

    async def stop(process):
        process.kill()

    monkeypatch.setattr(bundled, "_stop_cli", stop)
    app = bundled.create_bundled_app(root, work, SERVICE_TOKEN)
    return app, root, work, cache, calls, spawn


def _finished(client, task_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        tasks = client.get("/api/tasks").json()["tasks"]
        for task in tasks:
            if task["taskId"] == task_id and task["finished"]:
                return task
        time.sleep(0.01)
    raise AssertionError("Synthetic task did not finish")


@pytest.mark.parametrize("mode", ["mono", "dual", "both"])
def test_selected_outputs_fixed_cli_and_ephemeral_configuration(installation, mode):
    app, root, work, cache, calls, _spawn = installation
    body = _request(mode)
    with TestClient(app, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"}) as client:
        assert client.get("/health").json() == {
            "status": "ok",
            "version": bundled.BUNDLED_SERVICE_VERSION,
        }
        response = client.post("/translate", json=body)
        assert response.status_code == 200
        task_id = response.json()["taskId"]
        task = _finished(client, task_id)
        assert task["status"] == "success"
        assert task["progress"] == 100 and task["active"] is False
        expected = {"mono", "dual"} if mode == "both" else {mode}
        assert len(task["fileList"]) == len(expected)
        for name in task["fileList"]:
            download = client.get(f"/translatedFile/{name}")
            assert download.status_code == 200
            assert download.content.startswith(b"%PDF-")
        unselected = "dual" if mode == "mono" else "mono"
        if mode != "both":
            suffix = "LR_dual" if unselected == "dual" else "mono"
            name = f"rg-{task_id}.no_watermark.zh-CN.{suffix}.pdf"
            assert client.get(f"/translatedFile/{name}").status_code == 404
        assert client.post("/translate", json=body).status_code == 409
        assert client.get("/api/history").json()["history"] == [task]
    assert len(calls) == 1
    call = calls[0]
    argv, environment = call["argv"], call["env"]
    assert argv[0] == str(root / "pdf2zh.exe")
    assert "--openai" in argv and "--ignore-cache" in argv
    assert "--no-auto-extract-glossary" in argv and "--disable-config-auto-save" in argv
    assert argv[argv.index("--watermark-output-mode") + 1] == "no_watermark"
    assert argv[argv.index("--pool-max-workers") + 1] == "1"
    assert PROXY_TOKEN not in str(argv) and body["llm_api"]["model"] not in str(argv)
    assert call["cwd"].is_relative_to(work)
    assert call["input_content"].startswith(b"%PDF-")
    assert call["config"] == {
        "openai_detail": {
            "openai_model": body["llm_api"]["model"],
            "openai_base_url": "http://127.0.0.1:54321/v1",
            "openai_api_key": PROXY_TOKEN,
            "openai_timeout": "120",
            "openai_enable_json_mode": False,
            "openai_send_temprature": False,
            "openai_send_reasoning_effort": False,
        }
    }
    assert not call["configuration"].exists() and not call["input"].exists()
    assert not (call["cwd"] / "tmp").exists()
    for key in (
        "OPENAI_API_KEY",
        "SYNTHETIC_API_KEY",
        "PYTHONPATH",
        "HTTPS_PROXY",
        "RGS_TRANSLATION_SERVICE_TOKEN",
        "RGS_TRANSLATION_CACHE",
    ):
        assert key not in environment
    assert environment["USERPROFILE"] == str(cache)
    assert environment["HOME"] == str(cache)
    assert environment["HF_HUB_OFFLINE"] == "1"


@pytest.mark.parametrize("mode", ["nonzero", "missing", "corrupt"])
def test_failure_never_publishes_an_output(installation, mode):
    app, _root, _work, _cache, calls, spawn = installation
    spawn.mode = mode
    with TestClient(app, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"}) as client:
        result = client.post("/translate", json=_request()).json()
        task = _finished(client, result["taskId"])
        assert task["status"] == "failed" and task["fileList"] == []
        assert client.get("/translatedFile/model.toml").status_code == 404
        assert client.get("/translatedFile/runtime-manifest.json").status_code == 404
    assert not calls[0]["configuration"].exists()


def test_authentication_and_origin_rejection_apply_to_every_route(installation):
    app = installation[0]
    with TestClient(app) as client:
        for path in ("/health", "/api/tasks", "/api/history", "/translatedFile/test.pdf"):
            assert client.get(path).status_code == 401
            assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
            assert (
                client.get(
                    path,
                    headers={
                        "Authorization": f"Bearer {SERVICE_TOKEN}",
                        "Origin": "null",
                    },
                ).status_code
                == 403
            )
        assert client.post("/translate", json=_request()).status_code == 401
        assert (
            client.post(
                "/translate",
                json=_request(),
                headers={
                    "Authorization": f"Bearer {SERVICE_TOKEN}",
                    "Origin": "https://example.invalid",
                },
            ).status_code
            == 403
        )
    assert installation[4] == []


@pytest.mark.parametrize(
    "change",
    [
        "path",
        "uppercase",
        "malformed_uuid",
        "extra_field",
        "wrong_engine",
        "both_disabled",
        "inconsistent_mode",
        "boolean_number",
        "invalid_base64",
        "non_pdf",
        "external_proxy",
        "localhost_proxy",
        "proxy_credentials",
        "proxy_query",
        "proxy_fragment",
        "proxy_path",
        "proxy_port",
        "short_ticket",
        "ticket_control",
        "model_control",
        "extra_options",
        "json_enabled",
        "reasoning_enabled",
        "timeout_boolean",
    ],
)
def test_invalid_inputs_fail_before_cli(installation, change):
    app = installation[0]
    body = _request()
    if change == "path":
        body["fileName"] = "../" + body["fileName"]
    elif change == "uppercase":
        body["fileName"] = body["fileName"].upper()
    elif change == "malformed_uuid":
        body["fileName"] = "rg-invalid.pdf"
    elif change == "extra_field":
        body["command"] = "ignored-command"
    elif change == "wrong_engine":
        body["engine"] = "arbitrary-engine"
    elif change == "both_disabled":
        body.update(mono=False, dual=False, noMono=True, noDual=True)
    elif change == "inconsistent_mode":
        body["noDual"] = True
    elif change == "boolean_number":
        body["qps"] = True
    elif change == "invalid_base64":
        body["fileContent"] = "%%%"
    elif change == "non_pdf":
        body["fileContent"] = base64.b64encode(b"not a PDF").decode()
    elif change.startswith("proxy_") or change in {"external_proxy", "localhost_proxy"}:
        body["llm_api"]["apiUrl"] = {
            "external_proxy": "https://api.example.invalid/v1",
            "localhost_proxy": "http://localhost:54321/v1",
            "proxy_credentials": "http://user:pass@127.0.0.1:54321/v1",
            "proxy_query": "http://127.0.0.1:54321/v1?url=secret",
            "proxy_fragment": "http://127.0.0.1:54321/v1#secret",
            "proxy_path": "http://127.0.0.1:54321/v1/anything",
            "proxy_port": "http://127.0.0.1:invalid/v1",
        }[change]
    elif change == "short_ticket":
        body["llm_api"]["apiKey"] = "short"
    elif change == "ticket_control":
        body["llm_api"]["apiKey"] = PROXY_TOKEN + "\ncommand"
    elif change == "model_control":
        body["llm_api"]["model"] = "model\n[malicious]"
    elif change == "extra_options":
        body["llm_api"]["extraData"]["command"] = "anything"
    elif change == "json_enabled":
        body["llm_api"]["extraData"]["openai_enable_json_mode"] = True
    elif change == "reasoning_enabled":
        body["llm_api"]["extraData"]["openai_send_reasoning_effort"] = True
    elif change == "timeout_boolean":
        body["llm_api"]["extraData"]["openai_timeout"] = True
    with TestClient(app, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"}) as client:
        result = client.post("/translate", json=body)
        assert result.status_code == 400
        assert PROXY_TOKEN not in result.text
    assert installation[4] == []


def test_stream_limit_strict_json_and_pdf_limit(installation, monkeypatch):
    app = installation[0]
    with TestClient(app, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"}) as client:
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', "[]"):
            assert (
                client.post(
                    "/translate",
                    content=raw,
                    headers={
                        "Content-Type": "application/json",
                    },
                ).status_code
                == 400
            )
        assert client.post("/translate", content="text/plain").status_code == 415
        monkeypatch.setattr(bundled, "MAX_PDF_BYTES", 10)
        assert client.post("/translate", json=_request()).status_code == 400
        monkeypatch.setattr(bundled, "MAX_REQUEST_BYTES", 32)
        assert client.post("/translate", json=_request()).status_code == 413
        assert (
            client.post(
                "/translate",
                content=iter([b"x" * 20, b"x" * 20]),
                headers={
                    "Content-Type": "application/json",
                },
            ).status_code
            == 413
        )
    assert installation[4] == []


def test_lifespan_cancels_active_cli_and_removes_temporary_ticket(installation):
    app, _root, _work, _cache, calls, spawn = installation
    spawn.mode = "hang"
    with TestClient(app, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"}) as client:
        assert client.post("/translate", json=_request()).status_code == 200
        deadline = time.monotonic() + 5
        while not calls and time.monotonic() < deadline:
            time.sleep(0.01)
        assert calls
        assert client.get("/api/tasks").json()["tasks"][0]["active"] is True
        assert client.post("/translate", json=_request()).status_code == 409
    assert calls[0]["process"].stopped.is_set()
    assert not calls[0]["configuration"].exists()
    assert not calls[0]["input"].exists()


def test_preflight_is_local_and_checks_pinned_resources(tmp_path, monkeypatch):
    directory = _bundle(tmp_path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("local preflight must never execute an engine")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert bundled.validate_bundled_root(directory) == directory.resolve()
    for key, value in (("pdf2zh_next", "2.10.1"), ("babeldoc", "0.7.0"), ("engine_id", "unknown")):
        manifest = directory / "runtime-manifest.json"
        original = manifest.read_text()
        payload = json.loads(original)
        payload[key] = value
        manifest.write_text(json.dumps(payload))
        with pytest.raises(KnowledgeError, match="内置翻译组件") as error:
            bundled.validate_bundled_root(directory)
        assert error.value.code == "TRANSLATION_BUNDLE_INVALID"
        manifest.write_text(original)
    critical = directory / bundled.BUNDLED_REQUIRED_FILES[0]
    critical.unlink()
    with pytest.raises(KnowledgeError):
        bundled.validate_bundled_root(directory)


def test_spawn_uses_hidden_no_shell_process_with_discarded_io(tmp_path, monkeypatch):
    calls = []

    def popen(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeProcess(mode="success")

    monkeypatch.setattr(subprocess, "Popen", popen)
    bundled._spawn_cli(["synthetic.exe", "input.pdf"], tmp_path, {"HOME": str(tmp_path)})
    arguments, options = calls[0]
    assert arguments == (["synthetic.exe", "input.pdf"],)
    assert not options.get("shell", False)
    assert options["stdin"] == options["stdout"] == options["stderr"] == subprocess.DEVNULL
    assert options["close_fds"] is True
    assert options["creationflags"] == (subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
