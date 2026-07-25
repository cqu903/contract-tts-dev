"""Content-addressed segment cache. Key = hash(segment_text + voice_ref_id).
Identical text (static boilerplate) reuses one file across contracts automatically."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def cache_key(text: str, voice_ref_id: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(b"|")
    h.update(voice_ref_id.encode("utf-8"))
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

    def get(self, key: str) -> Path | None:
        p = self._path(key)
        return p if p.exists() else None

    def put(self, key: str, data: bytes, duration: float | None = None) -> Path:
        p = self._path(key)
        p.write_bytes(data)
        self._manifest[key] = {"duration": duration}
        self._save()
        return p
