"""Bundled process ownership with fake processes and local HTTP transports only."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import researchgraph.translation_bundled as bundled
import researchgraph.translation_runtime as runtime_module
from researchgraph.core import KnowledgeError
from researchgraph.translation_contracts import TranslationSettings
from researchgraph.translation_runtime import ManagedTranslationRuntime


class FakeOwnedProcess:
    pid = 12345

    def __init__(self):
        self.running = True
        self.listener_owned = True
        self.stop_calls = 0

    def alive(self):
        return self.running

    def owns_listener(self, host, port):
        assert host == "127.0.0.1" and 1 <= port <= 65535
        return self.listener_owned

    def stop(self):
        self.stop_calls += 1
        self.running = False


@pytest.fixture
def bundle_paths(tmp_path, monkeypatch):
    root = tmp_path / "内置 translation runtime"
    root.mkdir()
    for relative in bundled.BUNDLED_REQUIRED_FILES:
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"synthetic runtime resource; never executable")
    (root / "runtime-manifest.json").write_text(
        json.dumps(
            {
                "format": 1,
                "engine_id": "pdf2zh-next-2.10.2-babeldoc-0.7.1-rgs-1",
                "pdf2zh_next": "2.10.2",
                "babeldoc": "0.7.1",
            }
        ),
        encoding="utf-8",
    )
    validate = Mock(wraps=bundled.validate_bundled_root)
    monkeypatch.setattr(bundled, "find_bundled_root", lambda: root)
    monkeypatch.setattr(bundled, "validate_bundled_root", validate)
    return root, validate


def patch_process(monkeypatch, *, process=None, error=None):
    process = process or FakeOwnedProcess()
    launches = []

    def spawn(argv, cwd, env):
        work = Path(argv[argv.index("--output-dir") + 1])
        assert work.is_dir()
        (work / "temporary.pdf").write_bytes(b"synthetic temporary data")
        launches.append({"argv": argv, "cwd": cwd, "env": dict(env), "work": work})
        if error:
            raise error
        return process

    monkeypatch.setattr(runtime_module, "_spawn_windows", spawn)
    monkeypatch.setattr(runtime_module, "_PosixProcess", spawn)
    return process, launches


def patch_health(monkeypatch, handler):
    real_client = httpx.AsyncClient
    clients = []
    requests = []

    def respond(request):
        requests.append(request)
        return handler(request)

    def client(**kwargs):
        clients.append(kwargs)
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", client)
    return clients, requests


def test_bundled_validate_only_reads_resources_and_never_launches(
    bundle_paths, tmp_path, monkeypatch
):
    root, validate = bundle_paths

    def forbidden(*_args, **_kwargs):
        pytest.fail("configuration validation must not execute a process or call HTTP")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(runtime_module, "_spawn_windows", forbidden)
    monkeypatch.setattr(runtime_module, "_PosixProcess", forbidden)
    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", forbidden)
    runtime = ManagedTranslationRuntime(TranslationSettings(), tmp_path)
    runtime.validate()
    validate.assert_called_once_with(root)
    assert runtime.expected_version == bundled.BUNDLED_SERVICE_VERSION
    assert runtime.service_token is None
    assert runtime._process is None
    assert not (tmp_path / "translation-work").exists()


def test_missing_bundle_is_rejected_without_launching(tmp_path, monkeypatch):
    missing = tmp_path / "missing runtime"
    monkeypatch.setattr(bundled, "find_bundled_root", lambda: missing)

    def forbidden(*_args, **_kwargs):
        pytest.fail("missing resources must fail before process execution or HTTP")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(runtime_module, "_spawn_windows", forbidden)
    monkeypatch.setattr(runtime_module, "_PosixProcess", forbidden)
    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", forbidden)
    with pytest.raises(KnowledgeError) as caught:
        ManagedTranslationRuntime(TranslationSettings(), tmp_path).validate()
    assert caught.value.code == "TRANSLATION_BUNDLE_INVALID"
    assert not (tmp_path / "translation-work").exists()


@pytest.mark.parametrize("missing", bundled.BUNDLED_REQUIRED_FILES)
def test_missing_bundled_resource_fails_before_spawning(
    bundle_paths, tmp_path, monkeypatch, missing
):
    root, _ = bundle_paths
    (root / missing).unlink()

    def forbidden(*_args, **_kwargs):
        pytest.fail("an incomplete bundle must fail before process execution")

    monkeypatch.setattr(runtime_module, "_spawn_windows", forbidden)
    monkeypatch.setattr(runtime_module, "_PosixProcess", forbidden)
    with pytest.raises(KnowledgeError) as caught:
        ManagedTranslationRuntime(TranslationSettings(), tmp_path).validate()
    assert caught.value.code == "TRANSLATION_BUNDLE_INVALID"
    assert not (tmp_path / "translation-work").exists()


@pytest.mark.parametrize("frozen", [False, True])
def test_bundled_source_and_frozen_launch_keep_ticket_off_command_line(
    bundle_paths, tmp_path, monkeypatch, frozen
):
    root, _ = bundle_paths
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setenv("SYNTHETIC_API_KEY", "must-not-be-inherited")
    monkeypatch.setenv("PYTHONPATH", "must-not-inherit-user-imports")
    monkeypatch.setenv("HTTPS_PROXY", "http://must-not-inherit.invalid")
    monkeypatch.setenv("RGS_TRANSLATION_SERVICE_TOKEN", "must-not-reuse-parent-ticket")
    process, launches = patch_process(monkeypatch)
    clients, requests = patch_health(
        monkeypatch,
        lambda _request: httpx.Response(
            200, json={"status": "ok", "version": bundled.BUNDLED_SERVICE_VERSION}
        ),
    )

    async def run():
        runtime = ManagedTranslationRuntime(TranslationSettings(), tmp_path)
        async with runtime:
            assert len(launches) == 1
            launch = launches[0]
            argv = launch["argv"]
            prefix = [sys.executable] if frozen else [sys.executable, "-m", "researchgraph"]
            assert argv[: len(prefix)] == prefix
            assert argv[len(prefix) :] == [
                "--translation-server",
                "--translation-port",
                str(runtime._port),
                "--translation-root",
                str(root),
                "--output-dir",
                str(launch["work"]),
            ]
            assert launch["cwd"] == Path(sys.executable).parent
            env = launch["env"]
            assert runtime.service_token and len(runtime.service_token) >= 32
            assert env["RGS_TRANSLATION_SERVICE_TOKEN"] == runtime.service_token
            assert runtime.service_token not in subprocess.list2cmdline(argv)
            assert "must-not-reuse-parent-ticket" not in env.values()
            assert env["RGS_TRANSLATION_CACHE"] == str(tmp_path / "translation-runtime-cache")
            assert "SYNTHETIC_API_KEY" not in env and "HTTPS_PROXY" not in env
            if frozen:
                assert "PYTHONPATH" not in env
            else:
                assert env["PYTHONPATH"] == str(Path(runtime_module.__file__).resolve().parents[1])
            assert clients == [{"trust_env": False, "follow_redirects": False, "timeout": 0.5}]
            assert len(requests) == 1
            assert str(requests[0].url) == runtime.service_url + "/health"
            assert requests[0].headers["authorization"] == f"Bearer {runtime.service_token}"
            await runtime.ensure_owned()
        assert process.stop_calls == 1
        assert not launches[0]["work"].exists()
        await runtime.stop()
        assert process.stop_calls == 1
        with pytest.raises(KnowledgeError) as caught:
            await runtime.ensure_owned()
        assert caught.value.code == "TRANSLATION_RUNTIME_OWNERSHIP_LOST"
        with pytest.raises(KnowledgeError) as reused:
            async with runtime:
                pytest.fail("a stopped runtime must not restart")
        assert reused.value.code == "TRANSLATION_RUNTIME_REUSED"

    asyncio.run(run())


@pytest.mark.parametrize(
    ("status", "version", "owned", "alive", "expected"),
    [
        (200, "incompatible-version", True, True, "TRANSLATION_RUNTIME_VERSION_UNSUPPORTED"),
        (401, "ignored", True, True, "TRANSLATION_RUNTIME_START_TIMEOUT"),
        (200, "ignored", False, True, "TRANSLATION_RUNTIME_START_TIMEOUT"),
        (200, "ignored", True, False, "TRANSLATION_RUNTIME_EXITED"),
    ],
)
def test_unready_bundle_rejects_wrong_version_auth_and_listener_then_cleans_own_work(
    bundle_paths, tmp_path, monkeypatch, status, version, owned, alive, expected
):
    process, launches = patch_process(monkeypatch)
    process.listener_owned, process.running = owned, alive
    _, requests = patch_health(
        monkeypatch,
        lambda _request: httpx.Response(status, json={"status": "ok", "version": version}),
    )

    async def run():
        runtime = ManagedTranslationRuntime(TranslationSettings(), tmp_path, startup_timeout=0.05)
        with pytest.raises(KnowledgeError) as caught:
            async with runtime:
                pytest.fail("an unverified owned listener must not become usable")
        assert caught.value.code == expected
        assert process.stop_calls == 1
        assert not launches[0]["work"].exists()
        if not owned or not alive:
            assert not requests
        await runtime.stop()
        assert process.stop_calls == 1

    asyncio.run(run())


def test_bundled_spawn_failure_removes_only_its_work_directory(bundle_paths, tmp_path, monkeypatch):
    _, launches = patch_process(monkeypatch, error=OSError("synthetic create-process failure"))
    retained = tmp_path / "translation-work" / "retained-other-task"
    retained.mkdir(parents=True)
    (retained / "output.pdf").write_bytes(b"keep another task")

    async def run():
        runtime = ManagedTranslationRuntime(TranslationSettings(), tmp_path)
        with pytest.raises(KnowledgeError) as caught:
            async with runtime:
                pytest.fail("spawn failure cannot enter a context")
        assert caught.value.code == "TRANSLATION_RUNTIME_START_FAILED"
        assert len(launches) == 1
        assert not launches[0]["work"].exists()
        assert (retained / "output.pdf").read_bytes() == b"keep another task"
        await runtime.stop()

    asyncio.run(run())


def test_bundled_cancellation_before_start_never_spawns(bundle_paths, tmp_path, monkeypatch):
    _, launches = patch_process(monkeypatch)

    async def run():
        runtime = ManagedTranslationRuntime(TranslationSettings(), tmp_path, cancelled=lambda: True)
        with pytest.raises(KnowledgeError) as caught:
            async with runtime:
                pytest.fail("cancelled task must not start the bundled engine")
        assert caught.value.code == "TRANSLATION_CANCELLED"
        assert not launches
        assert not (tmp_path / "translation-work").exists()

    asyncio.run(run())
