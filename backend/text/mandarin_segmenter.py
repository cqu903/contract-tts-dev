"""Deterministic Mandarin contract segmentation.

Mandarin keeps sentence/newline boundaries, uses Chinese clause punctuation for
natural pauses, and guarantees bounded chunks through a token-aware fallback.
It deliberately does not reuse the Cantonese packing algorithm so both profiles
can evolve independently.
"""
from __future__ import annotations

import re

from .segmenter import Segment

TARGET = 24
SOFT_MAX = 46
HARD_MAX = 54

_SENTENCE_END = "。！？；"
_CLAUSE_END = "，、："
_LEFT_BOUNDARY = "，、：；。！？）】》」』)"
_RIGHT_BOUNDARY = "（【《「『("
_ASCII_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/@+-]*")
_PUNCTUATION_ONLY = re.compile(r"^[，、：；。！？）】》」』)］]+$")
_NUMBER_HEADING = re.compile(r"^(?:\d+|[A-Za-z])[.．]$")
_FORWARD_CONNECTORS = {"和", "及", "或", "以及"}


def _split_keep_delimiter(text: str, delimiters: str) -> list[str]:
    parts = re.split(f"([{re.escape(delimiters)}])", text)
    result: list[str] = []
    current = ""
    for part in parts:
        if not part:
            continue
        current += part
        if part in delimiters:
            if current.strip():
                result.append(current.strip())
            current = ""
    if current.strip():
        result.append(current.strip())
    return result


def _cut_inside_ascii_token(text: str, cut: int) -> tuple[int, int] | None:
    for match in _ASCII_TOKEN.finditer(text):
        if match.start() < cut < match.end():
            return match.start(), match.end()
    return None


def _safe_cut(text: str, hard_max: int) -> int:
    """Choose a Mandarin pause near hard_max without dangling opening brackets."""
    minimum = max(1, hard_max // 2)
    for index in range(hard_max - 1, minimum - 1, -1):
        char = text[index]
        if char in _LEFT_BOUNDARY:
            return index + 1
        if char in _RIGHT_BOUNDARY or char.isspace():
            return index

    token = _cut_inside_ascii_token(text, hard_max)
    if token is not None:
        start, end = token
        if start >= minimum:
            return start
        return end
    return hard_max


def _split_long_piece(piece: str, hard_max: int) -> list[str]:
    chunks: list[str] = []
    remaining = piece.strip()
    while len(remaining) > hard_max:
        cut = _safe_cut(remaining, hard_max)
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _pack_clauses(pieces: list[str], target: int, soft_max: int) -> list[str]:
    packed: list[str] = []
    current = ""
    for piece in pieces:
        candidate = current + piece
        if current and (len(current) >= target or len(candidate) > soft_max):
            packed.append(current)
            current = piece
        else:
            current = candidate
    if current:
        if packed and len(current) < target and len(packed[-1]) + len(current) <= soft_max:
            packed[-1] += current
        else:
            packed.append(current)
    return packed


def _is_forward_fragment(text: str) -> bool:
    return (
        text in _FORWARD_CONNECTORS
        or bool(_NUMBER_HEADING.fullmatch(text))
        or (len(text) <= 8 and text.endswith(("：", ":")))
    )


def _repair_fragments(segments: list[Segment]) -> list[Segment]:
    """Repair fragments that would sound unnatural as standalone Mandarin."""
    repaired: list[str] = []
    pending = ""

    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue

        if _PUNCTUATION_ONLY.fullmatch(text):
            if repaired:
                repaired[-1] += text
            else:
                pending += text
            continue

        if _is_forward_fragment(text):
            pending += text
            continue

        if repaired and repaired[-1].endswith(tuple(_RIGHT_BOUNDARY)):
            opening = repaired[-1][-1]
            repaired[-1] = repaired[-1][:-1].rstrip()
            text = opening + text

        if pending:
            text = pending + text
            pending = ""
        repaired.append(text)

    if pending:
        if repaired:
            repaired[-1] += pending
        else:
            repaired.append(pending)
    return [Segment(text) for text in repaired if text]


def split_contract_zh(text: str, *, target: int = TARGET, soft_max: int = SOFT_MAX,
                      hard_max: int = HARD_MAX) -> list[Segment]:
    """Split Mandarin contract text using Mandarin-specific pause rules.

    Newlines and sentence punctuation are never crossed. Within a sentence,
    Chinese commas, enumeration commas, and colons are preferred pauses. A
    token-aware fallback bounds punctuation-free text without splitting ASCII
    identifiers when avoidable.
    """
    if min(target, soft_max, hard_max) <= 0:
        raise ValueError("Mandarin segmentation limits must be positive")
    soft_max = min(soft_max, hard_max)
    target = min(target, soft_max)

    segments: list[Segment] = []
    for raw_line in (text or "").strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for sentence in _split_keep_delimiter(line, _SENTENCE_END):
            clauses = (
                _split_keep_delimiter(sentence, _CLAUSE_END)
                if len(sentence) > target
                else [sentence]
            )
            pieces = [
                chunk
                for clause in clauses
                for chunk in _split_long_piece(clause, hard_max)
            ]
            segments.extend(
                Segment(piece) for piece in _pack_clauses(pieces, target, soft_max)
            )
    return _repair_fragments(segments)


def estimate_duration_zh(text: str, rate: float = 4.0) -> float:
    """Estimate Mandarin speech duration by non-whitespace character count."""
    count = sum(1 for char in text if not char.isspace())
    return round(count / rate, 3)
