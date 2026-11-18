"""Local formula candidates and source-faithful previews.

The current Lite parser intentionally does not guess LaTeX from flattened PDF
text.  This module exposes a bounded, read-only bridge for the next step:
detect likely display-math regions from PDF geometry and render the original
region for comparison.  ``latex`` remains ``None`` until an explicitly
configured formula recognizer is added; a renderable string is never treated
as proof that recognition is correct.
"""

from __future__ import annotations

import base64
import hashlib
import math
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from fastapi import FastAPI, Query
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError, StrictModel, text_hash
from researchgraph.document_structure import current_structure
from researchgraph.models import AttachmentRevision, PaperSource
from researchgraph.source_files import MAX_BYTES
from researchgraph.storage import read_session

FormulaStatus = Literal[
    "source_only",
    "latex_unavailable",
    "recognized",
    "needs_review",
    "failed",
]
FormulaConfidence = Literal["suspected", "high"]

# This is an application-level identity for persisted recognition metadata. It
# is deliberately separate from the PDF parser version: changing the local
# OCR implementation invalidates its output without rewriting the source
# structure or the immutable PDF/chunk records.
FORMULA_RECOGNITION_VERSION = "formula-recognition-1"


class FormulaCandidate(StrictModel):
    id: str
    revision_id: str
    page: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    source_text: str
    source_text_hash: str
    confidence: FormulaConfidence
    status: FormulaStatus = "latex_unavailable"
    latex: str | None = None
    recognizer: str | None = None
    recognizer_version: str | None = None
    recognizer_config_hash: str | None = None
    note: str


class FormulaList(StrictModel):
    revision_id: str
    source_sha256: str
    items: list[FormulaCandidate]
    warnings: list[str] = Field(default_factory=list)


class FormulaRecognitionRequest(StrictModel):
    """Bounded local recognition request.

    Recognition is explicit and revision-scoped.  The route never invokes a
    model Provider; an optional local image-to-LaTeX adapter is injected by
    the application (and is absent in the default Lite build).
    """

    formula_ids: list[str] | None = Field(default=None, max_length=128)
    force: bool = False


class FormulaRecognitionItem(StrictModel):
    formula_id: str
    revision_id: str
    page: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    source_text: str
    source_text_hash: str
    status: FormulaStatus
    latex: str | None = None
    recognizer: str | None = None
    error_code: str | None = None
    message: str


class FormulaRecognitionResponse(StrictModel):
    revision_id: str
    source_sha256: str
    status: Literal["completed", "partial", "unavailable", "failed"]
    recognizer: str | None = None
    items: list[FormulaRecognitionItem]
    warnings: list[str] = Field(default_factory=list)
    reading_document_refresh_required: bool = False
    # This route is local-only.  Keeping the counter explicit prevents a UI
    # caller from mistaking OCR work for an LLM request.
    model_calls: int = 0


@dataclass(frozen=True)
class LocalRecognition:
    status: Literal["recognized", "needs_review", "failed"]
    latex: str | None = None
    recognizer: str | None = None
    error_code: str | None = None
    message: str = ""


class FormulaRecognizer(Protocol):
    name: str
    version: str
    config_hash: str

    def __call__(self, image: bytes, candidate: FormulaCandidate) -> LocalRecognition: ...


class FormulaPreview(StrictModel):
    """A JSON-safe, source-faithful crop for desktop bridges.

    The desktop host intentionally does not expose arbitrary binary engine
    responses.  Returning a bounded base64 PNG keeps the preview tied to the
    already validated revision and lets the UI show the original PDF region
    while a formula recognizer is still unavailable.
    """

    formula_id: str
    revision_id: str
    page: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    mime_type: Literal["image/png"] = "image/png"
    data_base64: str
    source_text_hash: str


_MATH_CHARS = frozenset(
    "=±×÷∑∏∫√∞∂∇≤≥≠≈∈∉⊂⊆∪∩→←↔⇒⇔∀∃αβγδεζηθικλμνξοπρστυφχψω"
)
_MATH_LATIN = re.compile(r"^[A-Za-z](?:[A-Za-z0-9_]|\s)*$")
_EQUATION_NUMBER = re.compile(r"^\(?\s*\d{1,3}[a-z]?\s*\)?$")
_MATH_WORD = re.compile(
    r"\b(?:argmax|argmin|relu|softmax|sigmoid|exp|log|ln|sin|cos|tan|sum|prod|lim|sqrt)\b",
    re.I,
)


def _normalize(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())


def formula_candidate_id(
    revision_id: str,
    page_index: int,
    bbox: list[float],
    source_text: str,
) -> str:
    """Return the stable identifier shared by structure, projection and API."""

    identity = f"{revision_id}:{page_index}:{bbox}:{text_hash(_normalize(source_text))}"
    return f"formula-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}"


def _math_score(text: str, spans: list[dict[str, Any]]) -> tuple[float, int]:
    compact = _normalize(text)
    symbol_count = sum(character in _MATH_CHARS for character in compact)
    symbol_count += sum(character in "^_{}()[]/" for character in compact)
    # PDF producers frequently encode Greek glyphs as private-use characters;
    # span metadata still gives a useful signal when a block is short and
    # centered, so count non-letter symbols and italic spans conservatively.
    symbol_count += sum(
        not character.isalnum() and not character.isspace() for character in compact
    )
    italic_chars = sum(
        len(str(span.get("text", "")))
        for span in spans
        if int(span.get("flags", 0)) & 2
    )
    return (
        symbol_count / max(1, len(compact))
        + min(0.35, italic_chars / max(1, len(compact))),
        symbol_count,
    )


def _candidate_blocks(page: Any) -> list[dict[str, Any]]:
    # The annotations are deliberately kept local to this function because
    # PyMuPDF's rawdict types vary between pinned minor versions.
    raw = page.get_text("dict", sort=True)
    result: list[dict[str, Any]] = []
    page_rect = page.rect
    page_width = float(page_rect.width)
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines = [line for line in block.get("lines", []) if line.get("spans")]
        spans = [span for line in lines for span in line.get("spans", [])]
        text = "\n".join(str(span.get("text", "")) for span in spans).strip()
        normalized = _normalize(text)
        if not normalized or len(normalized) > 420 or len(normalized.split()) > 55:
            continue
        bbox = [float(value) for value in block.get("bbox", [])]
        if len(bbox) != 4:
            continue
        width = bbox[2] - bbox[0]
        center_offset = abs((bbox[0] + bbox[2]) / 2 - page_width / 2) / max(1.0, page_width)
        score, symbols = _math_score(text, spans)
        lines_count = len(lines)
        has_operator = any(char in _MATH_CHARS for char in normalized) or "=" in normalized
        last_span = lines[-1].get("spans", [{}])[-1] if lines else {}
        has_equation_number = bool(
            lines and _EQUATION_NUMBER.fullmatch(_normalize(str(last_span.get("text", ""))))
        )
        # Prose can contain an isolated equality such as “a = b”. Require a
        # second mathematical signal before materializing an equation card.
        # This intentionally prefers a false negative over labeling prose as
        # a formula.
        strong_math_signal = bool(
            _MATH_WORD.search(normalized)
            or re.search(
                r"[±×÷∑∏∫√∞∂∇≤≥≠≈∈∉⊂⊆∪∩→←↔⇒⇔∀∃α-ω^_{}\[\]/]",
                normalized,
            )
            or has_equation_number
        )
        if "=" in normalized and not strong_math_signal:
            continue
        has_fraction_shape = "/" in normalized or any(
            int(span.get("flags", 0)) & 2 for span in spans
        )
        # A candidate is intentionally conservative: it must look like a
        # short display block, have an operator/symbol, and not be ordinary
        # prose.  Inline formulae remain in their paragraph until an explicit
        # recognizer can return a precise range.
        if not has_operator or symbols < 2:
            continue
        if len(normalized.split()) > 32 and score < 0.18:
            continue
        if center_offset > 0.34 and not has_equation_number:
            continue
        if width > page_width * 0.92 and lines_count <= 1 and not has_fraction_shape:
            continue
        if _MATH_LATIN.fullmatch(normalized) and not has_fraction_shape:
            continue
        confidence: FormulaConfidence = (
            "high" if has_equation_number or score >= 0.26 else "suspected"
        )
        result.append(
            {
                "bbox": bbox,
                "text": text,
                "confidence": confidence,
            }
        )
    return result


def detect_formula_candidates(document: Any, revision_id: str) -> list[FormulaCandidate]:
    candidates: list[FormulaCandidate] = []
    for page_index in range(len(document)):
        page = document[page_index]
        for item in _candidate_blocks(page):
            source_text = str(item["text"])
            bbox = [round(float(value), 3) for value in item["bbox"]]
            candidates.append(
                FormulaCandidate(
                    id=formula_candidate_id(revision_id, page_index, bbox, source_text),
                    revision_id=revision_id,
                    page=page_index + 1,
                    bbox=bbox,
                    source_text=source_text,
                    source_text_hash=text_hash(source_text),
                    confidence=item["confidence"],
                    note="仅依据 PDF 版面推断；请对照原图。当前未生成 LaTeX。",
                )
            )
    return candidates


def stored_formula_candidate(
    record: dict[str, Any], revision: AttachmentRevision
) -> FormulaCandidate | None:
    """Convert one persisted structure record into the public candidate DTO.

    Formula IDs are derived again from the current revision, page, bbox and
    source text.  This makes old ``unbound`` import records safe to read while
    dropping any recognition metadata whose source identity no longer agrees.
    """

    try:
        page_index = int(record["page_index"])
        bbox = [round(float(value), 3) for value in record["bbox"]]
        source_text = str(record.get("text", ""))
    except (KeyError, TypeError, ValueError):
        return None
    if (
        page_index < 0
        or page_index >= revision.page_count
        or len(bbox) != 4
        or not all(math.isfinite(value) for value in bbox)
        or bbox[2] <= bbox[0]
        or bbox[3] <= bbox[1]
        or not source_text
    ):
        return None
    formula_id = formula_candidate_id(revision.id, page_index, bbox, source_text)
    source_hash = text_hash(source_text)
    # Recognition fields are valid only when they were produced for exactly
    # this source hash and PDF revision.  A stale result remains in the raw
    # parse history but is not exposed as a renderable LaTeX candidate.
    recognized_revision = record.get("recognition_source_sha256")
    recognized_text_hash = record.get("recognition_source_text_hash")
    recognition_valid = (
        recognized_revision == revision.sha256
        and recognized_text_hash == source_hash
        and record.get("recognition_revision_id") == revision.id
        and record.get("recognition_page_index") == page_index
        and record.get("recognition_bbox") == bbox
        and record.get("formula_id") == formula_id
        and bool(record.get("recognizer_version"))
        and bool(record.get("recognizer_config_hash"))
    )
    status = str(record.get("status", "latex_unavailable"))
    if status not in {"source_only", "latex_unavailable", "recognized", "needs_review", "failed"}:
        status = "latex_unavailable"
    latex = record.get("latex") if recognition_valid else None
    if not _valid_latex(latex) or status != "recognized":
        latex = None
        if status == "recognized":
            status = "needs_review"
    confidence = record.get("confidence", "suspected")
    if confidence not in {"suspected", "high"}:
        confidence = "suspected"
    return FormulaCandidate(
        id=formula_id,
        revision_id=revision.id,
        page=page_index + 1,
        bbox=bbox,
        source_text=source_text,
        source_text_hash=source_hash,
        confidence=cast(FormulaConfidence, confidence),
        status=cast(FormulaStatus, status),
        latex=latex,
        recognizer=record.get("recognizer") if recognition_valid else None,
        recognizer_version=(record.get("recognizer_version") or FORMULA_RECOGNITION_VERSION)
        if recognition_valid and status == "recognized"
        else None,
        recognizer_config_hash=record.get("recognizer_config_hash") if recognition_valid else None,
        note=(
            "本地识别结果已绑定当前 PDF、原文哈希和区域；仍请对照原图。"
            if status == "recognized"
            else "仅依据 PDF 版面推断；请使用原图核对，当前没有可用 LaTeX。"
        ),
    )


def persisted_formula_candidates(
    session: Session, revision: AttachmentRevision
) -> list[FormulaCandidate] | None:
    """Read formula candidates from the current immutable structure artifact.

    ``None`` means there is no compatible persisted structure and callers may
    fall back to a fresh, read-only PDF scan.  The structure row itself is
    never mutated by a GET request.
    """

    artifact = current_structure(session, revision.id)
    if artifact is None or artifact.source_sha256 != revision.sha256:
        return None
    raw = artifact.data.get("formulas") if isinstance(artifact.data, dict) else None
    if not isinstance(raw, list):
        return None
    candidates = [
        candidate
        for item in raw
        if isinstance(item, dict)
        for candidate in [stored_formula_candidate(item, revision)]
        if candidate is not None
    ]
    return candidates


def persist_formula_recognition(
    session: Session,
    revision_id: str,
    formula_id: str,
    *,
    latex: str | None,
    status: FormulaStatus,
    confidence: FormulaConfidence,
    recognizer: str,
    recognizer_version: str = FORMULA_RECOGNITION_VERSION,
    recognizer_config_hash: str | None = None,
) -> dict[str, Any]:
    """Persist one local OCR result inside the versioned structure JSON.

    The immutable source text, page, bbox and parse artifact identity remain
    untouched.  Recognition metadata is replaced atomically on the JSON
    column, and every value is tied to the current PDF SHA and source hash.
    This avoids a migration while keeping results available after restart.
    """

    revision = session.get(AttachmentRevision, revision_id)
    if revision is None:
        raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
    artifact = current_structure(session, revision_id)
    if artifact is None or artifact.source_sha256 != revision.sha256:
        raise KnowledgeError("FORMULA_STRUCTURE_UNAVAILABLE", "当前文献没有可用的结构解析")
    data = deepcopy(artifact.data)
    formulas = data.get("formulas") if isinstance(data, dict) else None
    if not isinstance(formulas, list):
        raise KnowledgeError("FORMULA_NOT_FOUND", "当前结构中没有公式候选")
    selected: dict[str, Any] | None = None
    selected_id: str | None = None
    for item in formulas:
        if not isinstance(item, dict):
            continue
        try:
            page_index = int(item["page_index"])
            bbox = [round(float(value), 3) for value in item["bbox"]]
            source_text = str(item.get("text", ""))
        except (KeyError, TypeError, ValueError):
            continue
        candidate_id = formula_candidate_id(revision.id, page_index, bbox, source_text)
        if formula_id in {candidate_id, item.get("formula_id"), item.get("id")}:
            selected, selected_id = item, candidate_id
            break
    if selected is None or selected_id is None:
        raise KnowledgeError("FORMULA_NOT_FOUND", "公式候选不存在或已失效")
    source_text = str(selected.get("text", ""))
    if not source_text:
        raise KnowledgeError("FORMULA_SOURCE_INVALID", "公式原文为空，无法保存识别结果")
    source_text_hash = text_hash(source_text)
    normalized_status = status
    normalized_latex = latex.strip() if isinstance(latex, str) and latex.strip() else None
    if normalized_status == "recognized" and not _valid_latex(normalized_latex):
        raise KnowledgeError("FORMULA_RECOGNITION_INVALID", "recognized 状态必须包含有效 LaTeX")
    if normalized_status != "recognized":
        normalized_latex = None
    selected.update(
        {
            "id": selected_id,
            "formula_id": selected_id,
            "source_text_hash": source_text_hash,
            "status": normalized_status,
            "latex": normalized_latex,
            "confidence": confidence,
            "recognizer": recognizer,
            "recognizer_version": recognizer_version,
            "recognizer_config_hash": recognizer_config_hash,
            "recognition_source_sha256": revision.sha256,
            "recognition_source_text_hash": source_text_hash,
            "recognition_revision_id": revision.id,
            "recognition_page_index": int(selected["page_index"]),
            "recognition_bbox": [round(float(value), 3) for value in selected["bbox"]],
        }
    )
    artifact.data = data
    session.flush()
    return deepcopy(selected)


def _registered_pdf(session: Session, revision: AttachmentRevision, data_dir: Path | None) -> bytes:
    sources = list(
        session.scalars(
            select(PaperSource)
            .where(
                PaperSource.paper_id == revision.paper_id,
                PaperSource.revision_id == revision.id,
            )
            .order_by(PaperSource.id)
        )
    )
    paths: list[Path] = [Path(source.path) for source in sources]
    for source in sources:
        if source.managed_path and data_dir is not None:
            managed = Path(source.managed_path)
            if managed.resolve().is_relative_to(data_dir.resolve()):
                paths.append(managed)
    for path in dict.fromkeys(paths):
        if not path.is_absolute() or path.suffix.lower() != ".pdf":
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if len(content) <= MAX_BYTES and hashlib.sha256(content).hexdigest() == revision.sha256:
            return content
    raise KnowledgeError("FORMULA_SOURCE_UNAVAILABLE", "登记的原始 PDF 不可用或字节已变化")


def _load_candidates(
    engine: Engine, revision_id: str, data_dir: Path | None
) -> tuple[str, bytes, list[FormulaCandidate]]:
    import pymupdf

    with read_session(engine) as session:
        revision = session.get(AttachmentRevision, revision_id)
        if revision is None:
            raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
        content = _registered_pdf(session, revision, data_dir)
        candidates = persisted_formula_candidates(session, revision)
        if candidates is None:
            with pymupdf.open(stream=content, filetype="pdf") as document:
                candidates = detect_formula_candidates(document, revision.id)
        return revision.sha256, content, candidates


def _render_formula_crop(content: bytes, selected: FormulaCandidate) -> bytes:
    """Render one bounded crop from the validated source PDF.

    Keep the crop logic in one place so the binary compatibility route and the
    JSON desktop route enforce identical page, margin, scale and area limits.
    """

    import pymupdf

    with pymupdf.open(stream=content, filetype="pdf") as document:
        page = document[selected.page - 1]
        page_rect = page.rect
        margin = 8.0
        clip = pymupdf.Rect(
            max(0.0, selected.bbox[0] - margin),
            max(0.0, selected.bbox[1] - margin),
            min(float(page_rect.width), selected.bbox[2] + margin),
            min(float(page_rect.height), selected.bbox[3] + margin),
        )
        if clip.width <= 0 or clip.height <= 0 or clip.width * clip.height > 2_000_000:
            raise KnowledgeError("FORMULA_REGION_INVALID", "公式区域超出安全预览范围")
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(2.0, 2.0), clip=clip, alpha=False
        )
        return cast(bytes, pixmap.tobytes("png"))


def _valid_latex(value: str | None) -> bool:
    """Apply a conservative syntax gate before displaying OCR output.

    This is intentionally not a full TeX parser.  It rejects empty/control
    output and unbalanced braces, while leaving semantic validation to the
    renderer and the original PDF crop.  A rejected string is never persisted
    as ``recognized``.
    """

    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or len(text) > 12_000:
        return False
    if any(ord(char) < 9 or (13 <= ord(char) < 32) for char in text):
        return False
    depth = 0
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _unavailable_recognizer() -> None:
    """Marker used when no local OCR package/adapter is configured.

    The function is kept separate from the route so a future packaged Pix2Tex
    adapter can be selected without changing the API contract or introducing
    an accidental network fallback.
    """

    return None


def _recognition_item(
    candidate: FormulaCandidate,
    result: LocalRecognition,
) -> FormulaRecognitionItem:
    return FormulaRecognitionItem(
        formula_id=candidate.id,
        revision_id=candidate.revision_id,
        page=candidate.page,
        bbox=candidate.bbox,
        source_text=candidate.source_text,
        source_text_hash=candidate.source_text_hash,
        status=result.status,
        latex=result.latex if result.status == "recognized" else None,
        recognizer=result.recognizer,
        error_code=result.error_code,
        message=result.message,
    )


def recognize_revision_formulas(
    engine: Engine,
    revision_id: str,
    body: FormulaRecognitionRequest,
    data_dir: Path | None,
    recognizer: FormulaRecognizer | None,
    *,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> FormulaRecognitionResponse:
    """Run the configured local OCR adapter and return source-bound results.

    The default application has no recognizer, so this endpoint returns a
    deterministic ``unavailable`` response and does not create a model
    usage record.  When a local adapter is supplied, only the selected
    formula crops are processed; valid results are persisted into the
    versioned structure JSON and the caller is told to reload the reading
    projection.
    """

    def check_cancelled() -> None:
        if cancelled is not None and cancelled():
            raise KnowledgeError("FORMULA_RECOGNITION_CANCELLED", "公式识别已取消")

    check_cancelled()
    source_hash, content, candidates = _load_candidates(engine, revision_id, data_dir)
    candidate_by_id = {item.id: item for item in candidates}
    selected_ids = body.formula_ids
    if selected_ids is None:
        selected = candidates
    else:
        unknown = [item for item in selected_ids if item not in candidate_by_id]
        if unknown:
            raise KnowledgeError("FORMULA_NOT_FOUND", "公式候选不存在或已失效")
        selected = [candidate_by_id[item] for item in dict.fromkeys(selected_ids)]

    # Reuse a result only for this exact runtime/model configuration. A model
    # replacement must not silently keep an earlier model's cached output.
    if not body.force:
        selected = [
            item
            for item in selected
            if item.status != "recognized"
            or recognizer is None
            or item.recognizer != recognizer.name
            or item.recognizer_version != getattr(
                recognizer, "version", FORMULA_RECOGNITION_VERSION
            )
            or item.recognizer_config_hash != getattr(recognizer, "config_hash", None)
        ]
    if not selected:
        return FormulaRecognitionResponse(
            revision_id=revision_id,
            source_sha256=source_hash,
            status="completed",
            recognizer=getattr(recognizer, "name", None),
            items=[],
            warnings=[
                "所选公式已有当前识别器的有效结果，无需重复识别。"
                if candidates else "当前文献未发现可识别的独立公式候选。"
            ],
            model_calls=0,
        )

    if recognizer is None:
        items = [
            _recognition_item(
                candidate,
                LocalRecognition(
                    status="failed",
                    recognizer=None,
                    error_code="FORMULA_RECOGNIZER_UNAVAILABLE",
                    message=(
                        "当前安装包未配置本地公式识别器；已保留原图和原始文本，"
                        "不会根据损坏的 PDF 线性文本猜补 LaTeX。"
                    ),
                ),
            )
            for candidate in selected
        ]
        return FormulaRecognitionResponse(
            revision_id=revision_id,
            source_sha256=source_hash,
            status="unavailable",
            items=items,
            warnings=[
                "公式识别器不可用；请使用原图核对上下标、分数、矩阵和积分上下限。",
                "本地识别未调用 LLM，也未产生 Token 或费用。",
            ],
            model_calls=0,
        )

    results: list[tuple[FormulaCandidate, LocalRecognition]] = []
    if progress is not None:
        progress(0, len(selected))
    for candidate in selected:
        check_cancelled()
        try:
            result = recognizer(_render_formula_crop(content, candidate), candidate)
            if result.status == "recognized" and not _valid_latex(result.latex):
                result = LocalRecognition(
                    status="needs_review",
                    recognizer=result.recognizer or recognizer.name,
                    error_code="FORMULA_LATEX_INVALID",
                    message="识别器返回的 LaTeX 未通过安全语法检查，已回退原图。",
                )
        except Exception as error:  # pragma: no cover - defensive adapter boundary
            result = LocalRecognition(
                status="failed",
                recognizer=recognizer.name,
                error_code="FORMULA_RECOGNITION_FAILED",
                message=f"本地公式识别失败：{type(error).__name__}",
            )
        results.append((candidate, result))
        if progress is not None:
            progress(len(results), len(selected))

    persisted = False
    check_cancelled()
    # Persist only adapter results.  The no-adapter branch above is
    # intentionally read-only so installing/repairing an OCR package does
    # not alter the source artifact merely by probing the endpoint.
    with Session(engine) as session, session.begin():
        revision = session.get(AttachmentRevision, revision_id)
        if revision is None:
            raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
        if revision.sha256 != source_hash:
            raise KnowledgeError("SOURCE_CHANGED", "识别期间文献版本已变化，请重新识别")
        current = persisted_formula_candidates(session, revision)
        current_by_id = {item.id: item for item in current or []}
        if any(
            candidate.id not in current_by_id
            or current_by_id[candidate.id].source_text_hash != candidate.source_text_hash
            or current_by_id[candidate.id].bbox != candidate.bbox
            or current_by_id[candidate.id].page != candidate.page
            for candidate, _result in results
        ):
            raise KnowledgeError("SOURCE_CHANGED", "识别期间公式区域已变化，请重新整理后识别")
        check_cancelled()
        for candidate, result in results:
            persist_formula_recognition(
                session,
                revision_id,
                candidate.id,
                latex=result.latex,
                status=(
                    result.status
                    if result.status in {"recognized", "needs_review", "failed"}
                    else "failed"
                ),
                confidence=candidate.confidence,
                recognizer=result.recognizer or recognizer.name,
                recognizer_version=getattr(
                    recognizer, "version", FORMULA_RECOGNITION_VERSION
                ),
                recognizer_config_hash=getattr(recognizer, "config_hash", None),
            )
            persisted = True

        # Rebuild the disposable local reading projection in the same
        # transaction.  This does not parse the PDF or invoke a Provider;
        # it only re-assembles the already persisted source blocks so the
        # next reading-document GET can show the recognized LaTeX.
        if persisted:
            from researchgraph.reading_projection import (
                prepare_reading_document,
                publish_reading_document,
            )

            revision_for_view = session.get(AttachmentRevision, revision_id)
            if revision_for_view is not None and inspect(session.connection()).has_table(
                "lite_reading_documents"
            ):
                prepared = prepare_reading_document(
                    session,
                    revision_for_view.paper_id,
                    revision_id,
                    refresh=False,
                )
                if not publish_reading_document(session, prepared):
                    raise KnowledgeError("SOURCE_CHANGED", "阅读存档已变化，请重新读取后识别")

    response_items = [_recognition_item(candidate, result) for candidate, result in results]
    statuses = {item.status for item in response_items}
    response_status: Literal["completed", "partial", "unavailable", "failed"]
    if statuses == {"recognized"}:
        response_status = "completed"
    elif "recognized" in statuses or "needs_review" in statuses:
        response_status = "partial"
    else:
        response_status = "failed"
    return FormulaRecognitionResponse(
        revision_id=revision_id,
        source_sha256=source_hash,
        status=response_status,
        recognizer=recognizer.name,
        items=response_items,
        warnings=[
            "识别结果已绑定 PDF SHA、revision、页码、bbox 和原始文本哈希。",
            "请重新读取论文精读文档以加载最新的 LaTeX；原图和原始文本仍保留。",
        ],
        # The desktop caller still reloads its active query even when the
        # backend could rebuild the archive in the same transaction.
        reading_document_refresh_required=persisted,
        model_calls=0,
    )


def register_formula_api(
    app: FastAPI,
    get_engine: Callable[[], Engine],
    data_dir: Path | None,
    recognizer: FormulaRecognizer | None = None,
) -> None:
    @app.get("/api/v1/revisions/{revision_id}/formulas", response_model=FormulaList)
    def formulas(
        revision_id: str,
        page: int | None = Query(None, ge=1, le=300),
        limit: int = Query(64, ge=1, le=128),
    ) -> FormulaList:
        source_hash, _content, candidates = _load_candidates(get_engine(), revision_id, data_dir)
        if page is not None:
            candidates = [item for item in candidates if item.page == page]
        return FormulaList(
            revision_id=revision_id,
            source_sha256=source_hash,
            items=candidates[:limit],
            warnings=[
                (
                    "已显示本地公式识别结果；仍请使用原图核对上下标、分数、矩阵和积分上下限。"
                    if any(item.status == "recognized" for item in candidates)
                    else "公式候选仅由 PDF 版面启发式定位；LaTeX 识别尚未可靠确认。"
                ),
                "请使用原图核对上下标、分数、矩阵和积分上下限。",
            ],
        )

    @app.post(
        "/api/v1/revisions/{revision_id}/formulas/recognize",
        response_model=FormulaRecognitionResponse,
    )
    def recognize_formulas(
        revision_id: str, body: FormulaRecognitionRequest
    ) -> FormulaRecognitionResponse:
        return recognize_revision_formulas(
            get_engine(), revision_id, body, data_dir, recognizer
        )

    @app.get(
        "/api/v1/revisions/{revision_id}/formulas/{formula_id}/preview",
        response_model=FormulaPreview,
    )
    def formula_preview(revision_id: str, formula_id: str) -> FormulaPreview:
        _source_hash, content, candidates = _load_candidates(
            get_engine(), revision_id, data_dir
        )
        selected = next((item for item in candidates if item.id == formula_id), None)
        if selected is None:
            raise KnowledgeError("FORMULA_NOT_FOUND", "公式候选不存在或已失效")
        image = _render_formula_crop(content, selected)
        return FormulaPreview(
            formula_id=selected.id,
            revision_id=selected.revision_id,
            page=selected.page,
            bbox=selected.bbox,
            data_base64=base64.b64encode(image).decode("ascii"),
            source_text_hash=selected.source_text_hash,
        )

    @app.get("/api/v1/revisions/{revision_id}/formulas/{formula_id}/image")
    def formula_image(revision_id: str, formula_id: str) -> Response:
        _source_hash, content, candidates = _load_candidates(
            get_engine(), revision_id, data_dir
        )
        selected = next((item for item in candidates if item.id == formula_id), None)
        if selected is None:
            raise KnowledgeError("FORMULA_NOT_FOUND", "公式候选不存在或已失效")
        return Response(content=_render_formula_crop(content, selected), media_type="image/png")
