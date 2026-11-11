"""Owned synthetic processes only: no real PDF, engine, key, or model request."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from researchgraph.core import KnowledgeError
from researchgraph.translation_contracts import TranslationSettings
from researchgraph.translation_runtime import ManagedTranslationRuntime


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return server.getsockname()[1]


def _running(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 0x102
        finally:
            kernel.CloseHandle(handle)
    try:
        # A dead child may remain a zombie until its synthetic parent is reaped.
        return Path(f"/proc/{pid}/stat").read_text().split(") ")[1][0] != "Z"
    except (OSError, IndexError):
        return False


def _wait_dead(pids):
    deadline = time.monotonic() + 5
    while any(_running(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(0.025)
    assert all(not _running(pid) for pid in pids), pids


def _install(tmp_path, *, mode="ready", version="4.1.8", health_version="4.1.8"):
    # Spaces and Unicode exercise Windows CreateProcess command-line quoting.
    directory = tmp_path / "独立 translation environment"
    directory.mkdir()
    (directory / "grandchild.py").write_text(
        "import os,time\nfrom pathlib import Path\n"
        "Path(__file__).with_suffix('.pid').write_text(str(os.getpid()))\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    (directory / "child.py").write_text(
        "import subprocess,sys,time\nfrom pathlib import Path\n"
        "subprocess.Popen([sys.executable, str(Path(__file__).with_name('grandchild.py'))],"
        " stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    script = (
        textwrap.dedent("""\
        import argparse,json,os,subprocess,sys,time
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from pathlib import Path
        __version__ = VERSION
        parser=argparse.ArgumentParser()
        parser.add_argument('--host')
        parser.add_argument('--port',type=int)
        for name in ('enable_venv','skip_install','check_update','enable_mirror',
                     'enable_winexe','debug'):
            parser.add_argument('--'+name)
        args=parser.parse_args()
        directory=Path(__file__).parent
        child=subprocess.Popen([sys.executable,str(directory/'child.py')],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        (directory/'server.json').write_text(json.dumps({
            'pid':os.getpid(),'child':child.pid,'args':vars(args),'cwd':str(Path.cwd()),
            'inherited_secret':'SYNTHETIC_API_KEY' in os.environ,
            'inherited_pythonpath':'PYTHONPATH' in os.environ,
            'stdin':sys.stdin.read(1)}))
        deadline=time.monotonic()+5
        while not (directory/'grandchild.pid').exists() and time.monotonic()<deadline:
            time.sleep(0.01)
        print('discarded synthetic stdout')
        print('discarded synthetic stderr',file=sys.stderr)
        if MODE == 'exit':
            time.sleep(0.4)
            sys.exit(8)
        if MODE == 'never':
            time.sleep(120)
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                data=json.dumps({'status':'ok','version':HEALTH_VERSION}).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self,*args):
                pass
        ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
        """)
        .replace("VERSION", repr(version), 1)
        .replace("MODE", repr(mode))
    )
    script = script.replace("HEALTH_VERSION", repr(health_version))
    server_path = directory / "server.py"
    server_path.write_text(script, encoding="utf-8")
    settings = TranslationSettings(
        enabled=True,
        launch_mode="managed",
        service_url=f"http://127.0.0.1:{_free_port()}",
        python_path=str(Path(sys.executable).resolve()),
        server_path=str(server_path),
    )
    return directory, settings


async def _pids(directory):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            data = json.loads((directory / "server.json").read_text())
            grandchild = int((directory / "grandchild.pid").read_text())
            return [data["pid"], data["child"], grandchild]
        except (OSError, ValueError):
            await asyncio.sleep(0.025)
    raise AssertionError("Synthetic three-level process tree was not created")


def test_manual_context_never_spawns_or_requires_paths(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("manual mode must not start a process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)

    async def run():
        runtime = ManagedTranslationRuntime(TranslationSettings(launch_mode="manual"), tmp_path)
        runtime.validate()
        await runtime.ensure_owned()
        async with runtime:
            assert runtime.service_url == "http://127.0.0.1:8890"
        await runtime.stop()

    asyncio.run(run())


@pytest.mark.parametrize("change", ["python", "relative", "script", "version", "ipv6"])
def test_local_validation_rejects_invalid_installation_without_spawning(
    tmp_path, monkeypatch, change
):
    directory, settings = _install(tmp_path)
    if change == "python":
        settings.python_path = str(directory / "missing-python.exe")
    elif change == "relative":
        settings.server_path = "server.py"
    elif change == "script":
        (directory / "server.py").write_text("not valid Python!", encoding="utf-8")
    elif change == "version":
        text = (directory / "server.py").read_text(encoding="utf-8")
        (directory / "server.py").write_text(text.replace("'4.1.8'", "'4.1.7'"))
    elif change == "ipv6":
        settings.service_url = "http://[::1]:8890"

    def forbidden(*_args, **_kwargs):
        pytest.fail("validate must not execute an interpreter")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(KnowledgeError):
        ManagedTranslationRuntime(settings, tmp_path).validate()
    assert not (directory / "server.json").exists()


def test_occupied_port_is_never_adopted_or_stopped(tmp_path):
    directory, settings = _install(tmp_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        settings.service_url = f"http://127.0.0.1:{occupied.getsockname()[1]}"
        runtime = ManagedTranslationRuntime(settings, tmp_path)
        with pytest.raises(KnowledgeError) as caught:
            runtime.validate()
        assert caught.value.code == "TRANSLATION_RUNTIME_PORT_IN_USE"
        runtime.validate(check_port=False)
        assert occupied.fileno() >= 0
        assert not (directory / "server.json").exists()


def test_managed_context_closes_real_three_level_tree_and_stops_idempotently(tmp_path, monkeypatch):
    directory, settings = _install(tmp_path)
    monkeypatch.setenv("SYNTHETIC_API_KEY", "synthetic-only-do-not-inherit")
    monkeypatch.setenv("PYTHONPATH", "synthetic-invalid-pythonpath")

    async def run():
        runtime = ManagedTranslationRuntime(settings, tmp_path, startup_timeout=10)
        runtime.validate()
        assert not (directory / "server.json").exists()
        async with runtime:
            pids = await _pids(directory)
            assert all(_running(pid) for pid in pids)
            await runtime.ensure_owned()
            async with httpx.AsyncClient(trust_env=False) as client:
                assert (await client.get(runtime.service_url + "/health")).status_code == 200
            recorded = json.loads((directory / "server.json").read_text())
            assert recorded["cwd"] == str(directory)
            assert recorded["stdin"] == ""
            assert not recorded["inherited_secret"]
            assert not recorded["inherited_pythonpath"]
            assert recorded["args"]["enable_venv"] == "false"
            assert recorded["args"]["skip_install"] == "true"
            assert recorded["args"]["check_update"] == "false"
            assert recorded["args"]["enable_mirror"] == "false"
            assert recorded["args"]["enable_winexe"] == "false"
            assert recorded["args"]["debug"] == "false"
            await runtime.stop()  # caller may stop before publishing COMPLETED
            await runtime.stop()
            with pytest.raises(KnowledgeError) as caught:
                await runtime.ensure_owned()
            assert caught.value.code == "TRANSLATION_RUNTIME_OWNERSHIP_LOST"
        _wait_dead(pids)
        with pytest.raises(KnowledgeError):
            async with runtime:
                pytest.fail("runtime must not restart")

    asyncio.run(run())


def _terminate_original_server(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateProcess.restype = wintypes.BOOL
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100001, False, pid)
        assert handle
        try:
            assert kernel.TerminateProcess(handle, 8)
            assert kernel.WaitForSingleObject(handle, 5000) == 0
        finally:
            kernel.CloseHandle(handle)
    else:
        import signal

        os.kill(pid, signal.SIGKILL)


def test_lost_listener_is_rejected_and_replacement_service_is_never_stopped(tmp_path):
    directory, settings = _install(tmp_path)

    class Replacement(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"independent replacement"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    async def run():
        runtime = ManagedTranslationRuntime(settings, tmp_path, startup_timeout=10)
        with pytest.raises(KnowledgeError) as not_started:
            await runtime.ensure_owned()
        assert not_started.value.code == "TRANSLATION_RUNTIME_OWNERSHIP_LOST"
        async with runtime:
            pids = await _pids(directory)
            _terminate_original_server(pids[0])
            port = urlsplit(runtime.service_url).port
            deadline = time.monotonic() + 5
            while True:
                try:
                    replacement = ThreadingHTTPServer(("127.0.0.1", port), Replacement)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    await asyncio.sleep(0.025)
            serving = threading.Thread(target=replacement.serve_forever, daemon=True)
            serving.start()
            try:
                async with httpx.AsyncClient(trust_env=False) as client:
                    response = await client.get(runtime.service_url + "/health")
                    assert response.text == "independent replacement"
                    with pytest.raises(KnowledgeError) as lost:
                        await runtime.ensure_owned()
                    assert lost.value.code == "TRANSLATION_RUNTIME_OWNERSHIP_LOST"
                    await runtime.stop()
                    _wait_dead(pids)
                    assert (await client.get(runtime.service_url + "/health")).text == (
                        "independent replacement"
                    )
            finally:
                await asyncio.to_thread(replacement.shutdown)
                replacement.server_close()
                serving.join(timeout=5)

    asyncio.run(run())


@pytest.mark.parametrize(
    ("mode", "health_version", "expected"),
    [
        ("never", "4.1.8", "TRANSLATION_RUNTIME_START_TIMEOUT"),
        ("exit", "4.1.8", "TRANSLATION_RUNTIME_EXITED"),
        ("ready", "4.2.0", "TRANSLATION_RUNTIME_VERSION_UNSUPPORTED"),
    ],
)
def test_failed_start_always_stops_own_descendants(tmp_path, mode, health_version, expected):
    directory, settings = _install(tmp_path, mode=mode, health_version=health_version)

    async def run():
        runtime = ManagedTranslationRuntime(settings, tmp_path, startup_timeout=1.5)
        with pytest.raises(KnowledgeError) as caught:
            async with runtime:
                pytest.fail("invalid server must never become usable")
        assert caught.value.code == expected
        pids = await _pids(directory)
        _wait_dead(pids)
        await runtime.stop()

    asyncio.run(run())


@pytest.mark.parametrize("async_callback", [False, True])
def test_startup_cancellation_callback_stops_owned_tree(tmp_path, async_callback):
    directory, settings = _install(tmp_path, mode="never")

    def cancelled():
        return (directory / "grandchild.pid").exists()

    async def async_cancelled():
        return cancelled()

    async def run():
        runtime = ManagedTranslationRuntime(
            settings,
            tmp_path,
            cancelled=async_cancelled if async_callback else cancelled,
            startup_timeout=10,
        )
        with pytest.raises(KnowledgeError) as caught:
            async with runtime:
                pytest.fail("cancelled startup cannot enter context")
        assert caught.value.code == "TRANSLATION_CANCELLED"
        _wait_dead(await _pids(directory))

    asyncio.run(run())


def test_async_task_cancel_during_startup_stops_owned_tree(tmp_path):
    directory, settings = _install(tmp_path, mode="never")

    async def run():
        runtime = ManagedTranslationRuntime(settings, tmp_path, startup_timeout=10)

        async def enter():
            async with runtime:
                pytest.fail("never-ready server cannot enter")

        task = asyncio.create_task(enter())
        pids = await _pids(directory)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        _wait_dead(pids)

    asyncio.run(run())


@pytest.mark.skipif(os.name != "nt", reason="Windows Job kill-on-close crash guarantee")
def test_owner_crash_kills_server_children_without_pid_killing(tmp_path):
    directory, settings = _install(tmp_path)
    supervisor = tmp_path / "synthetic-owner.py"
    source_root = Path(__file__).resolve().parents[2] / "services" / "engine"
    supervisor.write_text(
        "import asyncio,sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0,{str(source_root)!r})\n"
        "from researchgraph.translation_contracts import TranslationSettings\n"
        "from researchgraph.translation_runtime import ManagedTranslationRuntime\n"
        "async def main():\n"
        f"    settings=TranslationSettings.model_validate_json({settings.model_dump_json()!r})\n"
        f"    async with ManagedTranslationRuntime(settings,Path({str(tmp_path)!r})):\n"
        f"        Path({str(tmp_path / 'owner.ready')!r}).write_text('ready')\n"
        "        await asyncio.sleep(120)\n"
        "asyncio.run(main())\n",
        encoding="utf-8",
    )
    owner = subprocess.Popen(
        [sys.executable, str(supervisor)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        pids = asyncio.run(_pids(directory))
        deadline = time.monotonic() + 10
        while not (tmp_path / "owner.ready").exists() and time.monotonic() < deadline:
            assert owner.poll() is None
            time.sleep(0.025)
        assert (tmp_path / "owner.ready").exists()
        owner.kill()  # owned Popen handle, never taskkill / PID-based enumeration
        owner.wait(timeout=5)
        _wait_dead(pids)
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=5)
