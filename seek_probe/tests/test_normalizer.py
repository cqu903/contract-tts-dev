from seek_probe.backend.normalizer import normalize_for_tts


def test_amount_with_commas():
    # the reported bug: 2,864,000 was read as "28640"
    assert normalize_for_tts("港幣2,864,000元") == "港幣二百八十六万四千元"


def test_large_amount():
    assert normalize_for_tts("港幣3,580,000元") == "港幣三百五十八万元"


def test_quantity():
    assert normalize_for_tts("數量共12,000件") == "數量共一万二千件"


def test_percentage_decimal():
    assert normalize_for_tts("年利率5.25%") == "年利率百分之五點二五"


def test_percentage_small_decimal():
    assert normalize_for_tts("0.5%") == "百分之零點五"


def test_whole_percentage():
    assert normalize_for_tts("累計不超過10%") == "累計不超過百分之十"


def test_full_date():
    assert normalize_for_tts("2026年8月1日") == "二零二六年八月一日"


def test_date_double_digit_day():
    assert normalize_for_tts("2026年8月15日") == "二零二六年八月十五日"


def test_duration_hours():
    assert normalize_for_tts("48小時") == "四十八小時"


def test_duration_months():
    assert normalize_for_tts("12個月") == "十二個月"


def test_already_chinese_unchanged():
    assert normalize_for_tts("百分之二十") == "百分之二十"
    assert normalize_for_tts("叁佰伍拾捌萬元整") == "叁佰伍拾捌萬元整"
