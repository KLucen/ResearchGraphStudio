"""Optional local image-to-LaTeX formula recognition.

The main Lite engine deliberately keeps formula OCR optional.  Importing this
module never downloads weights or calls a model provider.  A Pix2Text MFR
model is used only when the user has explicitly configured a local model
directory through ``RESEARCHGRAPH_FORMULA_OCR`` and
``RESEARCHGRAPH_FORMULA_MODEL_DIR``.  Without that directory the normal
installation continues to expose the source-faithful formula crop and the
``latex_unavailable`` state.
"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from threading import Lock
from typing import Any

from researchgraph.formula_api import (
    FormulaCandidate,
    LocalRecognition,
)


class Pix2TextFormulaRecognizer:
    """Lazy Pix2Text MFR adapter for one already-cropped formula image."""

    name = "pix2text-mfr-1.5-onnx"
    version = "pix2text-mfr-1.5-onnx"

    def __init__(self, model_dir: Path, *, device: str = "cpu") -> None:
        self.model_dir = model_dir
        self.device = device
        self.config_hash = hashlib.sha256(
            f"{self.name}:{self.version}:{model_dir.resolve()}:{device}".encode()
        ).hexdigest()
        self._engine: Any | None = None
        self._lock = Lock()

    def _load(self) -> Any:
        if self._engine is not None:
            return self._engine
        with self._lock:
            if self._engine is not None:
                return self._engine
            if not self.model_dir.is_dir():
                raise RuntimeError("FORMULA_OCR_MODEL_MISSING")
            try:
                from pix2text.latex_ocr import LatexOCR  # type: ignore[import-not-found]
            except Exception as error:  # pragma: no cover - optional dependency boundary
                raise RuntimeError("FORMULA_OCR_DEPENDENCY_MISSING") from error
            try:
                self._engine = LatexOCR(
                    model_name="mfr-1.5",
                    model_backend="onnx",
                    device=self.device,
                    model_dir=str(self.model_dir),
                    # CPU is deterministic and does not require a GPU runtime.
                    more_model_configs={"provider": "CPUExecutionProvider"},
                )
            except Exception as error:  # pragma: no cover - model/runtime boundary
                raise RuntimeError("FORMULA_OCR_MODEL_LOAD_FAILED") from error
            return self._engine

    def __call__(self, image: bytes, candidate: FormulaCandidate) -> LocalRecognition:
        del candidate  # the crop is already bound to the validated candidate
        try:
            from PIL import Image

            engine = self._load()
            with Image.open(io.BytesIO(image)) as source:
                result = engine.recognize(source.convert("RGB"), use_post_process=True)
        except RuntimeError as error:
            code = str(error)
            message = {
                "FORMULA_OCR_MODEL_MISSING": "公式 OCR 模型目录不存在，已保留原图。",
                "FORMULA_OCR_DEPENDENCY_MISSING": "公式 OCR 依赖未安装，已保留原图。",
                "FORMULA_OCR_MODEL_LOAD_FAILED": "公式 OCR 模型加载失败，已保留原图。",
            }.get(code, "公式 OCR 运行失败，已保留原图。")
            return LocalRecognition(
                status="failed",
                recognizer=self.name,
                error_code=code,
                message=message,
            )
        except Exception as error:  # pragma: no cover - defensive runtime boundary
            return LocalRecognition(
                status="failed",
                recognizer=self.name,
                error_code="FORMULA_OCR_FAILED",
                message=f"公式 OCR 运行失败：{type(error).__name__}。已保留原图。",
            )

        if isinstance(result, dict):
            latex = result.get("text")
            score = result.get("score")
        else:
            latex = result
            score = None
        if not isinstance(latex, str) or not latex.strip():
            return LocalRecognition(
                status="failed",
                recognizer=self.name,
                error_code="FORMULA_OCR_EMPTY",
                message="公式 OCR 未返回 LaTeX，已保留原图。",
            )
        # The API applies the final structural LaTeX gate.  A low model score
        # is still useful as a visible review state rather than a silent drop.
        low_confidence = isinstance(score, (int, float)) and float(score) < 0.65
        if low_confidence:
            return LocalRecognition(
                status="needs_review",
                latex=latex.strip(),
                recognizer=self.name,
                error_code="FORMULA_OCR_LOW_CONFIDENCE",
                message="公式已生成 LaTeX，但置信度较低，请对照原图核对。",
            )
        return LocalRecognition(
            status="recognized",
            latex=latex.strip(),
            recognizer=self.name,
            message="公式已由本地 OCR 转为 LaTeX，请对照原图核对。",
        )


def configured_formula_recognizer(data_dir: Path | None) -> Pix2TextFormulaRecognizer | None:
    """Return a local recognizer only when explicitly configured and ready.

    ``auto`` is intentionally opt-in through the environment variable.  This
    avoids importing a large optional dependency or downloading model files
    during normal application startup and keeps the default Lite install at
    zero model calls and zero network downloads.
    """

    mode = os.environ.get("RESEARCHGRAPH_FORMULA_OCR", "").strip().lower()
    if mode not in {"pix2text", "auto", "enabled"}:
        return None
    configured = os.environ.get("RESEARCHGRAPH_FORMULA_MODEL_DIR", "").strip()
    if configured:
        model_dir = Path(configured).expanduser()
    elif data_dir is not None:
        model_dir = data_dir / "formula-ocr" / "mfr-1.5"
    else:
        return None
    if not model_dir.is_dir():
        return None
    return Pix2TextFormulaRecognizer(model_dir)


__all__ = ["Pix2TextFormulaRecognizer", "configured_formula_recognizer"]
