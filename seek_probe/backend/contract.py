"""Segment index, seek mapping, contract loading."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from seek_probe.backend.segmenter import split_contract, estimate_duration

_CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"
_CONTRACT_FILES = {
    "sample": _CONTRACTS_DIR / "sample_contract.txt",
    "zacl0603": _CONTRACTS_DIR / "zacl0603.txt",
    "xcash": _CONTRACTS_DIR / "xcash.txt",
}


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


def dump_segments(idx: SegmentIndex, path: Path) -> Path:
    """Write the raw segmentation result to disk for inspection/tuning.

    Verbatim dump: exactly the segments split_contract produced (no
    normalization, no cleanup), one per line with its index and estimated
    timing, so segmentation tweaks can be reviewed against ground truth."""
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# {idx.contract_id}: {len(idx.segments)} segments, "
                f"total_est_s={idx.total_est_s}\n")
        for m in idx.segments:
            end = m.cumulative_start_s + m.est_dur_s
            f.write(f"[{m.seg_idx:03d}] ({m.cumulative_start_s:7.1f}s ~ {end:7.1f}s) {m.text}\n")
    return path


def load_contract_text(contract_id: str) -> str:
    p = _CONTRACT_FILES.get(contract_id)
    if p is None or not p.exists():
        raise KeyError(f"unknown contract: {contract_id}")
    return p.read_text(encoding="utf-8")
