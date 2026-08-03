"""Template-specific deterministic segmentation profiles."""
from __future__ import annotations

import re

from .segmenter import Segment, split_contract


def split_contract_zh(text: str) -> list[Segment]:
    """Split a Mandarin contract with independently tunable Chinese limits."""
    return split_contract(text, target=22, soft_max=48, hard_max=52)


def estimate_duration_zh(text: str, rate: float = 4.0) -> float:
    """Estimate Mandarin speech duration by non-whitespace character count."""
    count = sum(1 for char in text if not char.isspace())
    return round(count / rate, 3)


_EN_SENTENCE_END = re.compile(r"(?<=[.!?;])(?:\s+|$)")
_EN_WORD = re.compile(r"\S+")


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


def split_contract_en(text: str, *, target: int = 80, soft_max: int = 105,
                      hard_max: int = 120) -> list[Segment]:
    """Split English on sentence boundaries and never in the middle of a word."""
    if min(target, soft_max, hard_max) <= 0:
        raise ValueError("English segmentation limits must be positive")
    soft_max = min(soft_max, hard_max)
    target = min(target, soft_max)
    segments: list[Segment] = []
    for raw_line in (text or "").strip().splitlines():
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
    return segments


def estimate_duration_en(text: str, rate: float = 2.6) -> float:
    """Estimate English speech duration by spoken-word count."""
    words = len(re.findall(r"\b[\w']+\b", text or ""))
    return round(words / rate, 3)
