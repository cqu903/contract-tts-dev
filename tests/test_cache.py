from backend.cache import cache_key, SegmentCache


def test_key_stable_for_same_text_voice_engine_distinct_otherwise():
    assert cache_key("你好", "vA", "e1") == cache_key("你好", "vA", "e1")
    assert cache_key("你好", "vA", "e1") != cache_key("你好", "vA", "e2")   # different engine
    assert cache_key("你好", "vA", "e1") != cache_key("你好", "vB", "e1")   # different voice
    assert cache_key("你好", "vA", "e1") != cache_key("再见", "vA", "e1")   # different text


def test_put_then_get_roundtrip_and_access_refresh(tmp_path):
    c = SegmentCache(tmp_path / "cache")
    key = cache_key("x", "v", "e")
    assert c.get(key) is None
    c.put(key, b"RIFFxxxx", duration=1.5, now=1000.0)
    assert c.has(key)
    got = c.get(key, now=2000.0)
    assert got is not None and got.read_bytes() == b"RIFFxxxx"
    # hit refreshed last_access_at; created_at is preserved
    assert c._manifest[key]["last_access_at"] == 2000.0
    assert c._manifest[key]["created_at"] == 1000.0


def test_evict_removes_entries_not_hit_within_window(tmp_path):
    c = SegmentCache(tmp_path / "cache")
    cold = cache_key("cold", "v", "e")
    hot = cache_key("hot", "v", "e")
    c.put(cold, b"a", now=0.0)
    c.put(hot, b"b", now=0.0)
    c.get(hot, now=40 * 86400)          # hot hit at day 40
    # now = day 50: cold last hit day 0 (>30d ago) → evicted; hot last hit day 40 (<30d) → kept
    removed = c.evict_expired(50 * 86400, audio_ttl_days=30)
    assert removed == 1
    assert not c.has(cold)
    assert c.has(hot)
