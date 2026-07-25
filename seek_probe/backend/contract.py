"""Segment index, seek mapping, contract loading."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from seek_probe.backend.segmenter import split_contract, estimate_duration

_CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"
_CONTRACT_FILES = {"sample": _CONTRACTS_DIR / "sample_contract.txt"}


@dataclass(frozen=True)
class SegmentMeta:
    seg_idx: int
    text: str
    est_dur_s: float
    cumulative_start_s: float


@dataclass(frozen=True)
class SegmentIndex:
    contract_id: str
    segments: list[SegmentMeta]
    total_est_s: float


def build_index(contract_id: str, text: str) -> SegmentIndex:
    metas: list[SegmentMeta] = []
    t = 0.0
    for i, seg in enumerate(split_contract(text)):
        dur = estimate_duration(seg.text)
        metas.append(SegmentMeta(i, seg.text, dur, t))
        t += dur
    return SegmentIndex(contract_id, metas, round(t, 3))


def position_to_segment(idx: SegmentIndex, t: float) -> int:
    """Map a progress-bar position (seconds) to a segment index.
    Seek snaps to segment boundaries. Out-of-range clamps to [0, last]."""
    if not idx.segments:
        return 0
    if t < 0:
        return 0
    if t >= idx.total_est_s:
        return len(idx.segments) - 1
    for m in idx.segments:
        if t < m.cumulative_start_s + m.est_dur_s:
            return m.seg_idx
    return len(idx.segments) - 1


def load_contract_text(contract_id: str) -> str:
    p = _CONTRACT_FILES.get(contract_id)
    if p is None or not p.exists():
        raise KeyError(f"unknown contract: {contract_id}")
    return p.read_text(encoding="utf-8")
