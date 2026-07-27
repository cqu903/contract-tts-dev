from seek_probe.backend.normalizer import normalize_for_tts


def test_amount_with_commas():
    # the reported bug: 2,864,000 was read as "28640"
    assert normalize_for_tts("港幣2,864,000元") == "港幣二百八十六万四千元"


def test_large_amount():
    assert normalize_for_tts("港幣3,580,000元") == "港幣三百五十八万元"


def test_quantity():
    assert normalize_for_tts("數量共12,000件") == "數量共一万二千件"


def test_model_number_read_digit_by_digit():
    # codes read digit-by-digit, not as a quantity
    assert normalize_for_tts("型號為XR-7200") == "型號為XR-七二零零"
    assert normalize_for_tts("採用A100晶片") == "採用A一零零晶片"


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


def test_long_reference_number_digit_by_digit():
    # 19-digit loan-agreement number exceeds cn2an's 16-digit range -> digit-by-digit,
    # not a crash and not a (meaningless) cardinal reading.
    assert normalize_for_tts("貸款協議號碼 : 1279857891713384448") == \
        "貸款協議號碼 ： 一二七九八五七八九一七一三三八四四四八"


def test_clause_number_not_decimal():
    # "1." is a clause marker, not the decimal 1.0 -> 一 (period left in place)
    assert normalize_for_tts("1.訂立本協議") == "一.訂立本協議"
    assert "點" not in normalize_for_tts("9.年利率：47%")


def test_currency_decimal_zeros_dropped():
    # ".00" is zero cents -> drop the decimal, not read as 點零零
    assert normalize_for_tts("HK$126,000.00") == "港幣十二万六千"


def test_slash_date_dmy():
    # HK/EU date D/M/YYYY -> year digit-by-digit, not cardinal 二千零二十四
    assert normalize_for_tts("28/08/2024") == "二零二四年八月二十八日"


def test_hkd_symbol_to_yuen():
    # $ / HK$ -> 港幣; avoid doubling when 港幣 already precedes $
    assert normalize_for_tts("HK$126,000") == "港幣十二万六千"
    assert normalize_for_tts("港幣$5,000") == "港幣五千"


def test_phone_read_digit_by_digit():
    # bare 8-digit phone -> digit-by-digit, not the cardinal 二千五百三十一万…
    assert normalize_for_tts("電話25310333") == "電話二五三一零三三三"


def test_bank_account_hyphen_code():
    assert normalize_for_tts("024-363-529959882") == "零二四三六三五二九九五九八八二"


def test_licence_slash_code():
    # 0954/2024 is a licence (one slash, 4/4 digits), NOT a D/M/YYYY date -> digit-by-digit
    assert normalize_for_tts("牌照0954/2024") == "牌照零九五四二零二四"


def test_bare_reference_code():
    assert normalize_for_tts("協議202211") == "協議二零二二一一"


def test_time_hhmm():
    assert normalize_for_tts("23:31") == "二十三時三十一分"


def test_currency_amount_not_digit_by_digit():
    # $1000000 has no commas but is currency-prefixed -> stays cardinal 一百万
    assert normalize_for_tts("$1000000") == "港幣一百万"


def test_slash_date_vs_slash_code():
    assert normalize_for_tts("28/08/2024") == "二零二四年八月二十八日"   # date
    assert normalize_for_tts("0954/2024") == "零九五四二零二四"          # code


def test_control_char_stripped():
    assert "\x14" not in normalize_for_tts("A\x14B")
    assert normalize_for_tts("A\x14B") == "AB"


def test_ascii_punct_to_fullwidth():
    assert normalize_for_tts("(如有)") == "（如有）"


# --- address lexicon + roman numerals (general, no per-contract data) ---


def test_address_words_and_districts_translated():
    out = normalize_for_tts("FLT 08 39/F BLK 5 TAT YAN BUILDING PO TAT ESTATE KWUN TONG KOWLOON")
    assert "觀塘" in out and "九龍" in out          # districts
    assert "室" in out and "座" in out             # FLT->室, BLK->座
    assert "大廈" in out and "屋邨" in out         # BUILDING->大廈, ESTATE->屋邨
    assert "三十九樓" in out                       # 39/F -> floor
    # the structural English is gone; specific unknown names (TAT YAN, PO TAT) stay
    assert "FLT" not in out and "BLK" not in out and "BUILDING" not in out and "ESTATE" not in out


def test_floor_indicator_to_chinese():
    assert normalize_for_tts("39/F") == "三十九樓"


def test_roman_list_markers_to_chinese():
    assert "（二）" in normalize_for_tts("（ii）財務服務")
    assert "（三）" in normalize_for_tts("（iii）信貸")
    assert "（四）" in normalize_for_tts("（iv）放債人")


def test_ordinal_roman_after_di_to_chinese():
    # 第III部 / 第IV部 are Part references (ordinals), not list markers
    assert "第三部" in normalize_for_tts("《放債人條例》第III部撮要")
    assert "第四部" in normalize_for_tts("第IV部條文")
    assert "第三及第四部" in normalize_for_tts("第III及第IV部條文的撮要")


def test_company_name_kept_english():
    # names are left to the model's English pronunciation; lexicon must not touch them
    out = normalize_for_tts("由ZERO FINANCE HONG KONG LIMITED提供")
    assert "ZERO FINANCE HONG KONG LIMITED" in out
