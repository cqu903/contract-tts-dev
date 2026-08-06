import json
import os
from pathlib import Path

import pytest

from backend.audio import AudioArtifact, AudioFormat
from backend.cache import cache_key, SegmentCache


def test_key_stable_for_same_text_engine_distinct_otherwise():
    assert cache_key("xcash_yue", "你好", "e1", "v1") == cache_key("xcash_yue", "你好", "e1", "v1")
    assert cache_key("xcash_yue", "你好", "e1", "v1") != cache_key("xcash_yue", "你好", "e2", "v1")
    assert cache_key("xcash_yue", "你好", "e1", "v1") != cache_key("xcash_zh", "你好", "e1", "v1")
    assert cache_key("xcash_yue", "你好", "e1", "v1") != cache_key("xcash_yue", "再见", "e1", "v1")
    assert cache_key("xcash_yue", "你好", "e1", "v1") != cache_key("xcash_yue", "你好", "e1", "v2")
    assert cache_key(
        "xcash_yue",
        "你好",
        "e1",
        "v1",
        synthesis_fingerprint="wav-adapter-v1",
    ) != cache_key(
        "xcash_yue",
        "你好",
        "e1",
        "v1",
        synthesis_fingerprint="mp3-adapter-v1",
    )


def test_put_then_get_roundtrip_and_access_refresh(tmp_path):
    c = SegmentCache(tmp_path / "cache")
    key = cache_key("xcash_yue", "x", "e", "v1")
    assert c.get(key) is None
    artifact = AudioArtifact(b"RIFFxxxx", AudioFormat.WAV)
    stored = c.put(key, artifact, duration=1.5, now=1000.0)
    assert stored.suffix == ".wav"
    assert c.has(key)
    got = c.get(key, now=2000.0)
    assert got == artifact
    # hit refreshed last_access_at; created_at is preserved
    assert c._manifest[key]["last_access_at"] == 2000.0
    assert c._manifest[key]["created_at"] == 1000.0


def test_evict_removes_entries_not_hit_within_window(tmp_path):
    c = SegmentCache(tmp_path / "cache")
    cold = cache_key("xcash_yue", "cold", "e", "v1")
    hot = cache_key("xcash_yue", "hot", "e", "v1")
    c.put(cold, AudioArtifact(b"mp3-cold", AudioFormat.MP3), now=0.0)
    c.put(hot, AudioArtifact(b"wav-hot", AudioFormat.WAV), now=0.0)
    c.get(hot, now=40 * 86400)          # hot hit at day 40
    # now = day 50: cold last hit day 0 (>30d ago) → evicted; hot last hit day 40 (<30d) → kept
    removed = c.evict_expired(50 * 86400, audio_ttl_days=30)
    assert removed == 1
    assert not c.has(cold)
    assert c.has(hot)


def test_replacing_an_entry_with_a_new_format_removes_the_old_file(tmp_path):
    c = SegmentCache(tmp_path / "cache")
    key = cache_key("xcash_yue", "replace", "e", "v1")

    wav_path = c.put(key, AudioArtifact(b"wav-data", AudioFormat.WAV))
    mp3 = AudioArtifact(b"mp3-data", AudioFormat.MP3)
    mp3_path = c.put(key, mp3)

    assert not wav_path.exists()
    assert mp3_path.suffix == ".mp3"
    assert c.get(key) == mp3


def test_mp3_metadata_survives_cache_restart(tmp_path):
    root = tmp_path / "cache"
    key = cache_key("xcash_yue", "mp3", "e", "v1")
    expected = AudioArtifact(b"mp3-data", AudioFormat.MP3)
    path = SegmentCache(root).put(key, expected)

    restored = SegmentCache(root).get(key)

    assert path.suffix == ".mp3"
    assert restored == expected


def test_mismatched_manifest_and_empty_files_are_cache_misses(tmp_path):
    root = tmp_path / "cache"
    key = cache_key("xcash_yue", "mismatch", "e", "v1")
    cache = SegmentCache(root)
    path = cache.put(key, AudioArtifact(b"mp3-data", AudioFormat.MP3))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest[key]["media_type"] = "audio/wav"
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert SegmentCache(root).get(key) is None

    manifest[key]["media_type"] = "audio/mpeg"
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    path.write_bytes(b"")

    assert SegmentCache(root).get(key) is None


def test_legacy_wav_without_format_metadata_is_not_reused(tmp_path):
    root = tmp_path / "cache"
    root.mkdir()
    key = "legacy-key"
    (root / f"{key}.wav").write_bytes(b"legacy-wav")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                key: {
                    "created_at": 1.0,
                    "last_access_at": 1.0,
                    "duration": None,
                }
            }
        ),
        encoding="utf-8",
    )

    cache = SegmentCache(root)

    assert not cache.has(key)
    assert cache.get(key) is None


def test_empty_or_noncanonical_audio_artifacts_are_rejected():
    with pytest.raises(ValueError, match="non-empty bytes"):
        AudioArtifact(b"", AudioFormat.WAV)
    with pytest.raises(ValueError, match="canonical"):
        AudioArtifact(b"data", "wav")  # type: ignore[arg-type]


def test_a_corrupt_manifest_is_treated_as_an_empty_cache(tmp_path):
    root = tmp_path / "cache"
    root.mkdir()
    (root / "manifest.json").write_text("{truncated", encoding="utf-8")

    cache = SegmentCache(root)

    assert cache.get("any-key") is None
    assert not cache.has("any-key")


def test_failed_atomic_replace_keeps_the_previous_artifact(tmp_path, monkeypatch):
    root = tmp_path / "cache"
    cache = SegmentCache(root)
    key = cache_key("xcash_yue", "atomic", "e", "v1")
    previous = AudioArtifact(b"wav-complete", AudioFormat.WAV)
    cache.put(key, previous)
    real_replace = Path.replace

    def fail_mp3_replace(path, target):
        if path.name == f"{key}.mp3.tmp":
            raise OSError("simulated interrupted replace")
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_mp3_replace)

    with pytest.raises(OSError, match="interrupted replace"):
        cache.put(key, AudioArtifact(b"mp3-complete", AudioFormat.MP3))

    assert cache.get(key) == previous
    assert not (root / f"{key}.mp3").exists()
    assert not (root / f"{key}.mp3.tmp").exists()


def test_failed_manifest_commit_keeps_the_previous_artifact(tmp_path, monkeypatch):
    root = tmp_path / "cache"
    cache = SegmentCache(root)
    key = cache_key("xcash_yue", "manifest-atomic", "e", "v1")
    previous = AudioArtifact(b"wav-complete", AudioFormat.WAV)
    cache.put(key, previous)
    real_replace = Path.replace

    def fail_manifest_replace(path, target):
        if path.name == "manifest.json.tmp":
            raise OSError("simulated manifest interruption")
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_manifest_replace)

    with pytest.raises(OSError, match="manifest interruption"):
        cache.put(key, AudioArtifact(b"mp3-complete", AudioFormat.MP3))

    monkeypatch.setattr(Path, "replace", real_replace)
    assert cache.get(key) == previous
    assert not (root / f"{key}.mp3").exists()
    assert not (root / "manifest.json.tmp").exists()


def test_failed_manifest_commit_rolls_back_same_format_bytes(tmp_path, monkeypatch):
    root = tmp_path / "cache"
    cache = SegmentCache(root)
    key = cache_key("xcash_yue", "same-format-atomic", "e", "v1")
    previous = AudioArtifact(b"old-wav", AudioFormat.WAV)
    cache.put(key, previous)
    real_replace = Path.replace

    def fail_manifest_replace(path, target):
        if path.name == "manifest.json.tmp":
            raise OSError("simulated manifest interruption")
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_manifest_replace)

    with pytest.raises(OSError, match="manifest interruption"):
        cache.put(key, AudioArtifact(b"new-wav", AudioFormat.WAV))

    monkeypatch.setattr(Path, "replace", real_replace)
    assert cache.get(key) == previous


def test_non_object_manifest_entry_is_a_miss_and_can_be_repaired(tmp_path):
    root = tmp_path / "cache"
    root.mkdir()
    key = "bad-entry"
    (root / "manifest.json").write_text(
        json.dumps({key: "not-an-object"}), encoding="utf-8"
    )
    cache = SegmentCache(root)
    repaired = AudioArtifact(b"repaired-wav", AudioFormat.WAV)

    assert cache.get(key) is None
    cache.put(key, repaired, now=100.0)

    assert cache.get(key, now=200.0) == repaired


def test_eviction_removes_audio_for_a_non_object_manifest_entry(tmp_path):
    root = tmp_path / "cache"
    root.mkdir()
    key = "bad-entry"
    audio_path = root / f"{key}.wav"
    audio_path.write_bytes(b"orphaned-wav")
    (root / "manifest.json").write_text(
        json.dumps({key: ["not", "an", "object"]}), encoding="utf-8"
    )
    cache = SegmentCache(root)

    removed = cache.evict_expired(40 * 86400, audio_ttl_days=30)

    assert removed == 1
    assert not audio_path.exists()
    assert json.loads((root / "manifest.json").read_text(encoding="utf-8")) == {}


def test_eviction_removes_expired_orphans_after_manifest_corruption(tmp_path):
    root = tmp_path / "cache"
    root.mkdir()
    orphan = root / "orphan.mp3"
    orphan.write_bytes(b"orphaned-mp3")
    os.utime(orphan, (0.0, 0.0))
    (root / "manifest.json").write_text("{truncated", encoding="utf-8")
    cache = SegmentCache(root)

    removed = cache.evict_expired(40 * 86400, audio_ttl_days=30)

    assert removed == 1
    assert not orphan.exists()
