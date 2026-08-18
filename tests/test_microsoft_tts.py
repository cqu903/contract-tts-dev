import asyncio
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import backend.app as appmod
from backend.audio import AudioFormat
from backend.cache import SegmentCache
from backend.contract import ContractStore
from backend.engines.microsoft_tts import (
    EdgeTTSDriver,
    MicrosoftSynthesisError,
    MicrosoftTTSProvider,
    build_microsoft_provider,
    normalize_edge_rate,
)
from backend.templates import build_template_registry
from tests.test_app import FakeEngine


async def _collect(stream):
    return b"".join([chunk async for chunk in stream])


class FakeCommunicate:
    def __init__(self, events=None, error=None):
        self.events = events or []
        self.error = error

    async def stream(self):
        for event in self.events:
            yield event
        if self.error is not None:
            raise self.error


class FakeMicrosoftDriver:
    audio_format = AudioFormat.MP3

    def __init__(
        self,
        fingerprint="fake-edge-v1",
        error=None,
        partial=False,
        audio_prefix="native-mp3",
    ):
        self.synthesis_fingerprint = fingerprint
        self.error = error
        self.partial = partial
        self.audio_prefix = audio_prefix
        self.calls = 0
        self.texts = []

    async def synth(self, text):
        self.calls += 1
        self.texts.append(text)
        if self.partial:
            yield b"partial-mp3"
        if self.error is not None:
            raise self.error
        yield f"{self.audio_prefix}:{text}".encode()


class EmptyMicrosoftDriver(FakeMicrosoftDriver):
    async def synth(self, text):
        self.calls += 1
        self.texts.append(text)
        if False:
            yield b"unreachable"


def _select_microsoft_yue(tmp_path, monkeypatch, driver):
    monkeypatch.setattr(appmod, "cache", SegmentCache(tmp_path / "cache"))
    monkeypatch.setattr(
        appmod, "CONTRACT_STORE", ContractStore(tmp_path / "uploaded")
    )
    provider = MicrosoftTTSProvider(driver)
    profile = appmod.TEMPLATE_REGISTRY["xcash_yue"]
    selected = replace(
        profile,
        engine_profile=replace(
            profile.engine_profile,
            id="microsoft_yue",
            available=True,
            synthesis_fingerprint=provider.synthesis_fingerprint,
            engine_provider=lambda: provider,
        ),
    )
    monkeypatch.setitem(appmod.TEMPLATE_REGISTRY, "xcash_yue", selected)
    return provider


def _install_profile_matrix(
    tmp_path,
    monkeypatch,
    *,
    engine_names,
    engines,
    api_key="",
):
    monkeypatch.setattr(appmod, "cache", SegmentCache(tmp_path / "cache"))
    monkeypatch.setattr(
        appmod, "CONTRACT_STORE", ContractStore(tmp_path / "uploaded")
    )
    providers = {
        language: (lambda language=language: engines[language])
        for language in ("yue", "zh", "en")
    }
    registry = build_template_registry(
        engine_name=engine_names["yue"],
        engine_names=engine_names,
        api_key=api_key,
        engine_provider=providers["yue"],
        engine_providers=providers,
        synthesis_fingerprints={
            language: getattr(
                engines[language], "synthesis_fingerprint", "audio-artifact-v1"
            )
            for language in ("yue", "zh", "en")
        },
    )
    monkeypatch.setattr(appmod, "TEMPLATE_REGISTRY", registry)


def _upload_yue(client, text="第一段。第二段。"):  # two segments for cold-GET tests
    response = client.post(
        "/api/contracts",
        json={"text": text, "template_id": "xcash_yue"},
    )
    assert response.status_code == 200
    return response


@pytest.mark.parametrize(
    ("configured", "canonical"),
    [
        ("0%", "+0%"),
        ("-0%", "+0%"),
        ("+25%", "+25%"),
        (" -10% ", "-10%"),
    ],
)
def test_edge_rate_is_canonicalized(configured, canonical):
    assert normalize_edge_rate(configured) == canonical


@pytest.mark.parametrize("configured", ["", "fast", "1.5%", "+ 5%", "5"])
def test_invalid_edge_rate_fails_local_configuration(configured):
    with pytest.raises(ValueError, match="integer percentage"):
        normalize_edge_rate(configured)


def test_microsoft_provider_requires_a_supported_driver_and_nonempty_voice():
    with pytest.raises(ValueError, match="MICROSOFT_TTS_DRIVER"):
        build_microsoft_provider(driver_name="", voice="voice", rate="+0%")
    with pytest.raises(ValueError, match="unsupported Microsoft TTS driver"):
        build_microsoft_provider(driver_name="sapi", voice="voice", rate="+0%")
    with pytest.raises(ValueError, match="voice must not be empty"):
        build_microsoft_provider(driver_name="edge", voice=" ", rate="+0%")


def test_building_edge_provider_validates_without_starting_communication():
    calls = []

    def communicate_factory(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("communication must be lazy")

    provider = build_microsoft_provider(
        driver_name=" EDGE ",
        voice="zh-HK-WanLungNeural",
        rate="0%",
        communicate_factory=communicate_factory,
    )

    assert isinstance(provider, MicrosoftTTSProvider)
    assert isinstance(provider.driver, EdgeTTSDriver)
    assert provider.audio_format is AudioFormat.MP3
    assert provider.driver.rate == "+0%"
    assert calls == []


def test_edge_driver_passes_voice_and_rate_and_keeps_audio_chunks_in_order():
    calls = []
    communication = FakeCommunicate(
        [
            {"type": "WordBoundary", "offset": 1},
            {"type": "audio", "data": b"mp3-a"},
            {"type": "audio", "data": b"mp3-b"},
        ]
    )

    def communicate_factory(*args, **kwargs):
        calls.append((args, kwargs))
        return communication

    driver = EdgeTTSDriver(
        voice="zh-HK-WanLungNeural",
        rate="20%",
        communicate_factory=communicate_factory,
    )

    assert asyncio.run(_collect(driver.synth("合約內容"))) == b"mp3-amp3-b"
    assert calls == [
        (
            ("合約內容",),
            {"voice": "zh-HK-WanLungNeural", "rate": "+20%"},
        )
    ]


@pytest.mark.parametrize(
    "communication",
    [
        FakeCommunicate([{"type": "WordBoundary", "offset": 1}]),
        FakeCommunicate([{"type": "audio", "data": b""}]),
        FakeCommunicate(error=TimeoutError("upstream timed out")),
        FakeCommunicate(
            [{"type": "audio", "data": b"partial"}],
            ConnectionError("stream interrupted"),
        ),
    ],
)
def test_edge_driver_maps_empty_and_failed_streams_to_microsoft_error(
    communication,
):
    driver = EdgeTTSDriver(
        voice="zh-HK-WanLungNeural",
        rate="+0%",
        communicate_factory=lambda *args, **kwargs: communication,
    )

    with pytest.raises(MicrosoftSynthesisError):
        asyncio.run(_collect(driver.synth("合約內容")))


def test_edge_driver_maps_communication_construction_failure():
    def fail_to_connect(*args, **kwargs):
        raise ConnectionError("connection refused")

    driver = EdgeTTSDriver(
        voice="zh-HK-WanLungNeural",
        rate="+0%",
        communicate_factory=fail_to_connect,
    )

    with pytest.raises(MicrosoftSynthesisError, match="connection refused"):
        asyncio.run(_collect(driver.synth("合約內容")))


def test_edge_fingerprint_covers_driver_voice_rate_format_and_adapter():
    driver = EdgeTTSDriver(
        voice="zh-HK-WanLungNeural",
        rate="0%",
        communicate_factory=lambda *args, **kwargs: None,
    )

    assert '"driver":"edge"' in driver.synthesis_fingerprint
    assert '"voice":"zh-HK-WanLungNeural"' in driver.synthesis_fingerprint
    assert '"rate":"+0%"' in driver.synthesis_fingerprint
    assert '"format":"mp3"' in driver.synthesis_fingerprint
    assert '"adapter":"microsoft-edge-v' in driver.synthesis_fingerprint


def test_microsoft_provider_contract_accepts_replaceable_edge_and_azure_drivers():
    edge = FakeMicrosoftDriver(
        fingerprint="edge|voice=test|rate=+0%|mp3|v1",
        audio_prefix="edge-audio",
    )
    azure = FakeMicrosoftDriver(
        fingerprint="azure|voice=test|rate=+0%|mp3|v1",
        audio_prefix="azure-audio",
    )

    edge_provider = MicrosoftTTSProvider(edge)
    azure_provider = MicrosoftTTSProvider(azure)

    assert asyncio.run(_collect(edge_provider.synth("contract"))) == (
        b"edge-audio:contract"
    )
    assert asyncio.run(_collect(azure_provider.synth("contract"))) == (
        b"azure-audio:contract"
    )
    assert edge_provider.audio_format is azure_provider.audio_format
    assert (
        edge_provider.synthesis_fingerprint
        != azure_provider.synthesis_fingerprint
    )


def test_cantonese_microsoft_profile_returns_native_mp3_and_reuses_warm_cache(
    tmp_path, monkeypatch
):
    driver = FakeMicrosoftDriver()
    _select_microsoft_yue(tmp_path, monkeypatch, driver)
    client = TestClient(appmod.app)

    upload = _upload_yue(client, text="粵語合約內容。")
    calls_after_warm = driver.calls
    response = client.get(
        f"/api/contracts/{upload.json()['contract_id']}/segments/0"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content.startswith(b"native-mp3:")
    assert driver.calls == calls_after_warm


def test_microsoft_fingerprint_change_isolates_cached_segment(
    tmp_path, monkeypatch
):
    first = FakeMicrosoftDriver(fingerprint="edge|voice=a|rate=+0%|mp3|v1")
    _select_microsoft_yue(tmp_path, monkeypatch, first)
    client = TestClient(appmod.app)
    upload = _upload_yue(client, text="同一份合約。")
    cid = upload.json()["contract_id"]
    assert client.get(f"/api/contracts/{cid}/segments/0").status_code == 200
    assert first.calls == 1

    second = FakeMicrosoftDriver(fingerprint="edge|voice=b|rate=+0%|mp3|v1")
    provider = MicrosoftTTSProvider(second)
    profile = appmod.TEMPLATE_REGISTRY["xcash_yue"]
    monkeypatch.setitem(
        appmod.TEMPLATE_REGISTRY,
        "xcash_yue",
        replace(
            profile,
            engine_profile=replace(
                profile.engine_profile,
                synthesis_fingerprint=provider.synthesis_fingerprint,
                engine_provider=lambda: provider,
            ),
        ),
    )

    assert client.get(f"/api/contracts/{cid}/segments/0").status_code == 200
    assert second.calls == 1


def test_same_microsoft_configuration_reuses_a_shared_segment_across_contracts(
    tmp_path, monkeypatch
):
    driver = FakeMicrosoftDriver()
    _select_microsoft_yue(tmp_path, monkeypatch, driver)
    client = TestClient(appmod.app)
    first = _upload_yue(client, text="甲方資料。共同條款。").json()
    second = _upload_yue(client, text="乙方資料。共同條款。").json()
    calls_after_warm = driver.calls

    first_audio = client.get(
        f"/api/contracts/{first['contract_id']}/segments/1"
    )
    calls_after_first_get = driver.calls
    second_audio = client.get(
        f"/api/contracts/{second['contract_id']}/segments/1"
    )

    assert first["contract_id"] != second["contract_id"]
    assert first_audio.status_code == 200
    assert second_audio.status_code == 200
    assert calls_after_first_get == calls_after_warm + 1
    assert driver.calls == calls_after_first_get
    assert second_audio.content == first_audio.content


def test_uncached_microsoft_failure_returns_502_without_fallback_or_partial_cache(
    tmp_path, monkeypatch
):
    driver = FakeMicrosoftDriver(
        error=ConnectionError("edge unavailable"), partial=True
    )
    _select_microsoft_yue(tmp_path, monkeypatch, driver)

    class FallbackMustNotRun:
        calls = 0

        async def synth(self, text):
            self.calls += 1
            yield b"fallback"

    fallback = FallbackMustNotRun()
    monkeypatch.setattr(appmod, "engine", fallback)
    client = TestClient(appmod.app)
    upload = _upload_yue(client)
    cid = upload.json()["contract_id"]
    calls_after_failed_warm = driver.calls

    first = client.get(f"/api/contracts/{cid}/segments/1")
    second = client.get(f"/api/contracts/{cid}/segments/1")

    assert first.status_code == 502
    assert second.status_code == 502
    assert driver.calls == calls_after_failed_warm + 2
    assert fallback.calls == 0


def test_empty_microsoft_driver_stream_returns_502_and_is_not_cached(
    tmp_path, monkeypatch
):
    driver = EmptyMicrosoftDriver()
    _select_microsoft_yue(tmp_path, monkeypatch, driver)
    client = TestClient(appmod.app)
    upload = _upload_yue(client, text="空音訊測試。")
    cid = upload.json()["contract_id"]
    calls_after_failed_warm = driver.calls

    first = client.get(f"/api/contracts/{cid}/segments/0")
    second = client.get(f"/api/contracts/{cid}/segments/0")

    assert first.status_code == 502
    assert second.status_code == 502
    assert driver.calls == calls_after_failed_warm + 2


def test_failed_microsoft_preload_is_best_effort_and_get_retries_with_502(
    tmp_path, monkeypatch
):
    driver = FakeMicrosoftDriver(error=TimeoutError("edge timed out"))
    _select_microsoft_yue(tmp_path, monkeypatch, driver)
    client = TestClient(appmod.app)
    upload = _upload_yue(client)
    cid = upload.json()["contract_id"]

    preload = client.post(f"/api/contracts/{cid}/segments/1/preload")
    calls_after_preload = driver.calls
    response = client.get(f"/api/contracts/{cid}/segments/1")

    assert preload.status_code == 200
    assert preload.json()["status"] == "preloading"
    assert response.status_code == 502
    assert driver.calls == calls_after_preload + 1


def test_microsoft_rate_does_not_change_contract_timing_or_request_schema(
    tmp_path, monkeypatch
):
    first = EdgeTTSDriver(
        voice="zh-HK-WanLungNeural",
        rate="+0%",
        communicate_factory=lambda *args, **kwargs: FakeCommunicate(
            [{"type": "audio", "data": b"mp3"}]
        ),
    )
    _select_microsoft_yue(tmp_path, monkeypatch, first)
    client = TestClient(appmod.app)
    baseline = _upload_yue(client, text="第一條。第二條。").json()

    faster = EdgeTTSDriver(
        voice="zh-HK-WanLungNeural",
        rate="+30%",
        communicate_factory=lambda *args, **kwargs: FakeCommunicate(
            [{"type": "audio", "data": b"mp3"}]
        ),
    )
    provider = MicrosoftTTSProvider(faster)
    profile = appmod.TEMPLATE_REGISTRY["xcash_yue"]
    monkeypatch.setitem(
        appmod.TEMPLATE_REGISTRY,
        "xcash_yue",
        replace(
            profile,
            engine_profile=replace(
                profile.engine_profile,
                synthesis_fingerprint=provider.synthesis_fingerprint,
                engine_provider=lambda: provider,
            ),
        ),
    )
    changed = _upload_yue(client, text="第一條。第二條。").json()

    assert changed["total_est_s"] == baseline["total_est_s"]
    assert changed["segments"] == baseline["segments"]
    assert {"provider", "driver", "voice", "rate"}.isdisjoint(changed)


def test_global_microsoft_serves_native_mp3_for_all_language_templates(
    tmp_path, monkeypatch
):
    drivers = {
        "yue": FakeMicrosoftDriver(
            fingerprint="edge|yue|v1", audio_prefix="yue-mp3"
        ),
        "zh": FakeMicrosoftDriver(
            fingerprint="edge|zh|v1", audio_prefix="zh-mp3"
        ),
        "en": FakeMicrosoftDriver(
            fingerprint="edge|en|v1", audio_prefix="en-mp3"
        ),
    }
    engines = {
        language: MicrosoftTTSProvider(driver)
        for language, driver in drivers.items()
    }
    _install_profile_matrix(
        tmp_path,
        monkeypatch,
        engine_names={language: "microsoft" for language in drivers},
        engines=engines,
    )
    client = TestClient(appmod.app)

    requests = {
        "yue": ("xcash_yue", "粵語合同內容。"),
        "zh": ("xcash_zh", "普通话合同内容。"),
        "en": ("xcash_en", "The borrower shall pay."),
    }
    for language, (template_id, text) in requests.items():
        upload = client.post(
            "/api/contracts",
            json={"text": text, "template_id": template_id},
        )
        assert upload.status_code == 200
        response = client.get(
            f"/api/contracts/{upload.json()['contract_id']}/segments/0"
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.content.startswith(f"{language}-mp3:".encode())
        assert drivers[language].calls == 1


def test_language_profiles_can_mix_microsoft_gptsovits_and_cosyvoice(
    tmp_path, monkeypatch
):
    microsoft_driver = FakeMicrosoftDriver(audio_prefix="microsoft-yue")
    microsoft = MicrosoftTTSProvider(microsoft_driver)
    gptsovits = FakeEngine(AudioFormat.WAV)
    cosyvoice = FakeEngine(AudioFormat.WAV)
    _install_profile_matrix(
        tmp_path,
        monkeypatch,
        engine_names={
            "yue": "microsoft",
            "zh": "gptsovits",
            "en": "cosyvoice",
        },
        engines={"yue": microsoft, "zh": gptsovits, "en": cosyvoice},
        api_key="sk-test",
    )
    client = TestClient(appmod.app)

    matrix = [
        ("xcash_yue", "粵語合同。", "audio/mpeg"),
        ("xcash_zh", "普通话合同。", "audio/wav"),
        ("xcash_en", "English contract.", "audio/wav"),
    ]
    for template_id, text, media_type in matrix:
        upload = client.post(
            "/api/contracts",
            json={"text": text, "template_id": template_id},
        )
        assert upload.status_code == 200
        response = client.get(
            f"/api/contracts/{upload.json()['contract_id']}/segments/0"
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == media_type

    assert microsoft_driver.calls == 1
    assert gptsovits.calls == 1
    assert cosyvoice.calls == 1


def test_changing_one_language_fingerprint_preserves_other_language_caches(
    tmp_path, monkeypatch
):
    drivers = {
        language: FakeMicrosoftDriver(
            fingerprint=f"edge|{language}|v1", audio_prefix=f"{language}-v1"
        )
        for language in ("yue", "zh", "en")
    }
    engines = {
        language: MicrosoftTTSProvider(driver)
        for language, driver in drivers.items()
    }
    _install_profile_matrix(
        tmp_path,
        monkeypatch,
        engine_names={language: "microsoft" for language in drivers},
        engines=engines,
    )
    client = TestClient(appmod.app)
    uploads = {}
    for language, template_id, text in [
        ("yue", "xcash_yue", "共同条款。"),
        ("zh", "xcash_zh", "共同条款。"),
        ("en", "xcash_en", "Common term."),
    ]:
        response = client.post(
            "/api/contracts",
            json={"text": text, "template_id": template_id},
        )
        assert response.status_code == 200
        uploads[language] = response.json()["contract_id"]
    baseline_calls = {
        language: driver.calls for language, driver in drivers.items()
    }

    replacement_driver = FakeMicrosoftDriver(
        fingerprint="edge|zh|v2", audio_prefix="zh-v2"
    )
    replacement = MicrosoftTTSProvider(replacement_driver)
    zh_profile = appmod.TEMPLATE_REGISTRY["xcash_zh"]
    monkeypatch.setitem(
        appmod.TEMPLATE_REGISTRY,
        "xcash_zh",
        replace(
            zh_profile,
            engine_profile=replace(
                zh_profile.engine_profile,
                synthesis_fingerprint=replacement.synthesis_fingerprint,
                engine_provider=lambda: replacement,
            ),
        ),
    )

    responses = {
        language: client.get(f"/api/contracts/{cid}/segments/0")
        for language, cid in uploads.items()
    }

    assert all(response.status_code == 200 for response in responses.values())
    assert responses["zh"].content.startswith(b"zh-v2:")
    assert replacement_driver.calls == 1
    assert drivers["yue"].calls == baseline_calls["yue"]
    assert drivers["zh"].calls == baseline_calls["zh"]
    assert drivers["en"].calls == baseline_calls["en"]


def test_microsoft_failure_is_isolated_to_the_selected_language(
    tmp_path, monkeypatch
):
    yue_driver = FakeMicrosoftDriver(audio_prefix="yue-ok")
    zh_driver = FakeMicrosoftDriver(error=TimeoutError("zh edge unavailable"))
    en_driver = FakeMicrosoftDriver(audio_prefix="en-ok")
    engines = {
        "yue": MicrosoftTTSProvider(yue_driver),
        "zh": MicrosoftTTSProvider(zh_driver),
        "en": MicrosoftTTSProvider(en_driver),
    }
    _install_profile_matrix(
        tmp_path,
        monkeypatch,
        engine_names={language: "microsoft" for language in engines},
        engines=engines,
    )
    client = TestClient(appmod.app)

    yue_upload = client.post(
        "/api/contracts",
        json={"text": "粤语正常。", "template_id": "xcash_yue"},
    )
    zh_upload = client.post(
        "/api/contracts",
        json={"text": "普通话失败。", "template_id": "xcash_zh"},
    )
    en_upload = client.post(
        "/api/contracts",
        json={"text": "English works.", "template_id": "xcash_en"},
    )

    assert yue_upload.status_code == 200
    assert zh_upload.status_code == 200
    assert en_upload.status_code == 200
    assert client.get(
        f"/api/contracts/{yue_upload.json()['contract_id']}/segments/0"
    ).status_code == 200
    assert client.get(
        f"/api/contracts/{zh_upload.json()['contract_id']}/segments/0"
    ).status_code == 502
    assert client.get(
        f"/api/contracts/{en_upload.json()['contract_id']}/segments/0"
    ).status_code == 200


@pytest.mark.parametrize(
    ("language", "template_id", "text", "voice"),
    [
        ("zh", "xcash_zh", "第一条。第二条。", "zh-CN-YunyangNeural"),
        ("en", "xcash_en", "First term. Second term.", "en-HK-SamNeural"),
    ],
)
def test_microsoft_rate_does_not_change_mandarin_or_english_timing(
    tmp_path, monkeypatch, language, template_id, text, voice
):
    def communication(*args, **kwargs):
        return FakeCommunicate([{"type": "audio", "data": b"mp3"}])
    baseline_driver = EdgeTTSDriver(
        voice=voice,
        rate="+0%",
        communicate_factory=communication,
    )
    engines = {
        "yue": FakeEngine(AudioFormat.WAV),
        "zh": FakeEngine(AudioFormat.WAV),
        "en": FakeEngine(AudioFormat.WAV),
    }
    engines[language] = MicrosoftTTSProvider(baseline_driver)
    engine_names = {"yue": "gptsovits", "zh": "gptsovits", "en": "gptsovits"}
    engine_names[language] = "microsoft"
    _install_profile_matrix(
        tmp_path,
        monkeypatch,
        engine_names=engine_names,
        engines=engines,
    )
    client = TestClient(appmod.app)
    baseline = client.post(
        "/api/contracts",
        json={"text": text, "template_id": template_id},
    ).json()

    faster = MicrosoftTTSProvider(
        EdgeTTSDriver(
            voice=voice,
            rate="+30%",
            communicate_factory=communication,
        )
    )
    profile = appmod.TEMPLATE_REGISTRY[template_id]
    monkeypatch.setitem(
        appmod.TEMPLATE_REGISTRY,
        template_id,
        replace(
            profile,
            engine_profile=replace(
                profile.engine_profile,
                synthesis_fingerprint=faster.synthesis_fingerprint,
                engine_provider=lambda: faster,
            ),
        ),
    )
    changed_response = client.post(
        "/api/contracts",
        json={"text": text, "template_id": template_id},
    )
    assert changed_response.status_code == 200
    changed = changed_response.json()

    assert changed["segments"] == baseline["segments"]
    assert changed["total_est_s"] == baseline["total_est_s"]
