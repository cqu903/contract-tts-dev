"""Deterministic sentence segmentation for contract text."""
from __future__ import annotations
import re
from dataclasses import dataclass

_SENT_END = "。！？；"
_CLAUSE = "，、,;"


@dataclass(frozen=True)
class Segment:
    text: str


def _split_keep_delim(text: str, delims: str) -> list[str]:
    pattern = f"([{re.escape(delims)}])"
    parts = re.split(pattern, text)
    out: list[str] = []
    buf = ""
    for p in parts:
        if p == "":
            continue
        buf += p
        if p in delims:
            out.append(buf)
            buf = ""
    if buf.strip():
        out.append(buf)
    return [s for s in (x.strip() for x in out) if s]


def split_contract(text: str, max_chars: int = 60) -> list[Segment]:
    """Split text into Segments. First by sentence-ending punctuation; any
    sentence longer than max_chars is further split by clause punctuation.
    Deterministic: identical input always yields identical output."""
    text = (text or "").strip()
    segments: list[Segment] = []
    for sentence in _split_keep_delim(text, _SENT_END):
        if len(sentence) <= max_chars:
            segments.append(Segment(sentence))
        else:
            for clause in _split_keep_delim(sentence, _CLAUSE):
                if clause:
                    segments.append(Segment(clause))
    return segments


def estimate_duration(text: str, rate: float = 3.7) -> float:
    """Estimated spoken seconds. Cantonese natural pace ~3.5-4 chars/sec."""
    n = sum(1 for ch in text if not ch.isspace())
    return round(n / rate, 3)
