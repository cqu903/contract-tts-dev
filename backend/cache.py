"""Content-addressed segment cache. Key = hash(segment_text + engine_id).
Identical text (static boilerplate) reuses one file across contracts automatically.
The engine is part of the key so switching SEEK_PROBE_ENGINE can't serve stale audio
from the other engine (ADR-0006). Voice is a fixed internal attribute of each engine,
not a key dimension — changing it won't invalidate cache, see ADR-0006. Eviction is a
sliding window: entries not hit within audio_ttl_days are removed, and every hit
refreshes last_access_at (ADR-0004)."""
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path

_DAY = 86400.0


def cache_key(text: str, engine_id: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(b"|")
    h.update(engine_id.encode("utf-8"))
    return h.hexdigest()


class SegmentCache:
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

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.wav"

    def has(self, key: str) -> bool:
        return self._path(key).exists()

    def get(self, key: str, *, now: float | None = None) -> Path | None:
        p = self._path(key)
        if not p.exists():
            return None
        # 命中即刷新滑动窗口访问时间（ADR-0004）
        if key in self._manifest:
            self._manifest[key]["last_access_at"] = now if now is not None else time.time()
            self._save()
        return p

    def put(self, key: str, data: bytes, duration: float | None = None, *, now: float | None = None) -> Path:
        p = self._path(key)
        p.write_bytes(data)
        ts = now if now is not None else time.time()
        # 若该 key 已存在，保留原始创建时间（已知条目重新合成）
        created = self._manifest.get(key, {}).get("created_at", ts)
        self._manifest[key] = {"created_at": created, "last_access_at": ts, "duration": duration}
        self._save()
        return p

    def evict_expired(self, now: float, audio_ttl_days: int = 30) -> int:
        """删除最近一次命中超过 audio_ttl_days 的条目（滑动窗口）。"""
        cutoff = now - audio_ttl_days * _DAY
        removed = 0
        for key in list(self._manifest.keys()):
            last = self._manifest[key].get("last_access_at", 0.0)
            if last < cutoff:
                p = self._path(key)
                if p.exists():
                    p.unlink()
                del self._manifest[key]
                removed += 1
        if removed:
            self._save()
        return removed
