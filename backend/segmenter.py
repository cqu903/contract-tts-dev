"""Deterministic sentence segmentation for contract text."""
from __future__ import annotations
import re
from dataclasses import dataclass

_SENT_END = "。！？；"
# NOTE: ASCII ',' is intentionally excluded — it appears in comma-grouped
# numbers (126,000), and treating it as a clause boundary chops amounts
# mid-number. Chinese prose uses the fullwidth '，' (included) for clauses.
_CLAUSE = "，、;"

TARGET = 20    # merge short fragments until a segment reaches ~this length
SOFT_MAX = 45  # never merge beyond this (keeps segments TTS-friendly)
HARD_MAX = 50  # split any segment longer than this
CRUMB_MAX = 1  # a 1-char segment is a stray (和/及/或/］) -> fold into previous

# Boundaries for breaking an over-long clause that has no ，、；: fullwidth colon
# (form-field separator), fullwidth paren, book-title bracket, ASCII paren.
_OVERLONG_DELIMS = "：（《("


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


def _split_overlong(piece: str, hard_max: int) -> list[str]:
    """Break a piece longer than hard_max on the next structural boundary
    (fullwidth colon / paren / book-title bracket / ASCII paren). Delimiters
    stay attached to the preceding piece. An unsplittable piece is returned
    whole (callers have already split off newlines, so piece is a single line)."""
    if len(piece) <= hard_max:
        return [piece]
    if any(d in piece for d in _OVERLONG_DELIMS):
        out = [p for p in (x.strip() for x in _split_keep_delim(piece, _OVERLONG_DELIMS)) if p]
        if out:
            return out
    return [piece]                                 # no clean boundary: leave whole


def _merge_short(pieces: list[str], target: int, soft_max: int) -> list[str]:
    """Greedily concatenate adjacent pieces until ~target is reached, capped at
    soft_max. A single piece already over soft_max is kept alone. The trailing
    piece is folded back into the previous one if it fits, to avoid a tiny tail."""
    out: list[str] = []
    buf = ""
    for p in pieces:
        if not buf:
            buf = p
        elif len(buf) >= target:                   # buf already big enough -> flush
            out.append(buf)
            buf = p
        elif len(buf) + len(p) <= soft_max:        # merge
            buf += p
        else:                                      # would blow soft_max -> flush
            out.append(buf)
            buf = p
    if buf:
        # fold a small (< target) tail into the previous segment when it fits,
        # so we don't emit a lone crumb; a full-sized tail gets its own segment
        if out and len(buf) < target and len(out[-1]) + len(buf) <= soft_max:
            out[-1] += buf
        else:
            out.append(buf)
    return out


def split_contract(text: str, target: int = TARGET, soft_max: int = SOFT_MAX,
                   hard_max: int = HARD_MAX) -> list[Segment]:
    """Split text into Segments.

    Hard boundaries (never merged across): sentence-end punctuation (。！？；)
    and newlines (form-field boundaries). Within a line, a clause longer than
    `hard_max` is split (newlines / fullwidth parens); short fragments are then
    merged toward `target`, capped at `soft_max`.

    Deterministic: identical input always yields identical output."""
    text = (text or "").strip()
    segments: list[Segment] = []
    for sentence in _split_keep_delim(text, _SENT_END):
        for line in sentence.split("\n"):
            line = line.strip()
            if not line:
                continue
            if len(line) <= hard_max:
                pieces = [line]
            else:
                pieces = _split_keep_delim(line, _CLAUSE)
                pieces = [p for piece in pieces for p in _split_overlong(piece, hard_max)]
            pieces = [p for p in (x.strip() for x in pieces) if p]
            for merged in _merge_short(pieces, target, soft_max):
                segments.append(Segment(merged))
    return _absorb_crumbs(segments)


def _absorb_crumbs(segments: list[Segment]) -> list[Segment]:
    """Fold stray ≤CRUMB_MAX segments (a lone 和/及/或/］ stranded across a
    sentence or newline boundary) into the previous segment so they don't
    surface as meaningless 1-2 char seek units."""
    out: list[Segment] = []
    for seg in segments:
        # a ≤CRUMB_MAX stray always folds into the previous segment; the 1-2
        # char overflow on an already-large segment beats a meaningless seek unit
        if out and len(seg.text) <= CRUMB_MAX:
            out[-1] = Segment(out[-1].text + seg.text)
        else:
            out.append(seg)
    return out


def estimate_duration(text: str, rate: float = 3.7) -> float:
    """Estimated spoken seconds. Cantonese natural pace ~3.5-4 chars/sec."""
    n = sum(1 for ch in text if not ch.isspace())
    return round(n / rate, 3)
