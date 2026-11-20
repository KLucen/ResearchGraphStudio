"""PDF metadata and page slicing for resumable batches; no text extraction."""

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pymupdf

from researchgraph import document_transport
from researchgraph.document_transport import (
    DocumentRenderCancelled,
    DocumentRenderError,
    read_pdf_bytes,
)

MAX_BATCH_DOCUMENT_PAGES = 2048


def _stat_version(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
        "device": stat.st_dev,
        "inode": stat.st_ino,
    }


def assert_source_version(path: Path, version: dict[str, Any]) -> None:
    """Refuse changed source bytes metadata without hashing or reading source text."""
    try:
        current = _stat_version(path)
    except OSError:
        raise DocumentRenderError("源 PDF 已不可用；请重新创建解析任务") from None
    if any(
        type(version.get(key)) is not int or version[key] != value for key, value in current.items()
    ):
        raise DocumentRenderError("源 PDF 版本已变化；已停止续接，请重新创建解析任务")


def slice_pdf(raw: bytes, start: int, end: int) -> bytes:
    """Copy the inclusive one-based page range without extracting text."""
    try:
        with pymupdf.open(stream=raw, filetype="pdf") as document, pymupdf.open() as subset:
            if document.needs_pass:
                raise DocumentRenderError("PDF 已加密，无法分批解析")
            if (
                type(start) is not int
                or type(end) is not int
                or not 1 <= start <= end <= len(document)
            ):
                raise DocumentRenderError("PDF 批次页码范围无效")
            subset.insert_pdf(document, from_page=start - 1, to_page=end - 1)
            return bytes(subset.tobytes(garbage=3, deflate=True))
    except DocumentRenderError:
        raise
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        raise DocumentRenderError("PDF 无法分割，请检查文件是否损坏") from None


def prepare_document(
    path: Path,
    pages_per_batch: int,
    provider: Any,
    *,
    should_continue: Callable[[], bool] | None = None,
) -> tuple[bytes, dict[str, Any], list[dict[str, int]]]:
    """Plan ordered, nonoverlapping core pages with one shared preceding page.

    pages_per_batch bounds pages sent including overlap. Known model limits use
    conservative per-page estimates (not a claim about model quality). Pixel and
    encoded-image bounds are measured before any model request.
    """
    if type(pages_per_batch) is not int or not 2 <= pages_per_batch <= 32:
        raise DocumentRenderError("每批发送页数必须为2至32页（包含共享页）")

    def check_continue() -> None:
        if should_continue is not None and not should_continue():
            raise DocumentRenderCancelled

    check_continue()
    try:
        version: dict[str, Any] = _stat_version(path)
        raw = read_pdf_bytes(path)
        check_continue()
        assert_source_version(path, version)
        with pymupdf.open(stream=raw, filetype="pdf") as document:
            if document.needs_pass:
                raise DocumentRenderError("PDF 已加密，无法分批解析")
            count = len(document)
            if not 1 <= count <= MAX_BATCH_DOCUMENT_PAGES:
                raise DocumentRenderError("PDF 页数超过批次解析范围（1至2048页）；未发送")
            version["page_count"] = count
            capabilities = getattr(provider, "capabilities", None)
            transport = getattr(capabilities, "document_transport", "chat_file")
            output_limit = getattr(capabilities, "max_output_tokens", None)
            context_limit = getattr(capabilities, "context_window", None)
            limit = pages_per_batch
            core_limit = pages_per_batch
            if type(output_limit) is int:
                if output_limit < 2048:
                    raise DocumentRenderError(
                        "模型已知输出容量不足以容纳单页结构化转录；未发送，请选择更大输出容量"
                    )
                limit = min(limit, max(2, output_limit // 2048))
                core_limit = min(core_limit, max(1, output_limit // 2048))
            if type(context_limit) is int:
                # Reserve instructions/schema and output before estimating pages.
                output_reserve = min(output_limit or 4096, context_limit // 2)
                available = context_limit - output_reserve - 2048
                if available < 4096:
                    raise DocumentRenderError("模型已知上下文不足以容纳核心页和共享页；未发送")
                limit = min(limit, max(2, available // 2048))
            page_pixels: list[int] = []
            image_sizes: list[int] = []
            for page in document:
                check_continue()
                width = math.ceil(page.rect.width * document_transport.RENDER_DPI / 72)
                height = math.ceil(page.rect.height * document_transport.RENDER_DPI / 72)
                pixels = width * height
                if transport == "chat_images":
                    if width <= 0 or height <= 0 or pixels > document_transport.MAX_PAGE_PIXELS:
                        raise DocumentRenderError("PDF 单页超过图片输入像素上限；未发送或截页")
                    pixmap = page.get_pixmap(
                        matrix=pymupdf.Matrix(
                            document_transport.RENDER_DPI / 72, document_transport.RENDER_DPI / 72
                        ),
                        colorspace=pymupdf.csRGB,
                        alpha=False,
                    )
                    size = len(pixmap.tobytes("jpeg", jpg_quality=90))
                    check_continue()
                    if size > document_transport.MAX_IMAGE_BYTES:
                        raise DocumentRenderError("PDF 单页超过图片输入字节上限；未发送或截页")
                else:
                    size = 0
                page_pixels.append(pixels)
                image_sizes.append(size)
            ranges: list[dict[str, int]] = []
            core_start = 1
            while core_start <= count:
                check_continue()
                send_start = max(1, core_start - 1)
                core_end = min(count, send_start + limit - 1, core_start + core_limit - 1)
                while core_end >= core_start:
                    check_continue()
                    if transport == "chat_file":
                        if (
                            len(slice_pdf(raw, send_start, core_end))
                            <= document_transport.MAX_PDF_BYTES
                        ):
                            break
                    elif (
                        sum(page_pixels[send_start - 1 : core_end])
                        <= document_transport.MAX_TOTAL_PIXELS
                        and sum(image_sizes[send_start - 1 : core_end])
                        <= document_transport.MAX_IMAGE_BYTES
                    ):
                        break
                    core_end -= 1
                if core_end < core_start:
                    raise DocumentRenderError("PDF 相邻页超过单次输入容量；未发送或丢弃页面")
                ranges.append(
                    {
                        "index": len(ranges),
                        "page_start": core_start,
                        "page_end": core_end,
                        "send_start": send_start,
                        "send_end": core_end,
                    }
                )
                core_start = core_end + 1
            assert_source_version(path, version)
            check_continue()
            return raw, version, ranges
    except DocumentRenderError:
        raise
    except OSError:
        raise DocumentRenderError("无法读取源 PDF；未发送") from None
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        raise DocumentRenderError("PDF 无法分批，请检查文件是否损坏") from None
