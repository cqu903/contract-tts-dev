import pytest
from seek_probe.backend.contract import build_index, position_to_segment


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
