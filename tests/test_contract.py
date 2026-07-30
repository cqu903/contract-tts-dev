import pytest
from backend.contract import build_index, dump_segments, position_to_segment, ContractStore


def test_index_cumulative_starts_monotonic_and_total_matches():
    idx = build_index("c", "第一句。第二句！")
    starts = [m.cumulative_start_s for m in idx.segments]
    assert starts[0] == 0.0
    assert starts == sorted(starts)
    assert idx.total_est_s == pytest.approx(sum(m.est_dur_s for m in idx.segments))


def test_position_to_segment_bounds_and_boundary():
    idx = build_index("c", "甲。乙。丙。")
    assert position_to_segment(idx, 0.0) == 0
    # boundary at end of segment 0 belongs to segment 1
    end0 = idx.segments[0].cumulative_start_s + idx.segments[0].est_dur_s
    assert position_to_segment(idx, end0) == 1
    # beyond end clamps to last segment
    assert position_to_segment(idx, idx.total_est_s + 99) == len(idx.segments) - 1
    # negative clamps to 0
    assert position_to_segment(idx, -5) == 0


def test_dump_segments_verbatim(tmp_path):
    idx = build_index("c", "第一句。第二句！")
    out = dump_segments(idx, tmp_path / "c.segments.txt")
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# c: 2 segments")
    # every segment text appears verbatim, one per line, in order
    assert [line.split(") ", 1)[1] for line in lines[1:]] == [m.text for m in idx.segments]


def test_contract_store_evict_removes_old_originals(tmp_path):
    store = ContractStore(tmp_path / "uploaded")
    store.put("old", "原文甲", now=0.0)
    store.put("new", "原文乙", now=100 * 86400)   # day 100
    # evict at day 100, text_ttl_days=90 → cutoff = day 10：
    # old（创建于 day 0）已过期淘汰；new（创建于 day 100）保留
    removed = store.evict_expired(100 * 86400, text_ttl_days=90)
    assert removed == 1
    assert store.get("old") is None
    assert store.get("new") == "原文乙"
