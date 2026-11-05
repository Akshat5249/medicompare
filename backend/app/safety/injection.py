"""Recognise instruction-like text inside uploaded documents.

Uploaded text is data. Nothing in the pipeline executes it, and the deterministic pipeline has no
instruction channel at all. This detector exists so such lines are dropped from extraction, counted
and never forwarded to an optional LLM adapter.
"""

from __future__ import annotations

import re

_PATTERNS = re.compile(
    r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+|your\s+|previous\s+|prior\s+|above\s+)+"
    r"|system\s*(prompt|message|:)"
    r"|you\s+are\s+(now|an?)\b"
    r"|mark\s+(this|all|every|the)\b.{0,30}(verified|confirmed|approved)"
    r"|(auto|skip|bypass)[\s-]*(verif|approv|confirm)"
    r"|(set|change)\s+(status|price|confidence)\b"
    r"|as\s+an\s+(ai|assistant|llm)\b"
    r"|\b(assistant|instruction|prompt)\s*:"
    r"|<\s*/?\s*(script|system|instructions?)\b"
    r"|\b(api[_\s-]?key|password|secret)\b",
    re.IGNORECASE,
)


def looks_like_instruction(text: str) -> bool:
    return _PATTERNS.search(text) is not None
