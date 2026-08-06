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

    def __init__(self, fingerprint="fake-edge-v1", error=None, partial=False):
        self.synthesis_fingerprint = fingerprint
        self.error = error
        self.partial = partial
        self.calls = 0
        self.texts = []

    async def synth(self, text):
        self.calls += 1
        self.texts.append(text)
        if self.partial:
            yield b"partial-mp3"
        if self.error is not None:
            raise self.error
        yield f"native-mp3:{text}".encode()


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


def test_microsoft_provider_requires_explicit_edge_driver_and_nonempty_voice():
    with pytest.raises(ValueError, match="MICROSOFT_TTS_DRIVER"):
        build_microsoft_provider(driver_name="", voice="voice", rate="+0%")
    with pytest.raises(ValueError, match="unsupported Microsoft TTS driver"):
        build_microsoft_provider(driver_name="azure", voice="voice", rate="+0%")
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
