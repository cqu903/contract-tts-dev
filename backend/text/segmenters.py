"""Template-specific deterministic segmentation profiles."""
from __future__ import annotations

import re

from .segmenter import Segment


_EN_SENTENCE_END = re.compile(r"(?<=[.!?;])(?:\s+|$)")
_EN_WORD = re.compile(r"\S+")
_EN_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EN_MARKER_ONLY = re.compile(
    r"^(?:[（(](?:[A-Za-z]+|\d+(?:\.\d+)*)[）)]|"
    r"(?:\d+(?:\.\d+)*|[A-Za-z])[.)．])$"
)
_EN_PUNCTUATION_ONLY = re.compile(r"^[,.;:!?\-–—)\]）】]+$")


def _english_sentences(line: str) -> list[str]:
    return [part.strip() for part in _EN_SENTENCE_END.split(line) if part.strip()]


def _pack_english_words(sentence: str, hard_max: int) -> list[str]:
    words = _EN_WORD.findall(sentence)
    out: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if current and len(candidate) > hard_max:
            out.append(current)
            current = word
        else:
            current = candidate
    if current:
        out.append(current)
    return out


def _pack_english_pieces(pieces: list[str], target: int, soft_max: int) -> list[str]:
    """Pack adjacent sentence/word pieces toward target without crossing soft_max."""
    out: list[str] = []
    current = ""
    for piece in pieces:
        candidate = piece if not current else f"{current} {piece}"
        if current and (len(current) >= target or len(candidate) > soft_max):
            out.append(current)
            current = piece
        else:
            current = candidate
    if current:
        out.append(current)
    return out


def _repair_english_fragments(segments: list[Segment]) -> list[Segment]:
    """Attach extracted list labels and stray punctuation to readable text."""
    repaired: list[str] = []
    pending: list[str] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        if _EN_MARKER_ONLY.fullmatch(text):
            pending.append(text)
            continue
        if _EN_PUNCTUATION_ONLY.fullmatch(text):
            if repaired:
                repaired[-1] += text
            else:
                pending.append(text)
            continue
        if pending:
            text = " ".join([*pending, text])
            pending.clear()
        repaired.append(text)

    if pending:
        if repaired:
            repaired[-1] += " " + " ".join(pending)
        else:
            repaired.append(" ".join(pending))
    return [Segment(text) for text in repaired]


def split_contract_en(text: str, *, target: int = 80, soft_max: int = 105,
                      hard_max: int = 120) -> list[Segment]:
    """Split English on sentence boundaries and never in the middle of a word."""
    if min(target, soft_max, hard_max) <= 0:
        raise ValueError("English segmentation limits must be positive")
    soft_max = min(soft_max, hard_max)
    target = min(target, soft_max)
    segments: list[Segment] = []
    cleaned = _EN_CONTROL_CHARS.sub("", text or "")
    for raw_line in cleaned.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pieces: list[str] = []
        for sentence in _english_sentences(line):
            if len(sentence) <= hard_max:
                pieces.append(sentence)
            else:
                pieces.extend(_pack_english_words(sentence, hard_max))
        segments.extend(
            Segment(piece) for piece in _pack_english_pieces(pieces, target, soft_max)
        )
    return _repair_english_fragments(segments)


def estimate_duration_en(text: str, rate: float = 2.6) -> float:
    """Estimate English speech duration by spoken-word count."""
    words = len(re.findall(r"\b[\w']+\b", text or ""))
    return round(words / rate, 3)
