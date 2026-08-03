from dataclasses import replace

from fastapi.testclient import TestClient

import backend.app as appmod
from backend.bailian_cosyvoice_client import BailianCosyVoiceClient
from backend.gptsovits_client import GPTSoVITSClient
from backend.normalizers import normalize_for_tts_en, normalize_for_tts_zh
from backend.segmenters import estimate_duration_en, estimate_duration_zh, split_contract_en, split_contract_zh
from backend.templates import build_template_registry
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


def test_local_engine_only_exposes_cantonese_profile():
    registry = build_template_registry(engine_name="gptsovits")

    assert registry["xcash_yue"].engine_profile.available
    assert not registry["xcash_zh"].engine_profile.available
    assert not registry["xcash_en"].engine_profile.available


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

    assert "貸款" in out
    assert "一千二百五十" in out
    assert "二零二六年八月三日" in out
    assert "一二三四五六" in out


def test_mandarin_segmenter_is_independent_and_has_its_own_duration_rate():
    text = "第一句。第二句！"

    assert [s.text for s in split_contract_zh(text)] == ["第一句。", "第二句！"]
    assert estimate_duration_zh("普通话") != estimate_duration_en("普通话")


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


def test_english_normalizer_reads_dates_amounts_and_identifiers():
    out = normalize_for_tts_en("Pay $1,250 by 2026-08-03. Account AB-1234 is 5.25%.")

    assert "one thousand two hundred fifty dollars" in out
    assert "August third, two thousand twenty six" in out
    assert "five point two five percent" in out
    assert "A B one two three four" in out


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


def test_local_unconfigured_language_profile_returns_503_without_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "cache", appmod.SegmentCache(tmp_path / "cache"))
    monkeypatch.setattr(appmod, "CONTRACT_STORE", appmod.ContractStore(tmp_path / "uploaded"))
    client = TestClient(appmod.app)

    response = client.post(
        "/api/contracts",
        json={"text": "The borrower shall pay.", "template_id": "xcash_en"},
    )

    assert response.status_code == 503
    assert list((tmp_path / "uploaded").glob("*.txt")) == []


def test_make_engine_selects_language_specific_cloud_and_local_settings(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")

    zh_cloud = appmod.make_engine("bailian", "zh")
    en_cloud = appmod.make_engine("bailian", "en")
    zh_local = appmod.make_engine("gptsovits", "zh")

    assert isinstance(zh_cloud, BailianCosyVoiceClient)
    assert isinstance(en_cloud, BailianCosyVoiceClient)
    assert zh_cloud.voice == appmod.BAILIAN_VOICE_ZH
    assert en_cloud.voice == appmod.BAILIAN_VOICE_EN
    assert isinstance(zh_local, GPTSoVITSClient)
    assert zh_local.text_lang == zh_local.prompt_lang == "zh"
