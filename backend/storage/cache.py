"""Content-addressed cache for complete, format-aware Segment audio.

Keys cover Template, normalized text, Engine Profile, its manual cache version,
and a synthesis fingerprint. The fingerprint is the stable extension point for
Driver, voice, rate, audio format, and adapter-version isolation (ADR-0009).
Identical text (static boilerplate) reuses one file across contracts automatically.
The selected profile engine is part of the key, so per-language engine switches
cannot serve stale audio from the other engine. Eviction is a sliding window:
entries not hit within audio_ttl_days are removed, and every hit refreshes
last_access_at (ADR-0004)."""
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path

from backend.audio import AudioArtifact, AudioFormat

_DAY = 86400.0


def cache_key(
    template_id: str,
    text: str,
    engine_profile_id: str,
    cache_version: str = "v1",
    *,
    synthesis_fingerprint: str = "audio-artifact-v1",
) -> str:
    h = hashlib.sha256()
    h.update(template_id.encode("utf-8"))
    h.update(b"|")
    h.update(text.encode("utf-8"))
    h.update(b"|")
    h.update(engine_profile_id.encode("utf-8"))
    h.update(b"|")
    h.update(cache_version.encode("utf-8"))
    h.update(b"|")
    h.update(synthesis_fingerprint.encode("utf-8"))
    return h.hexdigest()


class SegmentCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self._manifest: dict[str, object] = self._load()

    def _load(self) -> dict[str, object]:
        if self.manifest_path.exists():
            try:
                manifest = json.loads(self.manifest_path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
            return manifest if isinstance(manifest, dict) else {}
        return {}

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _save(self, manifest: dict[str, object] | None = None) -> None:
        payload = json.dumps(
            self._manifest if manifest is None else manifest,
            ensure_ascii=False,
        ).encode("utf-8")
        self._atomic_write(self.manifest_path, payload)

    def _entry_format(self, key: str) -> AudioFormat | None:
        entry = self._manifest.get(key)
        if not isinstance(entry, dict):
            return None
        return AudioFormat.from_metadata(
            entry.get("audio_format"),
            entry.get("media_type"),
            entry.get("file_extension"),
        )

    def _path(self, key: str, audio_format: AudioFormat) -> Path:
        return self.root / f"{key}{audio_format.file_extension}"

    def has(self, key: str) -> bool:
        audio_format = self._entry_format(key)
        if audio_format is None:
            return False
        path = self._path(key, audio_format)
        return path.exists() and path.stat().st_size > 0

    def get(self, key: str, *, now: float | None = None) -> AudioArtifact | None:
        audio_format = self._entry_format(key)
        if audio_format is None:
            return None
        entry = self._manifest.get(key)
        if not isinstance(entry, dict):
            return None
        p = self._path(key, audio_format)
        if not p.exists():
            return None
        try:
            artifact = AudioArtifact(p.read_bytes(), audio_format)
        except (OSError, ValueError):
            return None
        # 命中即刷新滑动窗口访问时间（ADR-0004）
        entry["last_access_at"] = now if now is not None else time.time()
        self._save()
        return artifact

    def put(
        self,
        key: str,
        artifact: AudioArtifact,
        duration: float | None = None,
        *,
        now: float | None = None,
    ) -> Path:
        if not isinstance(artifact, AudioArtifact):
            raise TypeError("SegmentCache.put requires an AudioArtifact")
        previous_format = self._entry_format(key)
        p = self._path(key, artifact.audio_format)
        previous_data = (
            p.read_bytes()
            if previous_format is artifact.audio_format and p.exists()
            else None
        )
        self._atomic_write(p, artifact.data)
        ts = now if now is not None else time.time()
        # 若该 key 已存在，保留原始创建时间（已知条目重新合成）
        previous_entry = self._manifest.get(key)
        created = (
            previous_entry.get("created_at", ts)
            if isinstance(previous_entry, dict)
            else ts
        )
        updated_manifest = dict(self._manifest)
        updated_manifest[key] = {
            "created_at": created,
            "last_access_at": ts,
            "duration": duration,
            "audio_format": artifact.audio_format.format_id,
            "media_type": artifact.media_type,
            "file_extension": artifact.file_extension,
        }
        try:
            self._save(updated_manifest)
        except Exception:
            if previous_data is not None:
                self._atomic_write(p, previous_data)
            elif previous_format is not artifact.audio_format:
                p.unlink(missing_ok=True)
            raise
        self._manifest = updated_manifest
        if previous_format is not None and previous_format is not artifact.audio_format:
            previous_path = self._path(key, previous_format)
            if previous_path.exists():
                previous_path.unlink()
        return p

    def evict_expired(self, now: float, audio_ttl_days: int = 30) -> int:
        """删除最近一次命中超过 audio_ttl_days 的条目（滑动窗口）。"""
        cutoff = now - audio_ttl_days * _DAY
        removed = 0
        for key in list(self._manifest.keys()):
            entry = self._manifest[key]
            last = entry.get("last_access_at", 0.0) if isinstance(entry, dict) else 0.0
            if not isinstance(last, (int, float)):
                last = 0.0
            if last < cutoff:
                # Remove every canonical suffix so legacy WAV entries and any
                # orphan left by an interrupted format change expire safely.
                for audio_format in AudioFormat:
                    p = self._path(key, audio_format)
                    if p.exists():
                        p.unlink()
                del self._manifest[key]
                removed += 1
        referenced_paths = {
            self._path(key, audio_format)
            for key in self._manifest
            if (audio_format := self._entry_format(key)) is not None
        }
        for audio_format in AudioFormat:
            for path in self.root.glob(f"*{audio_format.file_extension}"):
                if path in referenced_paths:
                    continue
                try:
                    is_expired = path.stat().st_mtime < cutoff
                except OSError:
                    continue
                if is_expired:
                    path.unlink(missing_ok=True)
                    removed += 1
        if removed:
            self._save()
        return removed
