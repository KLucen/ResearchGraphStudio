"""Bounded PDF page rendering for explicitly selected model vision input.

This module only rasterizes pages. It never extracts text, formulas or tables.
"""

import base64
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pymupdf

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_DOCUMENT_PAGES = 128
MAX_PAGE_PIXELS = 8_000_000
MAX_TOTAL_PIXELS = 128_000_000
MAX_IMAGE_BYTES = 32 * 1024 * 1024
RENDER_DPI = 144


class DocumentRenderError(ValueError):
    """The complete PDF cannot fit the bounded image transport."""


class DocumentRenderCancelled(Exception):
    """The task ended before all page images were prepared."""


class DocumentRenderDeadline(Exception):
    """The complete document deadline elapsed while rendering pages."""


def read_pdf_bytes(path: Path) -> bytes:
    """Read at most one bounded input, including if the file grows after stat."""
    with path.open("rb") as source:
        raw = source.read(MAX_PDF_BYTES + 1)
    if len(raw) > MAX_PDF_BYTES:
        raise DocumentRenderError("PDF 超过 50 MiB 限制")
    return raw


def render_pdf_images(
    raw: bytes,
    *,
    should_continue: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    page_offset: int = 0,
    document_pages: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Render every page in source order, or fail without sending partial input."""

    if len(raw) > MAX_PDF_BYTES:
        raise DocumentRenderError("PDF 超过 50 MiB 限制")
    parts: list[dict[str, Any]] = []
    total_pixels, image_bytes = 0, 0
    try:
        with pymupdf.open(stream=raw, filetype="pdf") as document:
            if document.needs_pass:
                raise DocumentRenderError("PDF 已加密，请先使用可读取的 PDF 文件")
            page_count = len(document)
            if not page_count:
                raise DocumentRenderError("PDF 没有可读取的页面")
            if page_count > MAX_DOCUMENT_PAGES:
                raise DocumentRenderError(
                    f"PDF 共 {page_count} 页，超过单次图像输入的 {MAX_DOCUMENT_PAGES} 页限制；"
                    "这是软件本次输入上限，未发送或截取部分页面，"
                    "请拆分文件或使用支持 PDF 的文件接口"
                )
            if on_progress:
                on_progress(0, page_count)
            # Check all page dimensions before allocating any large pixmap.
            for page in document:
                if should_continue is not None and not should_continue():
                    raise DocumentRenderCancelled
                rect = page.rect
                width = math.ceil(rect.width * RENDER_DPI / 72)
                height = math.ceil(rect.height * RENDER_DPI / 72)
                pixels = width * height
                if width <= 0 or height <= 0 or pixels > MAX_PAGE_PIXELS:
                    raise DocumentRenderError(
                        "PDF 页面尺寸超过软件本次图像输入上限，无法安全转换；未发送"
                    )
                total_pixels += pixels
                if total_pixels > MAX_TOTAL_PIXELS:
                    raise DocumentRenderError(
                        "PDF 完整页面超过软件本次图像输入容量；未发送或截取部分页面，"
                        "请拆分文件或使用支持 PDF 的文件接口"
                    )
            for index, page in enumerate(document):
                if should_continue is not None and not should_continue():
                    raise DocumentRenderCancelled
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(RENDER_DPI / 72, RENDER_DPI / 72),
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )
                image = pixmap.tobytes("jpeg", jpg_quality=90)
                image_bytes += len(image)
                if image_bytes > MAX_IMAGE_BYTES:
                    raise DocumentRenderError(
                        "PDF 页面图片超过软件本次 32 MiB 容量；未发送或截取部分页面，"
                        "请拆分文件或使用支持 PDF 的文件接口"
                    )
                parts.extend(
                    [
                        {
                            "type": "text",
                            "text": (
                                f"PDF 原始第 {index + 1 + page_offset} 页 / "
                                f"共 {document_pages or page_count} 页"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64,"
                                + base64.b64encode(image).decode("ascii"),
                                "detail": "high",
                            },
                        },
                    ]
                )
                if on_progress:
                    on_progress(index + 1, page_count)
            return parts, {
                "page_count": page_count,
                "rendered_pages": page_count,
                "image_bytes": image_bytes,
                "render_dpi": RENDER_DPI,
            }
    except (DocumentRenderError, DocumentRenderCancelled, DocumentRenderDeadline):
        raise
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        # PyMuPDF exceptions can include source or document data. Return only
        # a stable explanation; no caller should persist the library message.
        raise DocumentRenderError("PDF 页面无法转换为图片，请检查文件是否损坏") from None
