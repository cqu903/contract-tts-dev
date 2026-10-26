from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import backend.app as appmod
from backend.audio import AudioFormat
from backend.bailian_cosyvoice_client import BailianCosyVoiceClient
from backend.gptsovits_client import GPTSoVITSClient
from backend.engines.microsoft_tts import MicrosoftTTSProvider
from backend.normalizers import normalize_for_tts_en, normalize_for_tts_zh
from backend.segmenter import split_contract
from backend.segmenters import (
    estimate_duration_en,
    estimate_duration_zh,
    split_contract_en,
    split_contract_zh,
)
from backend.templates import build_template_registry, canonical_engine_name
from tests.test_app import FakeEngine


def _enable_profile(monkeypatch, template_id, engine):
    profile = appmod.TEMPLATE_REGISTRY[template_id]
    enabled = replace(
        profile,
        engine_profile=replace(
            profile.engine_profile,
            available=True,
            engine_provider=lambda: engine,
        ),
    )
    monkeypatch.setitem(appmod.TEMPLATE_REGISTRY, template_id, enabled)


def test_bailian_registry_exposes_three_available_language_profiles():
    registry = build_template_registry(engine_name="bailian", api_key="sk-test")

    assert set(registry) == {"xcash_yue", "xcash_zh", "xcash_en"}
    assert all(profile.engine_profile.available for profile in registry.values())
    assert registry["xcash_yue"].engine_profile.id == "bailian_yue"
    assert registry["xcash_zh"].engine_profile.id == "bailian_zh"
    assert registry["xcash_en"].engine_profile.id == "bailian_en"


def test_local_engine_exposes_all_three_language_profiles():
    registry = build_template_registry(engine_name="gptsovits")

    assert all(profile.engine_profile.available for profile in registry.values())
    assert registry["xcash_yue"].engine_profile.id == "gptsovits_yue"
    assert registry["xcash_zh"].engine_profile.id == "gptsovits_zh"
    assert registry["xcash_en"].engine_profile.id == "gptsovits_en"


def test_registry_selects_engine_and_availability_per_language():
    registry = build_template_registry(
        engine_name="gptsovits",
        engine_names={
            "yue": "gptsovits",
            "zh": "cosyvoice",
            "en": "gptsovits",
        },
        api_key="",
    )

    assert registry["xcash_yue"].engine_profile.id == "gptsovits_yue"
    assert registry["xcash_zh"].engine_profile.id == "bailian_zh"
    assert registry["xcash_en"].engine_profile.id == "gptsovits_en"
    assert registry["xcash_yue"].engine_profile.available
    assert not registry["xcash_zh"].engine_profile.available
    assert registry["xcash_en"].engine_profile.available


def test_registry_enables_only_configured_cosyvoice_profiles_when_key_exists():
    registry = build_template_registry(
        engine_name="bailian",
        engine_names={"yue": "gptsovits", "zh": "bailian", "en": "cosyvoice"},
        api_key="sk-test",
    )

    assert all(profile.engine_profile.available for profile in registry.values())
    assert registry["xcash_yue"].engine_profile.id == "gptsovits_yue"
    assert registry["xcash_zh"].engine_profile.id == "bailian_zh"
    assert registry["xcash_en"].engine_profile.id == "bailian_en"


def test_registry_rejects_unknown_engine_names():
    with pytest.raises(ValueError, match="unsupported TTS engine"):
        build_template_registry(
            engine_name="gptsovits",
            engine_names={"zh": "not-an-engine"},
        )


def test_microsoft_is_a_canonical_engine_provider_for_cantonese():
    assert canonical_engine_name(" microsoft ") == "microsoft"

    registry = build_template_registry(
        engine_name="gptsovits",
        engine_names={"yue": "microsoft"},
        synthesis_fingerprints={"yue": "edge|voice=test|rate=+0%|format=mp3|adapter=v1"},
    )

    yue = registry["xcash_yue"].engine_profile
    assert yue.id == "microsoft_yue"
    assert yue.available
    assert yue.synthesis_fingerprint == (
        "edge|voice=test|rate=+0%|format=mp3|adapter=v1"
    )


def test_global_microsoft_enables_all_language_profiles_without_bailian_key():
    registry = build_template_registry(engine_name="microsoft", api_key="")

    assert all(profile.engine_profile.available for profile in registry.values())
    assert registry["xcash_yue"].engine_profile.id == "microsoft_yue"
    assert registry["xcash_zh"].engine_profile.id == "microsoft_zh"
    assert registry["xcash_en"].engine_profile.id == "microsoft_en"


def test_profiles_have_independently_configurable_cache_versions():
    registry = build_template_registry(
        engine_name="bailian",
        api_key="sk-test",
        cache_versions={"yue": "v2", "zh": "v3", "en": "v4"},
    )

    assert registry["xcash_yue"].engine_profile.cache_version == "v2"
    assert registry["xcash_zh"].engine_profile.cache_version == "v3"
    assert registry["xcash_en"].engine_profile.cache_version == "v4"


def test_mandarin_normalizer_preserves_traditional_text_and_normalizes_numbers():
    out = normalize_for_tts_zh("貸款金額 1,250 元，日期 2026年8月3日，編號 123456。")

    assert "貸款金額" in out
    assert "一千二百五十" in out
    assert "二零二六年八月三日" in out
    assert "一二三四五六" in out


def test_mandarin_normalizer_keeps_english_address_as_spoken_words():
    source = (
        "FLT 6 15/F BLK 5 CHEONG YAT HOUSE 3 CHEONG SAN LANE "
        "SHAM SHUI PO KOWLOON"
    )

    assert normalize_for_tts_zh(source) == (
        "Flat 6 15th Floor Block 5 Cheong Yat House 3 Cheong San Lane "
        "Sham Shui Po Kowloon"
    )


def test_mandarin_english_address_rules_generalize_and_preserve_chinese_values():
    assert normalize_for_tts_zh(
        "RM 8 21/F BLK 2 HARBOUR VIEW TWR 9 QUEEN'S RD CENTRAL"
    ) == (
        "Room 8 21st Floor Block 2 Harbour View Tower 9 Queen's Road Central"
    )
    assert normalize_for_tts_zh("HKD 5,000") == "港币五千"
    assert normalize_for_tts_zh("AB-1234") == "AB-一二三四"


def test_mandarin_address_remains_english_after_long_line_segmentation():
    source = (
        "FLT 6 15/F BLK 5 CHEONG YAT HOUSE 3 CHEONG SAN LANE "
        "SHAM SHUI PO KOWLOON"
    )

    spoken = " ".join(
        normalize_for_tts_zh(segment.text) for segment in split_contract_zh(source)
    )

    assert spoken == (
        "Flat 6 15th Floor Block 5 Cheong Yat House 3 Cheong San Lane "
        "Sham Shui Po Kowloon"
    )


def test_mandarin_segmenter_is_independent_and_has_its_own_duration_rate():
    text = "第一句。第二句！"

    assert [s.text for s in split_contract_zh(text)] == ["第一句。", "第二句！"]
    assert estimate_duration_zh("普通话") != estimate_duration_en("普通话")


def test_mandarin_segmenter_has_its_own_bracket_and_hard_limit_rules():
    text = "甲" * 30 + "（" + "乙" * 25 + "）。\n第二行。"

    mandarin = split_contract_zh(text, target=12, soft_max=24, hard_max=30)
    cantonese = split_contract(text, target=12, soft_max=24, hard_max=30)

    assert [len(segment.text) for segment in mandarin] == [30, 28, 4]
    assert mandarin[1].text.startswith("（")
    assert cantonese[0].text.endswith("（")
    assert [segment.text for segment in mandarin] != [segment.text for segment in cantonese]


def test_mandarin_segmenter_bounds_unpunctuated_text_and_keeps_ascii_ids_whole():
    unpunctuated = "甲" * 130 + "。"
    identifier = "條款前文" + "ACCOUNT-1234567890" + "條款後文" * 8 + "。"

    bounded = split_contract_zh(unpunctuated)
    with_identifier = split_contract_zh(
        identifier,
        target=12,
        soft_max=24,
        hard_max=30,
    )

    assert max(len(segment.text) for segment in bounded) <= 54
    assert any("ACCOUNT-1234567890" in segment.text for segment in with_identifier)


def test_mandarin_segmenter_repairs_connectors_labels_and_punctuation_fragments():
    text = "第一項；\n和\n第二項。\n地址：\n香港中環。\n4.\n資料收集"

    segments = [segment.text for segment in split_contract_zh(text)]

    assert segments == ["第一項；", "和第二項。", "地址：香港中環。", "4.資料收集"]
    assert not any(segment in {"和", "及", "或", "以及", "。"} for segment in segments)


def test_english_segmenter_keeps_words_whole():
    segments = split_contract_en(
        "The borrower shall pay the amount. The lender may terminate the agreement.",
        hard_max=30,
    )

    assert [segment.text for segment in segments] == [
        "The borrower shall pay the",
        "amount.",
        "The lender may terminate the",
        "agreement.",
    ]


def test_english_segmenter_honors_target_soft_max_and_newline_boundaries():
    segments = split_contract_en(
        "One short sentence. Two short sentence.\nA separate line stays separate.",
        target=25,
        soft_max=40,
        hard_max=50,
    )

    assert [segment.text for segment in segments] == [
        "One short sentence. Two short sentence.",
        "A separate line stays separate.",
    ]
    assert all(len(segment.text) <= 40 for segment in segments)


def test_english_segmenter_attaches_standalone_list_markers_to_their_text():
    segments = split_contract_en(
        "(a)\nBorrower shall pay.\n(ii)\nPayment is due."
    )

    assert [segment.text for segment in segments] == [
        "(a) Borrower shall pay.",
        "(ii) Payment is due.",
    ]


def test_mandarin_segmenter_attaches_standalone_list_markers_to_their_text():
    segments = split_contract_zh("（ii）\n借款人应付款。\n(A)\n其他条款。")

    assert [segment.text for segment in segments] == [
        "（ii）借款人应付款。",
        "(A)其他条款。",
    ]


def test_english_normalizer_reads_dates_amounts_and_identifiers():
    out = normalize_for_tts_en("Pay $1,250 by 2026-08-03. Account AB-1234 is 5.25%.")

    assert "one thousand two hundred fifty dollars" in out
    assert "August third, two thousand twenty six" in out
    assert "five point two five percent" in out
    assert "A B one two three four" in out


def test_english_profile_reads_day_month_year_date_before_slash_identifiers():
    source = "The agreement date is 30/07/2026."

    segments = split_contract_en(source)
    spoken = " ".join(normalize_for_tts_en(segment.text) for segment in segments)

    assert [segment.text for segment in segments] == [source]
    assert spoken == "The agreement date is July thirtieth, two thousand twenty six."
    assert normalize_for_tts_en("Reference 0954/2024.") == (
        "Reference zero nine five four two zero two four."
    )


def test_english_normalizer_expands_address_words_instead_of_spelling_letters():
    source = "Address:FLT 410 21/F WANG FOOK COURT 76981363 KOWLOON CITY KOWLOON"

    assert normalize_for_tts_en(source) == (
        "Address:Flat four hundred ten twenty first floor Wang Fook Court "
        "seven six nine eight one three six three Kowloon City Kowloon"
    )
    assert "Queen's Road" in normalize_for_tts_en(
        "ROOM 2110-11, 21/F, COSCO TOWER, 183 QUEEN'S RD CENTRAL"
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Due 30 July 2026.", "Due July thirtieth, two thousand twenty six."),
        ("Due 30th July 2026.", "Due July thirtieth, two thousand twenty six."),
        ("Due July 30, 2026.", "Due July thirtieth, two thousand twenty six."),
        ("Due 30-07-2026.", "Due July thirtieth, two thousand twenty six."),
        ("Due 1/1/2027.", "Due January first, two thousand twenty seven."),
        (
            "Due 29/02/2028.",
            "Due February twenty ninth, two thousand twenty eight.",
        ),
        ("At 10:00.", "At ten o'clock."),
        ("At 9:05.", "At nine oh five."),
        ("At 23:31.", "At twenty three thirty one."),
        (
            "Pay HK$1,250.00.",
            "Pay one thousand two hundred fifty Hong Kong dollars.",
        ),
        (
            "Pay HKD 1.50.",
            "Pay one Hong Kong dollar and fifty cents.",
        ),
        (
            "Rate HK$1.234.",
            "Rate one point two three four Hong Kong dollars.",
        ),
        ("Pay $2.05.", "Pay two dollars and five cents."),
        ("Office 39/F.", "Office thirty ninth floor."),
        ("(a) Borrower", "item A, Borrower"),
        ("(ii) Payment", "item I I, Payment"),
        (
            "Terms: (a) first; (ii) second",
            "Terms: item A, first; item I I, second",
        ),
        ("The account(s) remain open.", "The account(s) remain open."),
    ],
)
def test_english_normalizer_handles_general_contract_formats(source, expected):
    assert normalize_for_tts_en(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("$5,000", "港币五千"),
        ("港幣$5,000.00", "港币五千"),
        ("地址39/F", "地址三十九楼"),
        ("第III部", "第三部"),
        ("（ii）付款", "第I I项，付款"),
        ("包括：（a）甲；（ii）乙", "包括：第A项，甲；第I I项，乙"),
        ("2026-07-30", "二零二六年七月三十日"),
        ("30-07-2026", "二零二六年七月三十日"),
        ("1/1/2027", "二零二七年一月一日"),
        ("29/02/2028", "二零二八年二月二十九日"),
    ],
)
def test_mandarin_normalizer_handles_general_contract_formats(source, expected):
    assert normalize_for_tts_zh(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "訂立本協議/作出貸款日期：08/06/2026",
            "訂立本協議或作出貸款日期：二零二六年六月八日",
        ),
        ("貸款人及/或代理人", "貸款人及或代理人"),
        ("本人／吾等", "本人或吾等"),
        ("本人∕吾等", "本人或吾等"),
    ],
)
def test_mandarin_normalizer_speaks_cjk_slashes_by_context(source, expected):
    assert normalize_for_tts_zh(source) == expected


def test_invalid_numeric_date_is_not_rendered_as_a_mandarin_date():
    assert "年" not in normalize_for_tts_zh("31-02-2026")


def test_invalid_numeric_date_is_not_rendered_as_an_english_date():
    assert "February" not in normalize_for_tts_en("31/02/2026")


def test_language_normalizers_read_identifiers_and_units_without_rewriting_source():
    zh = normalize_for_tts_zh("合同编号 AB-1234，电话 138-0013-8000，时间 9:30。")
    en = normalize_for_tts_en(
        "Call 138-0013-8000. Refs AB12CD34 and A1-B2-C3. Weight 5kg or 1 lb."
    )

    assert "AB-一二三四" in zh
    assert "一三八零零一三八零零零" in zh
    assert "九点三十分" in zh
    assert "one three eight zero zero one three eight zero zero zero" in en
    assert "A B one two C D three four" in en
    assert "A one B two C three" in en
    assert "five kilograms" in en
    assert "one pound" in en


def test_identity_card_check_digit_is_not_misread_as_a_list_item():
    zh = normalize_for_tts_zh("香港身份證號碼：Z657587(1) 地址")
    en = normalize_for_tts_en("Hong Kong Identity Card No. M698604(3)")

    assert zh == "香港身份證號碼：Z六五七五八七一 地址"
    assert en == (
        "Hong Kong Identity Card No. M six nine eight six zero four three"
    )
    assert "第" not in zh
    assert "item" not in en.lower()


def test_mandarin_api_uses_its_profile_and_isolated_contract_id(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "cache", appmod.SegmentCache(tmp_path / "cache"))
    monkeypatch.setattr(appmod, "CONTRACT_STORE", appmod.ContractStore(tmp_path / "uploaded"))
    yue_engine = FakeEngine()
    zh_engine = FakeEngine()
    monkeypatch.setattr(appmod, "engine", yue_engine)
    _enable_profile(monkeypatch, "xcash_zh", zh_engine)
    client = TestClient(appmod.app)

    source = "同一份繁體合同 123456。"
    yue = client.post("/api/contracts", json={"text": source, "template_id": "xcash_yue"})
    zh = client.post("/api/contracts", json={"text": source, "template_id": "xcash_zh"})

    assert yue.status_code == 200 and zh.status_code == 200
    assert yue.json()["contract_id"] != zh.json()["contract_id"]
    assert appmod.CONTRACT_STORE.get(zh.json()["contract_id"]) == source
    assert yue_engine.calls == 1
    assert zh_engine.calls == 1
    assert "繁體合同" in yue_engine.texts[0]
    assert "繁體合同" in zh_engine.texts[0]


def test_english_api_uses_its_profile_and_isolated_contract_id(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "cache", appmod.SegmentCache(tmp_path / "cache"))
    monkeypatch.setattr(appmod, "CONTRACT_STORE", appmod.ContractStore(tmp_path / "uploaded"))
    en_engine = FakeEngine()
    _enable_profile(monkeypatch, "xcash_en", en_engine)
    client = TestClient(appmod.app)

    english = client.post(
        "/api/contracts",
        json={"text": "The borrower 零金融 shall pay the amount.", "template_id": "xcash_en"},
    )
    cantonese = client.post(
        "/api/contracts",
        json={"text": "The borrower 零金融 shall pay the amount.", "template_id": "xcash_yue"},
    )

    assert english.status_code == 200 and cantonese.status_code == 200
    assert english.json()["contract_id"] != cantonese.json()["contract_id"]
    assert en_engine.calls == 1


def test_local_english_profile_uploads_and_uses_selected_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "cache", appmod.SegmentCache(tmp_path / "cache"))
    monkeypatch.setattr(appmod, "CONTRACT_STORE", appmod.ContractStore(tmp_path / "uploaded"))
    engine = FakeEngine()
    _enable_profile(monkeypatch, "xcash_en", engine)
    client = TestClient(appmod.app)

    response = client.post(
        "/api/contracts",
        json={"text": "The borrower shall pay.", "template_id": "xcash_en"},
    )

    assert response.status_code == 200
    assert response.json()["template_id"] == "xcash_en"
    assert engine.calls == 1


def test_make_engine_selects_language_specific_cloud_and_local_settings(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")

    zh_cloud = appmod.make_engine("bailian", "zh")
    en_cloud = appmod.make_engine("bailian", "en")
    zh_local = appmod.make_engine("gptsovits", "zh")

    assert isinstance(zh_cloud, BailianCosyVoiceClient)
    assert isinstance(en_cloud, BailianCosyVoiceClient)
    assert zh_cloud.voice == appmod.BAILIAN_VOICE_ZH
    assert en_cloud.voice == appmod.BAILIAN_VOICE_EN
    assert zh_cloud.text_lang == "zh"
    assert en_cloud.text_lang == "en"
    assert isinstance(zh_local, GPTSoVITSClient)
    assert zh_local.text_lang == "zh"
    assert zh_local.prompt_lang == "yue"


def test_make_engine_builds_cantonese_microsoft_provider_from_server_config(
    monkeypatch,
):
    monkeypatch.setattr(appmod, "MICROSOFT_TTS_DRIVER", "edge")
    monkeypatch.setitem(
        appmod.MICROSOFT_TTS_LANGUAGE_CONFIGS,
        "yue",
        appmod.MicrosoftReadingLanguageConfig(
            voice="zh-HK-HiuMaanNeural", rate="15%"
        ),
    )

    selected = appmod.make_engine("microsoft", "yue")

    assert isinstance(selected, MicrosoftTTSProvider)
    assert selected.driver.voice == "zh-HK-HiuMaanNeural"
    assert selected.driver.rate == "+15%"
    assert selected.audio_format is AudioFormat.MP3


@pytest.mark.parametrize(
    ("reading_language", "expected_voice"),
    [
        ("yue", "zh-HK-WanLungNeural"),
        ("zh", "zh-CN-YunyangNeural"),
        ("en", "en-HK-SamNeural"),
    ],
)
def test_make_engine_builds_each_microsoft_language_with_contract_defaults(
    monkeypatch, reading_language, expected_voice
):
    monkeypatch.setattr(appmod, "MICROSOFT_TTS_DRIVER", "edge")
    monkeypatch.setitem(
        appmod.MICROSOFT_TTS_LANGUAGE_CONFIGS,
        reading_language,
        appmod.MicrosoftReadingLanguageConfig(expected_voice, "+0%"),
    )

    selected = appmod.make_engine("microsoft", reading_language)

    assert isinstance(selected, MicrosoftTTSProvider)
    assert selected.driver.voice == expected_voice
    assert selected.driver.rate == "+0%"
    assert selected.audio_format is AudioFormat.MP3


def test_configured_engines_support_a_three_provider_language_mix(monkeypatch):
    monkeypatch.setattr(appmod, "MICROSOFT_TTS_DRIVER", "edge")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setitem(
        appmod.MICROSOFT_TTS_LANGUAGE_CONFIGS,
        "yue",
        appmod.MicrosoftReadingLanguageConfig(
            "zh-HK-WanLungNeural", "+0%"
        ),
    )

    configured = appmod.build_configured_engines(
        {"yue": "microsoft", "zh": "gptsovits", "en": "cosyvoice"}
    )

    assert isinstance(configured["yue"], MicrosoftTTSProvider)
    assert configured["yue"].driver.voice == "zh-HK-WanLungNeural"
    assert isinstance(configured["zh"], GPTSoVITSClient)
    assert configured["zh"].text_lang == "zh"
    assert isinstance(configured["en"], BailianCosyVoiceClient)
    assert configured["en"].text_lang == "en"


def test_microsoft_voice_and_rate_overrides_are_isolated_by_language(monkeypatch):
    monkeypatch.setattr(appmod, "MICROSOFT_TTS_DRIVER", "edge")
    overrides = {
        "yue": appmod.MicrosoftReadingLanguageConfig("yue-voice", "5%"),
        "zh": appmod.MicrosoftReadingLanguageConfig("zh-voice", "-10%"),
        "en": appmod.MicrosoftReadingLanguageConfig("en-voice", "+20%"),
    }
    for language, config in overrides.items():
        monkeypatch.setitem(
            appmod.MICROSOFT_TTS_LANGUAGE_CONFIGS, language, config
        )

    configured = appmod.build_configured_engines(
        {"yue": "microsoft", "zh": "microsoft", "en": "microsoft"}
    )

    assert {
        language: (provider.driver.voice, provider.driver.rate)
        for language, provider in configured.items()
    } == {
        "yue": ("yue-voice", "+5%"),
        "zh": ("zh-voice", "-10%"),
        "en": ("en-voice", "+20%"),
    }


@pytest.mark.parametrize(
    ("reading_language", "config_field", "configured_value", "error"),
    [
        ("zh", "driver", "", "must be explicitly configured"),
        ("en", "driver", "sapi", "unsupported Microsoft"),
        ("en", "driver", "azure", "AZURE_SPEECH_KEY"),
        ("yue", "voice", "", "voice must not be empty"),
        ("zh", "rate", "fast", "integer percentage"),
        ("en", "rate", "+ 5%", "integer percentage"),
    ],
)
def test_each_selected_microsoft_profile_is_validated_locally(
    monkeypatch, reading_language, config_field, configured_value, error
):
    monkeypatch.setattr(appmod, "MICROSOFT_TTS_DRIVER", "edge")
    monkeypatch.setattr(appmod, "AZURE_SPEECH_KEY", "", raising=False)
    monkeypatch.setattr(appmod, "AZURE_SPEECH_REGION", "", raising=False)
    monkeypatch.setattr(appmod, "AZURE_SPEECH_ENDPOINT", "", raising=False)
    if config_field == "driver":
        monkeypatch.setattr(appmod, "MICROSOFT_TTS_DRIVER", configured_value)
    else:
        current = appmod.MICROSOFT_TTS_LANGUAGE_CONFIGS[reading_language]
        monkeypatch.setitem(
            appmod.MICROSOFT_TTS_LANGUAGE_CONFIGS,
            reading_language,
            replace(current, **{config_field: configured_value}),
        )
    selected = {"yue": "gptsovits", "zh": "gptsovits", "en": "gptsovits"}
    selected[reading_language] = "microsoft"

    with pytest.raises(ValueError, match=error):
        appmod.build_configured_engines(selected)


def test_unselected_microsoft_configuration_does_not_change_existing_defaults(
    monkeypatch,
):
    monkeypatch.setattr(appmod, "MICROSOFT_TTS_DRIVER", "")
    monkeypatch.setitem(
        appmod.MICROSOFT_TTS_LANGUAGE_CONFIGS,
        "yue",
        appmod.MicrosoftReadingLanguageConfig("", "+0%"),
    )
    monkeypatch.setitem(
        appmod.MICROSOFT_TTS_LANGUAGE_CONFIGS,
        "zh",
        appmod.MicrosoftReadingLanguageConfig("zh-voice", "invalid"),
    )

    configured = appmod.build_configured_engines(
        {"yue": "gptsovits", "zh": "gptsovits", "en": "gptsovits"}
    )

    assert all(
        isinstance(engine, GPTSoVITSClient) for engine in configured.values()
    )
