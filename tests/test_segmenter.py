from backend.segmenter import split_contract, estimate_duration


def test_same_text_yields_identical_segments():
    text = "甲方应于三日内支付。乙方收到后开具收据。"
    assert split_contract(text) == split_contract(text)


def test_splits_on_sentence_end_punctuation():
    segs = split_contract("第一句。第二句！第三句？")
    assert [s.text for s in segs] == ["第一句。", "第二句！", "第三句？"]


def test_long_sentence_is_subsplit_by_clause():
    long = "甲方同意在收到款项后的三个工作日内完成交付，并且保证质量符合约定，否则承担违约责任。"
    segs = split_contract(long, hard_max=20)
    assert len(segs) >= 2
    assert all(s.text for s in segs)


def test_estimate_duration_proportional_to_chars():
    assert estimate_duration("一二三四", rate=4.0) == 1.0
    assert estimate_duration("一二三") > estimate_duration("一")


def test_comma_grouped_number_not_split():
    # ASCII ',' inside a number (126,000) must NOT become a segment boundary;
    # only fullwidth '，' splits clauses. Otherwise amounts read as "126"…/"000".
    long = "甲方須支付港幣126,000元作為訂金，並且在收到貨物後完成驗收程序，否則視為違約。"
    segs = split_contract(long, hard_max=20)
    joined = "".join(s.text for s in segs)
    assert "126,000" in joined                 # number survived intact
    assert not any(s.text.rstrip().endswith("126,") for s in segs)


# --- new: merge short fragments ---


def test_short_clause_fragments_are_merged():
    # A long sentence whose only clause delimiters are 、 would otherwise shatter
    # into 2-3 char crumbs (洽商、追討、…). They must merge back toward `target`.
    text = ("本公司可為考慮任何信貸申請、洽商、追討、收費、信貸、指紋、存款、監管、政府、"
            "稅務、司法、行政、仲裁、權力、寬容、公司、洽商、收費、追討、仲裁。")
    segs = split_contract(text, target=20, soft_max=45)
    lens = [len(s.text) for s in segs]
    assert max(lens) >= 20                      # at least one segment reached ~target
    assert len(segs) <= 6                       # ~20 crumbs collapsed to a few segments
    assert "".join(s.text for s in segs) == text   # round-trip: nothing dropped


def test_merge_never_crosses_sentence_end():
    # Two tiny sentences must stay separate even though merging would fit.
    segs = split_contract("甲乙。丙丁。")
    assert [s.text for s in segs] == ["甲乙。", "丙丁。"]


def test_merge_never_crosses_newline():
    # Newline is a field boundary: short lines must not merge across it.
    text = "第一字段內容甲\n第二字段內容乙\n第三字段內容丙"
    segs = split_contract(text, target=20)
    assert [s.text for s in segs] == ["第一字段內容甲", "第二字段內容乙", "第三字段內容丙"]


# --- new: split over-long blocks ---


def test_overlong_block_splits_on_newline():
    # A >hard_max block with newlines splits into line/field pieces; no \n survives.
    text = ("貸款協議號碼：一二三四五六七八九零\nA. 主要內容\n"
            "1.日期：二零二四年八月\n2.姓名：ZERO FINANCE LIMITED")
    segs = split_contract(text, hard_max=30)
    assert len(segs) >= 2
    assert all("\n" not in s.text for s in segs)   # newline is a boundary, consumed
    assert all(len(s.text) <= 30 for s in segs)
    assert "2.姓名：ZERO FINANCE LIMITED" in [s.text for s in segs]   # field survived intact


def test_overlong_clause_without_newline_splits_on_paren():
    # A >hard_max clause with no newline but fullwidth parens still gets split.
    text = ("每期還款額為從訂立本協議日期（即首次貸款日期）（就第一期而言）或上一期還款日期"
            "（即每個月之二十八日）的累計未付利息（根據利率計算）。")
    segs = split_contract(text, hard_max=30)
    assert len(segs) >= 2
    assert "".join(s.text for s in segs) == text


def test_overlong_form_field_block_splits_on_colon():
    # A >hard_max form-field line (label：value label：value …) with no newline
    # must split on the fullwidth colon so each field is its own seek unit.
    text = "5.借款人姓名：CHAU KA CHUN香港身份證號碼：Y641451地址：FLT 08 BLK 5 TAT YAN BUILDING"
    segs = split_contract(text, hard_max=30)
    assert len(segs) >= 2
    assert all(len(s.text) <= 45 for s in segs)


def test_stray_conjunction_or_bracket_is_absorbed():
    # A lone 和/及/或 (stranded on its own line between list items) or a stray
    # ］ (stranded after a period) must fold into a neighbor, not survive as a
    # 1-char segment.
    text = "等待進行中；\n和\n借款人沒有開展破產行動。如本協議存在分歧。\n］\n本金可變動。"
    segs = split_contract(text)
    assert all(len(s.text) > 2 for s in segs), [s.text for s in segs if len(s.text) <= 2]
    assert "和" not in [s.text for s in segs]
    assert "］" not in [s.text for s in segs]
