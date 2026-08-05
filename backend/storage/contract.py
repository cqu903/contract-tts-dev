"""Segment index, seek mapping, and uploaded-contract storage (content-addressed)."""
from __future__ import annotations
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.text.segmenter import estimate_duration, split_contract

_DAY = 86400.0


def compute_contract_id(text: str, template_id: str) -> str:
    """Content-addressed id = sha256(template_id | text). Binds the raw text to its
    template: same text under different templates yields different ids (different
    segmentation → different seek). See ADR-0001 / ADR-0005."""
    h = hashlib.sha256()
    h.update(template_id.encode("utf-8"))
    h.update(b"|")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


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


def build_index(contract_id: str, text: str, *,
                splitter=split_contract,
                duration_estimator=estimate_duration,
                duration_text_transform: Callable[[str], str] | None = None,
                ) -> SegmentIndex:
    """Build a seek index while keeping raw Segment text private to the server.

    ``duration_text_transform`` lets a Template estimate the text that will
    actually be spoken after language conversion, avoiding large drift when a
    compact amount, date, or identifier expands into many spoken words.
    """
    metas: list[SegmentMeta] = []
    t = 0.0
    for i, seg in enumerate(splitter(text)):
        duration_text = (
            duration_text_transform(seg.text)
            if duration_text_transform is not None
            else seg.text
        )
        dur = duration_estimator(duration_text)
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


class ContractStore:
    """Disk-backed store of uploaded contract raw text, content-addressed by contract_id.

    Originals are kept for ~3 months (creation TTL) so an upload stays seekable /
    re-slicable without re-upload. See ADR-0001 / ADR-0004."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self._manifest: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text("utf-8"))
        return {}

    def _save(self) -> None:
        self.manifest_path.write_text(json.dumps(self._manifest, ensure_ascii=False), "utf-8")

    def _path(self, contract_id: str) -> Path:
        return self.root / f"{contract_id}.txt"

    def put(self, contract_id: str, text: str, *, template_id: str | None = None,
            now: float | None = None) -> None:
        ts = now if now is not None else time.time()
        self._path(contract_id).write_text(text, encoding="utf-8")
        # 内容寻址：相同 id 即相同文本，重复 put 幂等；保留首次写入时间
        if contract_id not in self._manifest:
            self._manifest[contract_id] = {"created_at": ts}
            if template_id is not None:
                self._manifest[contract_id]["template_id"] = template_id
            self._save()

    def get_template_id(self, contract_id: str) -> str | None:
        """Return the canonical Template recorded with a new Contract."""
        entry = self._manifest.get(contract_id)
        return entry.get("template_id") if entry else None

    def get(self, contract_id: str) -> str | None:
        p = self._path(contract_id)
        return p.read_text(encoding="utf-8") if p.exists() else None

    def evict_expired(self, now: float, text_ttl_days: int = 90) -> int:
        """删除创建时间超过 text_ttl_days 的原文（按 creation time）。"""
        cutoff = now - text_ttl_days * _DAY
        removed = 0
        for cid in list(self._manifest.keys()):
            if self._manifest[cid].get("created_at", 0.0) < cutoff:
                p = self._path(cid)
                if p.exists():
                    p.unlink()
                del self._manifest[cid]
                removed += 1
        if removed:
            self._save()
        return removed
