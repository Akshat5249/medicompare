"""Deterministic structured extraction from OCR lines.

Extracts only what is visible. A field that is absent is `unknown`; a field present but unreliable
is `unclear` with a null value. Lines holding personal details are dropped and only counted.
Instruction-like text is data: it is dropped and never acted upon.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import jsonschema

from app.safety.injection import looks_like_instruction

UNCLEAR_LINE_QUALITY = 0.45

EXTRACTION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "source_text",
                    "name",
                    "name_state",
                    "strength",
                    "strength_state",
                    "form",
                    "form_state",
                    "frequency",
                    "frequency_state",
                    "duration",
                    "duration_state",
                ],
                "properties": {
                    "source_text": {"type": "string"},
                    "name": {"type": ["string", "null"]},
                    "name_state": {"enum": ["visible", "unclear", "unknown"]},
                    "strength": {"type": ["string", "null"]},
                    "strength_state": {"enum": ["visible", "unclear", "unknown"]},
                    "form": {"type": ["string", "null"]},
                    "form_state": {"enum": ["visible", "unclear", "unknown"]},
                    "frequency": {"type": ["string", "null"]},
                    "frequency_state": {"enum": ["visible", "unclear", "unknown"]},
                    "duration": {"type": ["string", "null"]},
                    "duration_state": {"enum": ["visible", "unclear", "unknown"]},
                },
            },
        }
    },
}

_PII = re.compile(
    r"\b(patient|pt\.?\s*name|name\s*[:\-]|age\s*[:/\-]|sex\s*[:/\-]|gender|m/f|mobile|phone|ph\.?\s*no|tel\b|"
    r"address|addr\b|reg(?:istration)?\.?\s*(?:no|number)|dr\.?\s+[a-z]|doctor|m\.?b\.?b\.?s|md\b|clinic|hospital|"
    r"nursing\s*home|date\s*[:\-]|signature|sign\b|aadhaar|abha|uhid|mrn|email|e-mail|pin\s*[:\-])",
    re.IGNORECASE,
)
_PHONE_OR_DATE = re.compile(r"\b(?:\+?\d[\d\s-]{8,}\d|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
_NOISE = re.compile(
    r"^(rx|r/?x|℞|advice|diagnosis|c/o|o/e|bp\b|pulse\b|temp\b|weight|follow[\s-]*up)\b", re.I
)
_FORM = re.compile(
    r"^\s*(?:\d+[.)]\s*)?(tab(?:let)?s?|cap(?:sule)?s?|inj(?:ection)?|syp|syr(?:up)?|susp(?:ension)?|"
    r"drops?|cream|oint(?:ment)?|gel|inh(?:aler)?|sachet)\b\.?\s*",
    re.IGNORECASE,
)
_STRENGTH = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?\s*(?:mcg|mg|gm|g|iu|ml|%)(?:\s*/\s*\d*(?:\.\d+)?\s*(?:ml|mg))?"
    r"(?:\s*\+\s*\d+(?:\.\d+)?\s*(?:mcg|mg|gm|g|iu|ml|%))*)",
    re.IGNORECASE,
)
_FREQUENCY = re.compile(
    r"(?<![\w-])(\d(?:\.\d)?\s*-\s*\d(?:\.\d)?\s*-\s*\d(?:\.\d)?|o\.?d\.?|b\.?d\.?|t\.?d\.?s\.?|q\.?i\.?d\.?|"
    r"h\.?s\.?|s\.?o\.?s\.?|stat|once\s+daily|twice\s+daily|at\s+night)(?![\w])",
    re.IGNORECASE,
)
_DURATION = re.compile(
    r"(?:[x\u00d7*]\s*|for\s+)?(\d+\s*(?:days?|d|weeks?|wks?|months?|mo))\b", re.IGNORECASE
)
_RELEASE = re.compile(r"\b(sr|er|xr|xl|cr|mr|od|ec|dt)\b", re.IGNORECASE)
_MEDICINE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9+\-\s/.]{2,}")


@dataclass
class OcrLine:
    text: str
    quality: float
    bbox: list[float] | None = None
    page: int = 0


@dataclass
class ExtractedField:
    value: str | None
    state: str


@dataclass
class ExtractedLine:
    source_text: str
    name: ExtractedField
    strength: ExtractedField
    form: ExtractedField
    frequency: ExtractedField
    duration: ExtractedField
    quality: float
    bbox: list[float] | None
    page: int


@dataclass
class ExtractionResult:
    items: list[ExtractedLine] = field(default_factory=list)
    redacted_lines: int = 0
    instruction_lines: int = 0
    ignored_lines: int = 0


def _field(value: str | None, quality: float) -> ExtractedField:
    if value is None:
        return ExtractedField(None, "unknown")
    if quality < UNCLEAR_LINE_QUALITY:
        return ExtractedField(None, "unclear")
    return ExtractedField(re.sub(r"\s+", " ", value).strip(), "visible")


def parse_line(line: OcrLine) -> ExtractedLine | None:
    """Parse one line, or return None if nothing suggests a medicine."""
    text = re.sub(r"\s+", " ", line.text).strip()
    form_match = _FORM.match(text)
    strength_match = _STRENGTH.search(text)
    if form_match is None and strength_match is None:
        return None
    remainder = text
    form = form_match.group(1) if form_match else None
    if form_match:
        remainder = remainder[form_match.end() :]
    strength = strength_match.group(1) if strength_match else None
    frequency_match = _FREQUENCY.search(remainder)
    frequency = frequency_match.group(1) if frequency_match else None
    duration_match = _DURATION.search(remainder)
    duration = duration_match.group(1) if duration_match else None
    cut_points = [
        match.start()
        for match in (_STRENGTH.search(remainder), frequency_match, duration_match)
        if match is not None
    ]
    name_part = remainder[: min(cut_points)] if cut_points else remainder
    name_part = re.sub(r"^[\s.\-:*]+|[\s.\-:*,]+$", "", name_part)
    name = name_part if _MEDICINE_NAME.fullmatch(name_part or "") else None
    name_field = _field(name, line.quality)
    if name is None and name_part:
        name_field = ExtractedField(None, "unclear")  # text is there but is not readable as a name
    return ExtractedLine(
        source_text=text,
        name=name_field,
        strength=_field(strength, line.quality),
        form=_field(form, line.quality),
        frequency=_field(frequency, line.quality),
        duration=_field(duration, line.quality),
        quality=line.quality,
        bbox=line.bbox,
        page=line.page,
    )


def extract(lines: list[OcrLine]) -> ExtractionResult:
    result = ExtractionResult()
    for line in lines:
        text = line.text.strip()
        if not text:
            continue
        if looks_like_instruction(text):
            result.instruction_lines += 1
            continue
        if _PII.search(text) or _PHONE_OR_DATE.search(text):
            result.redacted_lines += 1
            continue
        if _NOISE.match(text):
            result.ignored_lines += 1
            continue
        parsed = parse_line(line)
        if parsed is None:
            result.ignored_lines += 1
            continue
        result.items.append(parsed)
    validate_output(to_schema_dict(result))
    return result


def to_schema_dict(result: ExtractionResult) -> dict[str, Any]:
    return {
        "items": [
            {
                "source_text": item.source_text,
                "name": item.name.value,
                "name_state": item.name.state,
                "strength": item.strength.value,
                "strength_state": item.strength.state,
                "form": item.form.value,
                "form_state": item.form.state,
                "frequency": item.frequency.value,
                "frequency_state": item.frequency.state,
                "duration": item.duration.value,
                "duration_state": item.duration.state,
            }
            for item in result.items
        ]
    }


def validate_output(data: dict[str, Any]) -> None:
    jsonschema.validate(data, EXTRACTION_SCHEMA)


def release_marker(text: str | None) -> str | None:
    """A visible release-type marker such as SR or ER. Never inferred from anything else."""
    if not text:
        return None
    match = _RELEASE.search(text)
    return match.group(1).lower() if match else None
