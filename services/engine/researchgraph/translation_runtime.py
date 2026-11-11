"""Task-scoped ownership of an independently installed PDF translation server.

This module never installs or imports external code, opens a shell, reads model
credentials, or attaches to an existing server. Windows creates the server in a
non-inheritable kill-on-close Job *atomically*, before its first instruction.
"""

import ast
import asyncio
import inspect
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, Self
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from researchgraph.core import KnowledgeError

CancelCheck = Callable[[], bool | Awaitable[bool]]


class RuntimeSettings(Protocol):
    @property
    def launch_mode(self) -> str: ...

    @property
    def service_url(self) -> str: ...

    @property
    def python_path(self) -> str | None: ...

    @property
    def server_path(self) -> str | None: ...


class _OwnedProcess(Protocol):
    pid: int

    def alive(self) -> bool: ...

    def stop(self) -> None: ...

    def owns_listener(self, host: str, port: int) -> bool: ...


def _local_file(value: str | None, *, python: bool) -> Path:
    try:
        path = Path(value or "")
        if (
            not value
            or "\x00" in value
            or not path.is_absolute()
            or str(path).startswith("\\\\")
            or path.is_symlink()
            or not path.is_file()
        ):
            raise ValueError
        resolved = path.resolve(strict=True)
        if str(resolved).startswith("\\\\"):
            raise ValueError
        if python:
            if os.name == "nt" and resolved.name.lower() not in {"python.exe", "pythonw.exe"}:
                raise ValueError
            if os.name != "nt" and not os.access(resolved, os.X_OK):
                raise ValueError
        elif resolved.name.lower() != "server.py" or resolved.stat().st_size > 4_000_000:
            raise ValueError
        return resolved
    except (OSError, ValueError, RuntimeError):
        label = "Python 可执行文件" if python else "server.py"
        raise KnowledgeError(
            "TRANSLATION_RUNTIME_PATH_INVALID", f"请指定独立翻译环境中本机绝对路径的 {label}"
        ) from None


def _environment(python: Path) -> dict[str, str]:
    # Do not pass PYTHONPATH, proxy variables, or API credentials to the external
    # installation. Its CLI resolves pdf2zh_next from this interpreter's PATH.
    allowed = {
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "HOMEDRIVE",
        "HOMEPATH",
        "PROGRAMDATA",
        "HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    paths = [python.parent, python.parent / "Scripts", python.parent / "Library" / "bin"]
    env["PATH"] = os.pathsep.join([*(str(path) for path in paths), os.defpath])
    # A Windows Conda environment also needs the OS utility directories, without
    # inheriting another environment's Scripts entry or user executable search.
    if os.name == "nt":
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        env["PATH"] += os.pathsep + os.pathsep.join(
            str(path) for path in (system_root / "System32", system_root)
        )
    env.update(PYTHONUTF8="1", PYTHONNOUSERSITE="1", PYTHONUNBUFFERED="1")
    return env


class _PosixProcess:
    def __init__(self, argv: list[str], cwd: Path, env: Mapping[str, str]):
        self.process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        self.pid = self.process.pid
        self._closed = False

    def alive(self) -> bool:
        if sys.platform == "win32":
            raise RuntimeError("POSIX process requested on Windows")
        # Keep an exited leader unreaped until stop, preventing its PID/group ID
        # from being reused while we still own and must stop its descendants.
        result = os.waitid(os.P_PID, self.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        return result is None

    def owns_listener(self, host: str, port: int) -> bool:
        if not sys.platform.startswith("linux"):
            raise OSError("Managed server listener ownership is unavailable on this platform")
        inodes = set()
        for fd in Path(f"/proc/{self.pid}/fd").iterdir():
            try:
                link = fd.readlink().as_posix()
            except OSError:
                continue
            if link.startswith("socket:["):
                inodes.add(link[8:-1])
        address = socket.inet_aton(host)[::-1].hex().upper()
        for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
            fields = line.split()
            if fields[1] == f"{address}:{port:04X}" and fields[3] == "0A" and fields[9] in inodes:
                return True
        return False

    def stop(self) -> None:
        if sys.platform == "win32":
            raise RuntimeError("POSIX process requested on Windows")
        if self._closed:
            return
        self._closed = True
        try:
            os.killpg(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=5)


def _spawn_windows(argv: list[str], cwd: Path, env: Mapping[str, str]) -> _OwnedProcess:
    # Keep Windows-only imports local so the module remains importable in Linux
    # CI. The API structures use pointer-sized fields, including on x64.
    import ctypes
    from ctypes import wintypes

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.DWORD),
            ("descriptor", wintypes.LPVOID),
            ("inherit", wintypes.BOOL),
        ]

    class StartupInfo(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("reserved", wintypes.LPWSTR),
            ("desktop", wintypes.LPWSTR),
            ("title", wintypes.LPWSTR),
            ("x", wintypes.DWORD),
            ("y", wintypes.DWORD),
            ("x_size", wintypes.DWORD),
            ("y_size", wintypes.DWORD),
            ("x_chars", wintypes.DWORD),
            ("y_chars", wintypes.DWORD),
            ("fill", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("show", wintypes.WORD),
            ("reserved_size", wintypes.WORD),
            ("reserved_bytes", ctypes.POINTER(ctypes.c_byte)),
            ("stdin", wintypes.HANDLE),
            ("stdout", wintypes.HANDLE),
            ("stderr", wintypes.HANDLE),
        ]

    class StartupInfoEx(ctypes.Structure):
        _fields_ = [("info", StartupInfo), ("attributes", wintypes.LPVOID)]

    class ProcessInfo(ctypes.Structure):
        _fields_ = [
            ("process", wintypes.HANDLE),
            ("thread", wintypes.HANDLE),
            ("pid", wintypes.DWORD),
            ("tid", wintypes.DWORD),
        ]

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_int64),
            ("job_time", ctypes.c_int64),
            ("flags", wintypes.DWORD),
            ("min_working", ctypes.c_size_t),
            ("max_working", ctypes.c_size_t),
            ("active_limit", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in (
                "read_ops",
                "write_ops",
                "other_ops",
                "read_bytes",
                "write_bytes",
                "other_bytes",
            )
        ]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("basic", BasicLimit),
            ("io", IoCounters),
            ("process_mem", ctypes.c_size_t),
            ("job_mem", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t),
            ("peak_job", ctypes.c_size_t),
        ]

    class BasicAccounting(ctypes.Structure):
        _fields_ = [
            ("user_time", ctypes.c_int64),
            ("kernel_time", ctypes.c_int64),
            ("period_user_time", ctypes.c_int64),
            ("period_kernel_time", ctypes.c_int64),
            ("page_faults", wintypes.DWORD),
            ("total_processes", wintypes.DWORD),
            ("active_processes", wintypes.DWORD),
            ("terminated_processes", wintypes.DWORD),
        ]

    kernel: Any = ctypes.WinDLL("kernel32", use_last_error=True)

    def signature(name: str, args: list[Any], result: Any) -> Any:
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
        return function

    handle, ptr, dword, boolean = (wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.BOOL)
    close = signature("CloseHandle", [handle], boolean)
    create_job = signature("CreateJobObjectW", [ptr, wintypes.LPCWSTR], handle)
    set_job = signature("SetInformationJobObject", [handle, ctypes.c_int, ptr, dword], boolean)
    terminate_job = signature("TerminateJobObject", [handle, wintypes.UINT], boolean)
    query_job = signature(
        "QueryInformationJobObject", [handle, ctypes.c_int, ptr, dword, ptr], boolean
    )
    wait = signature("WaitForSingleObject", [handle, dword], dword)
    resume = signature("ResumeThread", [handle], dword)
    create_file = signature(
        "CreateFileW", [wintypes.LPCWSTR, dword, dword, ptr, dword, dword, handle], handle
    )
    initialize = signature(
        "InitializeProcThreadAttributeList",
        [ptr, dword, dword, ctypes.POINTER(ctypes.c_size_t)],
        boolean,
    )
    update = signature(
        "UpdateProcThreadAttribute",
        [ptr, dword, ctypes.c_size_t, ptr, ctypes.c_size_t, ptr, ptr],
        boolean,
    )
    delete = signature("DeleteProcThreadAttributeList", [ptr], None)
    create_process = signature(
        "CreateProcessW",
        [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            ptr,
            ptr,
            boolean,
            dword,
            ptr,
            wintypes.LPCWSTR,
            ptr,
            ptr,
        ],
        boolean,
    )

    def require(success: Any) -> None:
        if not success:
            raise ctypes.WinError(ctypes.get_last_error())

    job = create_job(None, None)
    require(job)
    process_info = ProcessInfo()
    nul = None
    attributes = None
    initialized = False
    try:
        limits = ExtendedLimit()
        limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        require(set_job(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        security = SecurityAttributes(ctypes.sizeof(SecurityAttributes), None, True)
        nul = create_file("NUL", 0xC0000000, 3, ctypes.byref(security), 3, 0x80, None)
        if nul == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        size = ctypes.c_size_t()
        initialize(None, 2, 0, ctypes.byref(size))
        attributes = ctypes.create_string_buffer(size.value)
        require(initialize(attributes, 2, 0, ctypes.byref(size)))
        initialized = True
        inherited = (handle * 1)(nul)
        jobs = (handle * 1)(job)
        # JOB_LIST (Win10+) assigns the job inside CreateProcess. A separate
        # suspended->Assign call would leave a parent-crash orphan window.
        require(update(attributes, 0, 0x0002000D, jobs, ctypes.sizeof(jobs), None, None))
        require(update(attributes, 0, 0x00020002, inherited, ctypes.sizeof(inherited), None, None))
        startup = StartupInfoEx()
        startup.info.cb = ctypes.sizeof(startup)
        startup.info.flags = 0x00000101  # STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW
        startup.info.show = 0  # SW_HIDE
        startup.info.stdin = startup.info.stdout = startup.info.stderr = nul
        startup.attributes = ctypes.cast(attributes, ptr)
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        environment = ctypes.create_unicode_buffer(
            "\x00".join(f"{key}={value}" for key, value in sorted(env.items())) + "\x00\x00"
        )
        require(
            create_process(
                argv[0],
                command,
                None,
                None,
                True,
                0x08000000 | 0x00000004 | 0x00080000 | 0x00000400,
                environment,
                str(cwd),
                ctypes.byref(startup),
                ctypes.byref(process_info),
            )
        )  # NO_WINDOW | SUSPENDED | EXTENDED_STARTUPINFO | UNICODE_ENVIRONMENT
        if resume(process_info.thread) == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        terminate_job(job, 1)
        close(job)
        if process_info.process:
            wait(process_info.process, 5000)
            close(process_info.process)
        raise
    finally:
        if process_info.thread:
            close(process_info.thread)
        if initialized:
            delete(attributes)
        if nul and nul != ctypes.c_void_p(-1).value:
            close(nul)

    class WindowsProcess:
        def __init__(self) -> None:
            self.pid = int(process_info.pid)
            self._job = job
            self._handle = process_info.process

        def alive(self) -> bool:
            return bool(self._handle and wait(self._handle, 0) == 0x00000102)

        def stop(self) -> None:
            if not self._job:
                return
            terminate_job(self._job, 1)
            confirmed = False
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                accounting = BasicAccounting()
                if not query_job(
                    self._job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
                ):
                    break
                if accounting.active_processes == 0:
                    confirmed = True
                    break
                time.sleep(0.01)
            close(self._job)  # kill-on-close remains effective if Terminate fails
            self._job = None
            if self._handle:
                wait(self._handle, 5000)
                close(self._handle)
                self._handle = None
            if not confirmed:
                raise KnowledgeError(
                    "TRANSLATION_RUNTIME_STOP_UNCONFIRMED",
                    "自建翻译进程的停止未能确认；已关闭专属进程组，不能将任务标记为完成",
                )

        def owns_listener(self, host: str, port: int) -> bool:
            class TcpRow(ctypes.Structure):
                _fields_ = [
                    (name, dword)
                    for name in ("state", "address", "port", "remote_address", "remote_port", "pid")
                ]

            iphlp: Any = ctypes.WinDLL("iphlpapi", use_last_error=True)
            table = iphlp.GetExtendedTcpTable
            table.argtypes = [
                ptr,
                ctypes.POINTER(dword),
                boolean,
                wintypes.ULONG,
                ctypes.c_int,
                wintypes.ULONG,
            ]
            table.restype = dword
            size = dword()
            table(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
            buffer = ctypes.create_string_buffer(size.value)
            if table(buffer, ctypes.byref(size), False, socket.AF_INET, 3, 0) != 0:
                raise OSError("Cannot verify managed listener owner")
            count = dword.from_buffer(buffer).value
            for index in range(count):
                offset = ctypes.sizeof(dword) + index * ctypes.sizeof(TcpRow)
                row = TcpRow.from_buffer(buffer, offset)
                address = socket.inet_ntoa(int(row.address).to_bytes(4, "little"))
                if (
                    row.pid == self.pid
                    and socket.ntohs(row.port & 0xFFFF) == port
                    and address == host
                ):
                    return True
            return False

    return WindowsProcess()


class ManagedTranslationRuntime:
    def __init__(
        self,
        settings: RuntimeSettings,
        data_dir: Path,
        *,
        cancelled: CancelCheck | None = None,
        startup_timeout: float = 90.0,
    ):
        self.settings = settings
        self.service_url = settings.service_url
        self.service_token: str | None = None
        self.expected_version = "4.1.8"
        self.data_dir = Path(data_dir)
        self.cancelled = cancelled
        self.startup_timeout = min(180.0, max(0.05, startup_timeout))
        self._process: _OwnedProcess | None = None
        self._stop_task: asyncio.Task[None] | None = None
        self._entered = False
        self._python: Path | None = None
        self._server: Path | None = None
        self._host = "127.0.0.1"
        self._port = 0
        self._work_dir: Path | None = None
        self._bundle: Path | None = None

    def validate(self, *, check_port: bool = True) -> None:
        """Read local files and port state only; never execute the installation."""
        if self.settings.launch_mode == "manual":
            return
        if self.settings.launch_mode == "bundled":
            from researchgraph.translation_bundled import (
                BUNDLED_SERVICE_VERSION,
                find_bundled_root,
                validate_bundled_root,
            )

            self._bundle = find_bundled_root()
            validate_bundled_root(self._bundle)
            self.expected_version = BUNDLED_SERVICE_VERSION
            return
        if self.settings.launch_mode != "managed":
            raise KnowledgeError("TRANSLATION_RUNTIME_INVALID", "翻译服务启动模式无效")
        parsed = urlsplit(self.service_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise KnowledgeError(
                "TRANSLATION_RUNTIME_ADDRESS_INVALID", "自动启动仅支持 127.0.0.1 的本机 HTTP 地址"
            )
        try:
            self._port = parsed.port or 0
        except ValueError:
            self._port = 0
        if not 1 <= self._port <= 65535:
            raise KnowledgeError("TRANSLATION_RUNTIME_ADDRESS_INVALID", "翻译服务端口无效")
        self._python = _local_file(self.settings.python_path, python=True)
        self._server = _local_file(self.settings.server_path, python=False)
        try:
            tree = ast.parse(self._server.read_text(encoding="utf-8-sig"))
            versions = [
                node.value.value
                for node in tree.body
                if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and any(
                    isinstance(target, ast.Name) and target.id == "__version__"
                    for target in node.targets
                )
            ]
            if versions != ["4.1.8"]:
                raise ValueError
        except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError):
            raise KnowledgeError(
                "TRANSLATION_RUNTIME_VERSION_UNSUPPORTED", "自动启动仅支持独立安装的 Server 4.1.8"
            ) from None
        if check_port:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                try:
                    if os.name == "nt":
                        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    probe.bind((self._host, self._port))
                except OSError:
                    raise KnowledgeError(
                        "TRANSLATION_RUNTIME_PORT_IN_USE",
                        "自动启动端口已被占用；请换一个专用空闲端口，软件不会接管或关闭已有服务",
                    ) from None

    async def _check_cancelled(self) -> None:
        if self.cancelled is None:
            return
        result = self.cancelled()
        if inspect.isawaitable(result):
            result = await result
        if result:
            raise KnowledgeError("TRANSLATION_CANCELLED", "翻译任务已取消，自动启动已停止")

    async def __aenter__(self) -> Self:
        if self._entered:
            raise KnowledgeError("TRANSLATION_RUNTIME_REUSED", "自动翻译服务实例只能启动一次")
        self._entered = True
        self.validate()
        if self.settings.launch_mode == "manual":
            return self
        await self._check_cancelled()
        if self.settings.launch_mode == "bundled":
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((self._host, 0))
                self._port = probe.getsockname()[1]
            self.service_url = f"http://{self._host}:{self._port}"
            self.service_token = secrets.token_urlsafe(32)
            self._work_dir = self.data_dir / "translation-work" / str(uuid4())
            self._work_dir.mkdir(parents=True, exist_ok=False)
            assert self._bundle is not None
            argv = [sys.executable]
            if not getattr(sys, "frozen", False):
                argv.extend(["-m", "researchgraph"])
            argv.extend(
                [
                    "--translation-server",
                    "--translation-port",
                    str(self._port),
                    "--translation-root",
                    str(self._bundle),
                    "--output-dir",
                    str(self._work_dir),
                ]
            )
            cwd = Path(sys.executable).parent
            env = _environment(Path(sys.executable))
            # Source execution needs only this project's import root. Frozen
            # execution deliberately inherits no user Python search path.
            if not getattr(sys, "frozen", False):
                env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
            env["RGS_TRANSLATION_SERVICE_TOKEN"] = self.service_token
            env["RGS_TRANSLATION_CACHE"] = str(self.data_dir / "translation-runtime-cache")
        else:
            assert self._python is not None and self._server is not None
            argv = [
                str(self._python),
                "-u",
                str(self._server),
                "--host",
                self._host,
                "--port",
                str(self._port),
                "--enable_venv",
                "false",
                "--skip_install",
                "true",
                "--check_update",
                "false",
                "--enable_mirror",
                "false",
                "--enable_winexe",
                "false",
                "--debug",
                "false",
            ]
            cwd = self._server.parent
            env = _environment(self._python)
        try:
            self._process = (
                _spawn_windows(argv, cwd, env) if os.name == "nt" else _PosixProcess(argv, cwd, env)
            )
            await self._wait_ready()
            return self
        except BaseException as error:
            await self.stop()
            if isinstance(error, (KnowledgeError, asyncio.CancelledError)):
                raise
            raise KnowledgeError(
                "TRANSLATION_RUNTIME_START_FAILED",
                "无法自动启动翻译服务；请检查独立环境依赖、目录权限和版本，未接管已有服务",
            ) from None

    async def _wait_ready(self) -> None:
        deadline = time.monotonic() + self.startup_timeout
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=0.5
        ) as client:
            while time.monotonic() < deadline:
                await self._check_cancelled()
                assert self._process is not None
                if not self._process.alive():
                    raise KnowledgeError(
                        "TRANSLATION_RUNTIME_EXITED",
                        "独立翻译服务启动后退出，请检查环境依赖和目录权限",
                    )
                if self._process.owns_listener(self._host, self._port):
                    try:
                        headers = (
                            {"Authorization": f"Bearer {self.service_token}"}
                            if self.service_token
                            else {}
                        )
                        response = await client.get(self.service_url + "/health", headers=headers)
                        data = response.json() if response.status_code == 200 else {}
                        if isinstance(data, dict) and data.get("status") == "ok":
                            if data.get("version") != self.expected_version:
                                raise KnowledgeError(
                                    "TRANSLATION_RUNTIME_VERSION_UNSUPPORTED",
                                    "自动启动的服务版本不兼容，已停止自建进程",
                                )
                            await self._check_cancelled()
                            return
                    except (httpx.HTTPError, json.JSONDecodeError, UnicodeError):
                        pass
                await asyncio.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        raise KnowledgeError(
            "TRANSLATION_RUNTIME_START_TIMEOUT", "翻译服务未能在时限内就绪，已停止自建进程"
        )

    async def stop(self) -> None:
        """Idempotently stop only this context's tree, including engine children."""
        if self._process is None:
            if self._work_dir is not None:
                await asyncio.to_thread(shutil.rmtree, self._work_dir, True)
            return
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(asyncio.to_thread(self._process.stop))
        try:
            await asyncio.shield(self._stop_task)
        except asyncio.CancelledError:
            await asyncio.shield(self._stop_task)
            raise
        finally:
            if self._stop_task.done():
                self._process = None
                if self._work_dir is not None:
                    await asyncio.to_thread(shutil.rmtree, self._work_dir, True)

    async def ensure_owned(self) -> None:
        """Reject replacement listeners throughout a managed translation task."""
        if self.settings.launch_mode == "manual":
            return
        process = self._process
        owned = False
        if process is not None and self._stop_task is None:
            try:
                owned = await asyncio.to_thread(
                    lambda: process.alive() and process.owns_listener(self._host, self._port)
                )
            except Exception:
                owned = False
        if not owned or self._process is not process or self._stop_task is not None:
            raise KnowledgeError(
                "TRANSLATION_RUNTIME_OWNERSHIP_LOST",
                "自动启动的翻译服务已退出或端口归属改变；已拒绝使用替代服务，请重新启动任务",
            )

    async def __aexit__(self, *_: Any) -> None:
        await self.stop()
