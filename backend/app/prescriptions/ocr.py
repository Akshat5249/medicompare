"""Pluggable OCR engines. Each returns text spans with boxes and per-span quality signals."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.prescriptions.extraction import OcrLine


@dataclass(frozen=True)
class TextSpan:
    text: str
    bbox: tuple[float, float, float, float]
    quality: float


class OcrEngine(Protocol):
    name: str

    @property
    def version(self) -> str: ...

    def recognize(self, image: np.ndarray) -> list[TextSpan]: ...


class TesseractEngine:
    name = "tesseract"

    @property
    def version(self) -> str:
        import pytesseract

        return str(pytesseract.get_tesseract_version())

    def recognize(self, image: np.ndarray) -> list[TextSpan]:
        import pytesseract

        data = pytesseract.image_to_data(
            image, config="--psm 6", output_type=pytesseract.Output.DICT, timeout=60
        )
        spans: list[TextSpan] = []
        for index, text in enumerate(data["text"]):
            confidence = float(data["conf"][index])
            if not text.strip() or confidence < 0:
                continue
            left, top = float(data["left"][index]), float(data["top"][index])
            width, height = float(data["width"][index]), float(data["height"][index])
            spans.append(TextSpan(text, (left, top, left + width, top + height), confidence / 100))
        return spans


class RapidOcrEngine:
    """PP-OCR models via ONNX Runtime (the PaddleOCR model family without the Paddle runtime)."""

    name = "rapidocr"

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    @property
    def version(self) -> str:
        from importlib.metadata import version

        return version("rapidocr-onnxruntime")

    def recognize(self, image: np.ndarray) -> list[TextSpan]:
        result, _elapsed = self._engine(image)
        spans: list[TextSpan] = []
        for box, text, score in result or []:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            spans.append(TextSpan(str(text), (min(xs), min(ys), max(xs), max(ys)), float(score)))
        return spans


@lru_cache
def get_engine(name: str) -> OcrEngine:
    engines: dict[str, type[TesseractEngine] | type[RapidOcrEngine]] = {
        "tesseract": TesseractEngine,
        "rapidocr": RapidOcrEngine,
    }
    if name not in engines:
        raise ValueError(f"Unknown OCR engine {name}")
    return engines[name]()


def spans_to_lines(spans: list[TextSpan], page: int = 0) -> list[OcrLine]:
    """Group spans into reading-order lines by vertical overlap."""
    ordered = sorted(spans, key=lambda s: (s.bbox[1] + s.bbox[3]) / 2)
    groups: list[list[TextSpan]] = []
    for span in ordered:
        centre = (span.bbox[1] + span.bbox[3]) / 2
        height = span.bbox[3] - span.bbox[1]
        if groups:
            last = groups[-1]
            last_centre = sum((s.bbox[1] + s.bbox[3]) / 2 for s in last) / len(last)
            if abs(centre - last_centre) < max(height * 0.6, 4):
                last.append(span)
                continue
        groups.append([span])
    lines: list[OcrLine] = []
    for group in groups:
        group.sort(key=lambda s: s.bbox[0])
        total = sum(len(s.text) for s in group) or 1
        quality = sum(s.quality * len(s.text) for s in group) / total
        box = [
            min(s.bbox[0] for s in group),
            min(s.bbox[1] for s in group),
            max(s.bbox[2] for s in group),
            max(s.bbox[3] for s in group),
        ]
        lines.append(OcrLine(" ".join(s.text for s in group), round(quality, 4), box, page))
    return lines
