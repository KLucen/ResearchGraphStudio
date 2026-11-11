"""Original, task-scoped HTTP adapter for the bundled official PDF translator.

The upstream CLI is never imported or executed during local preflight. Its only
model credential is a short-lived loopback proxy ticket in a task-local TOML
file. The parent runtime owns the complete Windows process tree in a Job.
"""

import asyncio
import base64
import binascii
import contextlib
import hmac
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import pymupdf
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from researchgraph.core import KnowledgeError

BUNDLED_ENGINE_ID = "pdf2zh-next-2.10.2-babeldoc-0.7.1-rgs-1"
BUNDLED_SERVICE_VERSION = "rgs-pdf2zh-2.10.2-1"
MAX_REQUEST_BYTES = 72 * 1024 * 1024
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_BYTES = 200 * 1024 * 1024
BUNDLED_REQUIRED_FILES = (
    "pdf2zh.exe",
    "_pystand_static.int",
    "runtime/pythonw.exe",
    "runtime/python313.dll",
    "runtime/python313.zip",
    "runtime/python313._pth",
    "site-packages/pdf2zh_next/main.py",
    "site-packages/babeldoc/format/pdf/high_level.py",
    "offline_assets_b485a82328a20d1e4b5c37bb9c6472e7af9943333bdffd39a05b1f57d6d7a1da.zip",
)
_NAME = re.compile(r"rg-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.pdf\Z")
_FIELDS = {
    "fileName",
    "fileContent",
    "asyncJob",
    "engine",
    "next_service",
    "sourceLang",
    "targetLang",
    "mono",
    "dual",
    "noMono",
    "noDual",
    "dualMode",
    "noWatermark",
    "qps",
    "poolSize",
    "disableGlossary",
    "ignoreCache",
    "llm_api",
}


def _ordinary(path: Path, *, directory: bool = False) -> bool:
    try:
        metadata = path.lstat()
        return (
            not stat.S_ISLNK(metadata.st_mode)
            and not getattr(metadata, "st_file_attributes", 0) & 0x400
            and (stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode))
        )
    except OSError:
        return False


def _local_directory(path: Path, *, create: bool = False) -> Path:
    if not path.is_absolute() or str(path).startswith("\\\\"):
        raise ValueError("local absolute directory required")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not _ordinary(path, directory=True):
        raise ValueError("ordinary directory required")
    resolved = path.resolve(strict=True)
    if str(resolved).startswith("\\\\"):
        raise ValueError("local directory required")
    # Junctions or symlink ancestors must not redirect a local path to a share.
    if any(not _ordinary(parent, directory=True) for parent in path.parents):
        raise ValueError("ordinary directory ancestors required")
    return resolved


def _bundle_file(root: Path, relative: str) -> Path:
    path = root / relative
    if not _ordinary(path) or path.stat().st_size == 0:
        raise ValueError("bundle file missing")
    for parent in path.parents:
        if parent == root:
            break
        if not _ordinary(parent, directory=True):
            raise ValueError("redirected bundle directory")
    if not path.resolve(strict=True).is_relative_to(root):
        raise ValueError("redirected bundle file")
    return path


def validate_bundled_root(root: Path) -> Path:
    """Check pinned manifest and critical local resources without executing code."""
    try:
        root = _local_directory(root)
        manifest_path = _bundle_file(root, "runtime-manifest.json")
        if manifest_path.stat().st_size > 64 * 1024:
            raise ValueError("manifest too large")
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
        if not isinstance(manifest, dict) or any(
            type(manifest.get(key)) is not type(value) or manifest.get(key) != value
            for key, value in {
                "format": 1,
                "engine_id": BUNDLED_ENGINE_ID,
                "pdf2zh_next": "2.10.2",
                "babeldoc": "0.7.1",
            }.items()
        ):
            raise ValueError("unsupported bundle")
        for relative in BUNDLED_REQUIRED_FILES:
            _bundle_file(root, relative)
        return root
    except (OSError, ValueError, RuntimeError):
        raise KnowledgeError(
            "TRANSLATION_BUNDLE_INVALID", "内置翻译组件缺失、版本不匹配或路径不安全，请修复安装"
        ) from None


def find_bundled_root() -> Path:
    """Locate installed resources, or the prepared bundle in a source checkout."""
    candidates: tuple[Path, ...]
    if getattr(sys, "frozen", False):
        candidates = (Path(sys.executable).parent / "translation-runtime",)
    else:
        project = Path(__file__).resolve().parents[3]
        candidates = (
            project / ".local" / "translation-bundle-2.10.2" / "pdf2zh",
            project / "apps" / "desktop" / "src-tauri" / "translation-runtime",
            project / "src-tauri" / "translation-runtime",
        )
    for candidate in candidates:
        if candidate.exists():
            return validate_bundled_root(candidate)
    raise KnowledgeError("TRANSLATION_BUNDLE_MISSING", "未找到内置翻译组件，请安装完整版本")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate field")
        value[key] = item
    return value


def _reject_constant(_value: str) -> None:
    raise ValueError("nonfinite JSON")


async def _body(request: Request) -> dict[str, Any]:
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if not length.isdecimal() or int(length) > MAX_REQUEST_BYTES:
                raise ValueError
        except ValueError:
            raise HTTPException(413, "Translation request is too large") from None
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise HTTPException(415, "JSON request required")
    raw = bytearray()
    async for part in request.stream():
        if len(raw) + len(part) > MAX_REQUEST_BYTES:
            raise HTTPException(413, "Translation request is too large")
        raw.extend(part)
    try:
        value = json.loads(raw, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
        if not isinstance(value, dict):
            raise ValueError("object required")
        return value
    except (ValueError, RecursionError):
        raise HTTPException(400, "Invalid translation request") from None


def _text(value: Any, *, limit: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > limit
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("invalid string")
    return value


@dataclass(frozen=True)
class _Submission:
    stem: str
    content: bytes
    proxy_url: str
    proxy_token: str
    model: str
    kinds: tuple[str, ...]


def _submission(body: dict[str, Any]) -> _Submission:
    if set(body) != _FIELDS:
        raise ValueError("unsupported fields")
    filename = _text(body["fileName"], limit=80)
    match = _NAME.fullmatch(filename)
    if match is None or str(UUID(match[1])) != match[1]:
        raise ValueError("invalid filename")
    for key, value in {
        "asyncJob": True,
        "engine": "pdf2zh_next",
        "next_service": "openai",
        "sourceLang": "en",
        "targetLang": "zh-CN",
        "dualMode": "LR",
        "noWatermark": True,
        "qps": 1,
        "poolSize": 1,
        "disableGlossary": True,
        "ignoreCache": True,
    }.items():
        if type(body[key]) is not type(value) or body[key] != value:
            raise ValueError("unsupported option")
    if any(type(body[key]) is not bool for key in ("mono", "dual", "noMono", "noDual")):
        raise ValueError("boolean option required")
    if body["mono"] == body["noMono"] or body["dual"] == body["noDual"]:
        raise ValueError("inconsistent outputs")
    kinds = tuple(kind for kind in ("mono", "dual") if body[kind])
    if not kinds:
        raise ValueError("output required")
    api = body["llm_api"]
    if not isinstance(api, dict) or set(api) != {"apiKey", "apiUrl", "model", "extraData"}:
        raise ValueError("invalid proxy settings")
    proxy_url = _text(api["apiUrl"])
    parsed = urlsplit(proxy_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or not 1 <= parsed.port <= 65535
        or parsed.netloc != f"127.0.0.1:{parsed.port}"
        or parsed.path != "/v1"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("loopback proxy required")
    ticket = _text(api["apiKey"], limit=256)
    if len(ticket) < 16 or re.fullmatch(r"[A-Za-z0-9_-]+", ticket) is None:
        raise ValueError("temporary proxy ticket required")
    model = _text(api["model"], limit=200)
    extra = api["extraData"]
    expected = {
        "openai_timeout": 120,
        "openai_enable_json_mode": False,
        "openai_send_temprature": False,
        "openai_send_reasoning_effort": False,
    }
    if (
        not isinstance(extra, dict)
        or set(extra) != set(expected)
        or any(
            type(extra[key]) is not type(value) or extra[key] != value
            for key, value in expected.items()
        )
    ):
        raise ValueError("unsupported model options")
    encoded = body["fileContent"]
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_PDF_BYTES + 2) // 3):
        raise ValueError("PDF too large")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("invalid PDF encoding") from None
    if not content or len(content) > MAX_PDF_BYTES or not _valid_pdf(content):
        raise ValueError("invalid PDF")
    return _Submission(filename[:-4], content, proxy_url, ticket, model, kinds)


def _valid_pdf(content: bytes) -> bool:
    if not content.startswith(b"%PDF-"):
        return False
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            return bool(document.is_pdf and not document.needs_pass and document.page_count > 0)
    except Exception:
        return False


def _read_pdf(path: Path) -> bytes:
    _local_directory(path.parent)
    if not _ordinary(path) or not 0 < path.stat().st_size <= MAX_OUTPUT_BYTES:
        raise ValueError("invalid output")
    with path.open("rb") as stream:
        content = stream.read(MAX_OUTPUT_BYTES + 1)
    if len(content) > MAX_OUTPUT_BYTES or not _valid_pdf(content):
        raise ValueError("invalid PDF output")
    return content


def _configuration(submission: _Submission) -> str:
    # JSON quoting is valid for these restricted TOML basic strings. No actual
    # model API key is available in this process or written to this file.
    values = {
        "openai_model": submission.model,
        "openai_base_url": submission.proxy_url,
        "openai_api_key": submission.proxy_token,
        "openai_timeout": "120",
    }
    return (
        "[openai_detail]\n"
        + "".join(
            f"{key} = {json.dumps(value, ensure_ascii=False)}\n" for key, value in values.items()
        )
        + (
            "openai_enable_json_mode = false\n"
            "openai_send_temprature = false\n"
            "openai_send_reasoning_effort = false\n"
        )
    )


def _cli_environment(root: Path, task_dir: Path, cache_dir: Path) -> dict[str, str]:
    allowed = {
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "PROGRAMDATA",
        "LANG",
        "LC_ALL",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    paths = [root, root / "runtime"]
    if os.name == "nt":
        windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        paths.extend((windows / "System32", windows))
    temporary = task_dir / "tmp"
    temporary.mkdir()
    environment.update(
        PATH=os.pathsep.join(str(path) for path in paths),
        HOME=str(cache_dir),
        USERPROFILE=str(cache_dir),
        APPDATA=str(cache_dir / "roaming"),
        LOCALAPPDATA=str(cache_dir / "local"),
        TEMP=str(temporary),
        TMP=str(temporary),
        TMPDIR=str(temporary),
        PYTHONUTF8="1",
        PYTHONNOUSERSITE="1",
        PYTHONUNBUFFERED="1",
        HF_HUB_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        DO_NOT_TRACK="1",
    )
    return environment


def _spawn_cli(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


async def _stop_cli(process: subprocess.Popen[bytes]) -> None:
    if sys.platform != "win32":
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    elif process.poll() is None:
        # Descendants inherit the parent runtime's atomic kill-on-close Job.
        with contextlib.suppress(ProcessLookupError, OSError):
            process.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        await asyncio.to_thread(process.wait, timeout=5)


@dataclass
class _Task:
    task_id: str
    directory: Path
    status: str = "running"
    filenames: list[str] = field(default_factory=list)
    worker: asyncio.Task[None] | None = None
    process: subprocess.Popen[bytes] | None = None

    def public(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "status": self.status,
            "active": self.status == "running",
            "finished": self.status != "running",
            "progress": 100 if self.status == "success" else 0,
            "fileList": list(self.filenames),
        }


async def _run(root: Path, cache_dir: Path, task: _Task, submission: _Submission) -> None:
    input_path = task.directory / f"{submission.stem}.pdf"
    configuration = task.directory / "model.toml"
    output = task.directory / "output"
    try:
        with input_path.open("xb") as stream:
            stream.write(submission.content)
        with configuration.open("x", encoding="utf-8") as stream:
            stream.write(_configuration(submission))
        configuration.chmod(0o600)
        output.mkdir()
        argv = [
            str(root / "pdf2zh.exe"),
            str(input_path),
            "--openai",
            "--config-file",
            str(configuration),
            "--lang-in",
            "en",
            "--lang-out",
            "zh-CN",
            "--output",
            str(output),
            "--ignore-cache",
            "--qps",
            "1",
            "--pool-max-workers",
            "1",
            "--no-auto-extract-glossary",
            "--watermark-output-mode",
            "no_watermark",
            "--disable-config-auto-save",
        ]
        for kind in ("mono", "dual"):
            if kind not in submission.kinds:
                argv.append(f"--no-{kind}")
        environment = _cli_environment(root, task.directory, cache_dir)
        task.process = _spawn_cli(argv, task.directory, environment)
        if await asyncio.to_thread(task.process.wait) != 0:
            raise ValueError("translator failed")
        filenames = []
        for kind in submission.kinds:
            original = output / f"{submission.stem}.no_watermark.zh-CN.{kind}.pdf"
            await asyncio.to_thread(_read_pdf, original)
            suffix = "LR_dual" if kind == "dual" else kind
            name = f"{submission.stem}.no_watermark.zh-CN.{suffix}.pdf"
            target = output / name
            if original != target:
                if target.exists():
                    raise ValueError("unexpected output collision")
                original.rename(target)
            filenames.append(name)
        task.filenames = filenames
        task.status = "success"
    except asyncio.CancelledError:
        task.status = "failed"
        raise
    except Exception:
        # Upstream exceptions can contain model text or tickets. Publish only a
        # terminal failed state; never forward its command, logs, or traceback.
        task.status = "failed"
    finally:
        if task.process is not None:
            await _stop_cli(task.process)
        for path in (input_path, configuration):
            with contextlib.suppress(OSError):
                path.unlink(missing_ok=True)
        await asyncio.to_thread(shutil.rmtree, task.directory / "tmp", True)


def create_bundled_app(runtime_root: Path, work_dir: Path, token: str) -> FastAPI:
    """Create the private Bridge-compatible service inside an owned runtime."""
    root = validate_bundled_root(runtime_root)
    try:
        work_dir = _local_directory(work_dir)
        cache_dir = _local_directory(
            Path(os.environ.get("RGS_TRANSLATION_CACHE", str(work_dir.parent / "runtime-cache"))),
            create=True,
        )
        if len(_text(token, limit=256)) < 16:
            raise ValueError("short token")
    except (ValueError, OSError, RuntimeError):
        raise KnowledgeError(
            "TRANSLATION_RUNTIME_PATH_INVALID", "翻译任务目录或临时凭据无效"
        ) from None
    tasks: dict[str, _Task] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            pending = [task.worker for task in tasks.values() if task.worker is not None]
            for worker in pending:
                if not worker.done():
                    worker.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def authenticate(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if "origin" in request.headers:
            return JSONResponse({"detail": "Browser origins are not accepted"}, status_code=403)
        authorization = request.headers.get("authorization", "")
        if not hmac.compare_digest(authorization.encode(), ("Bearer " + token).encode()):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": BUNDLED_SERVICE_VERSION}

    @app.get("/api/tasks")
    async def active_tasks() -> dict[str, Any]:
        return {"status": "success", "tasks": [task.public() for task in tasks.values()]}

    @app.get("/api/history")
    async def history() -> dict[str, Any]:
        return {
            "status": "success",
            "history": [task.public() for task in tasks.values() if task.status != "running"],
        }

    @app.post("/translate")
    async def translate(request: Request) -> dict[str, str]:
        body = await _body(request)
        try:
            submission = await asyncio.to_thread(_submission, body)
        except (ValueError, TypeError, OverflowError, UnicodeError):
            raise HTTPException(400, "Invalid translation request") from None
        task_id = submission.stem[3:]
        if task_id in tasks or any(task.status == "running" for task in tasks.values()):
            raise HTTPException(409, "Translation task already exists or is busy")
        if len(tasks) >= 16:
            raise HTTPException(409, "This task-scoped service has reached its task limit")
        directory = work_dir / task_id
        try:
            directory.mkdir(exist_ok=False)
        except OSError:
            raise HTTPException(409, "Translation task directory is unavailable") from None
        task = _Task(task_id, directory)
        tasks[task_id] = task
        task.worker = asyncio.create_task(_run(root, cache_dir, task, submission))
        return {"status": "accepted", "taskId": task_id}

    @app.get("/translatedFile/{filename}")
    async def translated_file(filename: str) -> Response:
        for task in tasks.values():
            if task.status == "success" and filename in task.filenames:
                try:
                    content = await asyncio.to_thread(
                        _read_pdf, task.directory / "output" / filename
                    )
                except (OSError, ValueError):
                    raise HTTPException(404, "Translated PDF is unavailable") from None
                return Response(content, media_type="application/pdf")
        raise HTTPException(404, "Translated PDF is unavailable")

    return app
