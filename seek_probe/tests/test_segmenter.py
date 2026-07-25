from seek_probe.backend.segmenter import split_contract, estimate_duration


def test_same_text_yields_identical_segments():
    text = "甲方应于三日内支付。乙方收到后开具收据。"
    assert split_contract(text) == split_contract(text)


def test_splits_on_sentence_end_punctuation():
    segs = split_contract("第一句。第二句！第三句？")
    assert [s.text for s in segs] == ["第一句。", "第二句！", "第三句？"]


def test_long_sentence_is_subsplit_by_clause():
    long = "甲方同意在收到款项后的三个工作日内完成交付，并且保证质量符合约定，否则承担违约责任。"
    segs = split_contract(long, max_chars=20)
    assert len(segs) >= 2
    assert all(s.text for s in segs)


def test_estimate_duration_proportional_to_chars():
    assert estimate_duration("一二三四", rate=4.0) == 1.0
    assert estimate_duration("一二三") > estimate_duration("一")
