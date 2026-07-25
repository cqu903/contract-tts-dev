from seek_probe.backend.cache import cache_key, SegmentCache


def test_key_stable_for_same_text_and_voice_distinct_otherwise():
    assert cache_key("你好", "vA") == cache_key("你好", "vA")
    assert cache_key("你好", "vA") != cache_key("你好", "vB")   # different voice
    assert cache_key("你好", "vA") != cache_key("再见", "vA")   # different text


def test_put_then_get_roundtrip(tmp_path):
    c = SegmentCache(tmp_path / "cache")
    key = cache_key("x", "v")
    assert c.get(key) is None
    p = c.put(key, b"RIFFxxxx", duration=1.5)
    assert c.has(key)
    got = c.get(key)
    assert got is not None and got.read_bytes() == b"RIFFxxxx"
