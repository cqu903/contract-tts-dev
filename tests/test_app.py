import asyncio
import hashlib
import os
import time
from dataclasses import replace

import httpx
from fastapi.testclient import TestClient
import backend.app as appmod
from backend.audio import AudioArtifact, AudioFormat
from backend.cache import SegmentCache
from backend.contract import ContractStore
from backend.gptsovits_client import GPTSoVITSClient
from backend.bailian_cosyvoice_client import BailianCosyVoiceClient


class FakeEngine:
    def __init__(self, audio_format=AudioFormat.WAV):
        self.calls = 0
        self.texts = []
        self.audio_format = audio_format

    async def synth(self, text, transport=None):
        self.calls += 1
        self.texts.append(text)
        yield f"audio:{text}".encode()


class SlowFakeEngine(FakeEngine):
    async def synth(self, text, transport=None):
        self.calls += 1
        self.texts.append(text)
        await asyncio.sleep(0.05)
        yield f"audio:{text}".encode()


class PartialFailureEngine(FakeEngine):
    async def synth(self, text, transport=None):
        self.calls += 1
        self.texts.append(text)
        yield b"partial"
        raise RuntimeError("stream interrupted")


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "cache", SegmentCache(tmp_path / "cache"))
    monkeypatch.setattr(appmod, "CONTRACT_STORE", ContractStore(tmp_path / "uploaded"))
    fake = FakeEngine()
    monkeypatch.setattr(appmod, "engine", fake)
    return fake


def _upload(client, text="第一句。第二句！", template_id="xcash"):
    r = client.post("/api/contracts", json={"text": text, "template_id": template_id})
    assert r.status_code == 200
    return r.json()["contract_id"]


def test_upload_index_and_segment_caches_after_first_call(tmp_path, monkeypatch):
    fake = _setup(tmp_path, monkeypatch)
    client = TestClient(appmod.app)

    cid = _upload(client)
    r = client.get(f"/api/contracts/{cid}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_est_s"] > 0 and len(data["segments"]) == 2
    assert "texts" not in data   # ADR-0001: do not echo segment text

    # 上传后台预热了 seg 0：GET seg 0 命中缓存、不触发新合成
    baseline = fake.calls
    assert client.get(f"/api/contracts/{cid}/segments/0").status_code == 200
    assert fake.calls == baseline   # seg 0 already warmed on upload

    # seg 1 未预热：GET 合成一次
    r1 = client.get(f"/api/contracts/{cid}/segments/1")
    assert r1.status_code == 200 and fake.calls == baseline + 1

    r2 = client.get(f"/api/contracts/{cid}/segments/1")   # cache hit, no new synth
    assert r2.status_code == 200 and fake.calls == baseline + 1


def test_segment_response_uses_the_engine_audio_format(tmp_path, monkeypatch):
    fake = _setup(tmp_path, monkeypatch)
    fake.audio_format = AudioFormat.MP3
    client = TestClient(appmod.app)

    cid = _upload(client, text="格式感知。", template_id="xcash_yue")
    response = client.get(f"/api/contracts/{cid}/segments/0")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == "audio:格式感知。".encode()


def test_concurrent_requests_for_the_same_segment_synthesize_once(
    tmp_path, monkeypatch
):
    _setup(tmp_path, monkeypatch)
    slow = SlowFakeEngine()
    monkeypatch.setattr(appmod, "engine", slow)

    async def request_twice():
        transport = httpx.ASGITransport(app=appmod.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            upload = await client.post(
                "/api/contracts",
                json={"text": "第一句。第二句。", "template_id": "xcash"},
            )
            assert upload.status_code == 200
            cid = upload.json()["contract_id"]
            calls_after_warm = slow.calls
            responses = await asyncio.gather(
                client.get(f"/api/contracts/{cid}/segments/1"),
                client.get(f"/api/contracts/{cid}/segments/1"),
            )
        return calls_after_warm, responses

    calls_after_warm, responses = asyncio.run(request_twice())

    assert [response.status_code for response in responses] == [200, 200]
    assert slow.calls == calls_after_warm + 1
    assert responses[0].content == responses[1].content


def test_interrupted_synthesis_does_not_leave_a_partial_cache_hit(
    tmp_path, monkeypatch
):
    _setup(tmp_path, monkeypatch)
    failing = PartialFailureEngine()
    monkeypatch.setattr(appmod, "engine", failing)
    client = TestClient(appmod.app)
    cid = _upload(client, text="预热段。失败段。")
    calls_after_warm = failing.calls

    first = client.get(f"/api/contracts/{cid}/segments/1")
    second = client.get(f"/api/contracts/{cid}/segments/1")

    assert first.status_code == 500
    assert second.status_code == 500
    assert failing.calls == calls_after_warm + 2


def test_unknown_template_id_returns_400(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(appmod.app)
    r = client.post("/api/contracts", json={"text": "x", "template_id": "bogus"})
    assert r.status_code == 400


def test_upload_rejects_control_only_contract_text(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(appmod.app)

    response = client.post(
        "/api/contracts",
        json={"text": "\x00\x01\x02", "template_id": "xcash_yue"},
    )

    assert response.status_code == 400
    assert list((tmp_path / "uploaded").glob("*.txt")) == []


def test_upload_echoes_canonical_template_id(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(appmod.app)

    response = client.post(
        "/api/contracts",
        json={"text": "普通话合同。", "template_id": "xcash_yue"},
    )

    assert response.status_code == 200
    assert response.json()["template_id"] == "xcash_yue"


def test_frontend_assets_disable_conditional_browser_cache():
    client = TestClient(appmod.app)

    first = client.get("/app.js")
    second = client.get(
        "/app.js",
        headers={
            "If-None-Match": first.headers.get("etag", '"stale"'),
            "If-Modified-Since": first.headers.get(
                "last-modified", "Wed, 21 Oct 2015 07:28:00 GMT"
            ),
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers["cache-control"] == "no-store, no-cache, must-revalidate"


def test_frontend_initially_requests_three_segments():
    client = TestClient(appmod.app)

    source = client.get("/app.js").text

    assert "const INITIAL_SEGMENT_REQUEST_COUNT = 3;" in source
    assert "const firstSegment = loadSegment(0);" in source
    assert "preloadAhead(0, INITIAL_SEGMENT_REQUEST_COUNT - 1);" in source


def test_xcash_alias_and_canonical_template_share_new_contract_id(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(appmod.app)

    alias = _upload(client, text="同一份合同。", template_id="xcash")
    canonical = _upload(client, text="同一份合同。", template_id="xcash_yue")

    assert alias == canonical


def test_unavailable_template_profile_returns_503_without_creating_contract(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    profile = appmod.TEMPLATE_REGISTRY["xcash_yue"]
    unavailable = replace(
        profile,
        engine_profile=replace(profile.engine_profile, available=False),
    )
    monkeypatch.setitem(appmod.TEMPLATE_REGISTRY, "xcash_yue", unavailable)
    client = TestClient(appmod.app)

    r = client.post("/api/contracts", json={"text": "不可用。", "template_id": "xcash_yue"})

    assert r.status_code == 503
    assert list((tmp_path / "uploaded").glob("*.txt")) == []


def test_template_profile_selects_its_engine_provider(tmp_path, monkeypatch):
    default_engine = _setup(tmp_path, monkeypatch)
    selected_engine = FakeEngine()
    profile = appmod.TEMPLATE_REGISTRY["xcash_yue"]
    selected = replace(
        profile,
        engine_profile=replace(
            profile.engine_profile,
            engine_provider=lambda: selected_engine,
        ),
    )
    monkeypatch.setitem(appmod.TEMPLATE_REGISTRY, "xcash_yue", selected)
    client = TestClient(appmod.app)

    _upload(client, text="选择 profile。", template_id="xcash_yue")

    assert selected_engine.calls == 1
    assert default_engine.calls == 0


def test_engine_profile_synthesis_fingerprint_isolates_cached_audio(
    tmp_path, monkeypatch
):
    fake = _setup(tmp_path, monkeypatch)
    profile = appmod.TEMPLATE_REGISTRY["xcash_yue"]
    first_profile = replace(
        profile,
        engine_profile=replace(
            profile.engine_profile,
            synthesis_fingerprint="wav-adapter-v1",
        ),
    )
    monkeypatch.setitem(appmod.TEMPLATE_REGISTRY, "xcash_yue", first_profile)
    client = TestClient(appmod.app)
    cid = _upload(client, text="缓存指纹。", template_id="xcash_yue")
    calls_after_warm = fake.calls

    assert client.get(f"/api/contracts/{cid}/segments/0").status_code == 200
    assert fake.calls == calls_after_warm

    second_profile = replace(
        first_profile,
        engine_profile=replace(
            first_profile.engine_profile,
            synthesis_fingerprint="wav-adapter-v2",
        ),
    )
    monkeypatch.setitem(appmod.TEMPLATE_REGISTRY, "xcash_yue", second_profile)

    assert client.get(f"/api/contracts/{cid}/segments/0").status_code == 200
    assert fake.calls == calls_after_warm + 1


def test_new_pipeline_does_not_hit_legacy_cache_key(tmp_path, monkeypatch):
    fake = _setup(tmp_path, monkeypatch)
    client = TestClient(appmod.app)
    cid = _upload(client, text="第一句。第二句！")

    from backend.normalizer import normalize_for_tts

    tts_text = normalize_for_tts("第二句！")
    legacy_key = hashlib.sha256(
        f"{tts_text}|{appmod.ENGINE_NAME}".encode("utf-8")
    ).hexdigest()
    appmod.cache.put(
        legacy_key,
        AudioArtifact(b"legacy-audio", AudioFormat.WAV),
    )
    baseline = fake.calls

    response = client.get(f"/api/contracts/{cid}/segments/1")

    assert response.status_code == 200
    assert response.content != b"legacy-audio"
    assert fake.calls == baseline + 1


def test_unknown_contract_returns_404(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(appmod.app)
    assert client.get("/api/contracts/nope").status_code == 404
    assert client.get("/api/contracts/nope/segments/0").status_code == 404
    assert client.post("/api/contracts/nope/segments/0/preload").status_code == 404


def test_preload_warms_cache_without_blocking(tmp_path, monkeypatch):
    fake = _setup(tmp_path, monkeypatch)
    client = TestClient(appmod.app)
    cid = _upload(client)

    r = client.post(f"/api/contracts/{cid}/segments/1/preload")
    assert r.status_code == 200
    assert r.json()["status"] in {"preloading", "cached"}
    # BackgroundTasks run before TestClient returns the response, so cache is warm now
    calls_before = fake.calls
    client.get(f"/api/contracts/{cid}/segments/1")
    assert fake.calls == calls_before   # already cached, no new synth


def test_make_engine_bailian_reads_api_key_and_default_voice(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-x")
    e = appmod.make_engine("bailian")
    assert isinstance(e, BailianCosyVoiceClient)
    assert e.api_key == "sk-x"
    assert e.voice == "longjiaxin_v3"   # native Cantonese voice (粤语/英文)


def test_make_engine_passes_bailian_transport_configuration(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-x")
    monkeypatch.setattr(appmod, "BAILIAN_TRANSPORT", "wss")
    monkeypatch.setattr(appmod, "BAILIAN_MODEL", "cosyvoice-v3-flash")
    monkeypatch.setattr(
        appmod,
        "BAILIAN_WS_URL",
        "wss://workspace.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference",
    )
    monkeypatch.setattr(appmod, "BAILIAN_WORKSPACE_ID", "ws-test")

    engine = appmod.make_engine("bailian", "en")

    assert engine.transport_mode == "wss"
    assert engine.model == "cosyvoice-v3-flash"
    assert engine.voice == appmod.BAILIAN_VOICE_EN
    assert engine.ws_url.startswith("wss://workspace.ap-southeast-1")
    assert engine.workspace == "ws-test"


def test_make_engine_defaults_to_gptsovits():
    engine = appmod.make_engine("gptsovits")
    assert isinstance(engine, GPTSoVITSClient)
    assert engine.audio_format is AudioFormat.WAV


def test_make_engine_bailian_declares_wav_audio(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-x")

    engine = appmod.make_engine("bailian")

    assert isinstance(engine, BailianCosyVoiceClient)
    assert engine.audio_format is AudioFormat.WAV


def test_make_engine_builds_cross_lingual_gptsovits_profiles():
    yue = appmod.make_engine("gptsovits", "yue")
    zh = appmod.make_engine("gptsovits", "zh")
    en = appmod.make_engine("gptsovits", "en")

    assert (yue.text_lang, zh.text_lang, en.text_lang) == ("yue", "zh", "en")
    assert (yue.prompt_lang, zh.prompt_lang, en.prompt_lang) == (
        "yue",
        "yue",
        "yue",
    )
    assert zh.ref_audio_path == en.ref_audio_path == yue.ref_audio_path
    assert zh.prompt_text == en.prompt_text == yue.prompt_text


def test_make_engine_reduces_fragment_pause_only_for_cantonese():
    yue = appmod.make_engine("gptsovits", "yue")
    zh = appmod.make_engine("gptsovits", "zh")
    en = appmod.make_engine("gptsovits", "en")

    assert (yue.fragment_interval, yue.text_split_method) == (0.05, "cut0")
    assert (zh.fragment_interval, zh.text_split_method) == (0.3, "cut5")
    assert (en.fragment_interval, en.text_split_method) == (0.3, "cut5")


def test_make_engine_uses_language_specific_engine_defaults(monkeypatch):
    monkeypatch.setattr(
        appmod,
        "ENGINE_NAMES",
        {"yue": "gptsovits", "zh": "bailian", "en": "gptsovits"},
    )

    assert isinstance(appmod.make_engine(reading_language="yue"), GPTSoVITSClient)
    assert isinstance(
        appmod.make_engine(reading_language="zh"), BailianCosyVoiceClient
    )
    assert isinstance(appmod.make_engine(reading_language="en"), GPTSoVITSClient)
    assert isinstance(appmod.make_engine("cosyvoice", "en"), BailianCosyVoiceClient)


def test_language_specific_gptsovits_reference_overrides_cross_lingual_fallback(
    tmp_path, monkeypatch
):
    prompt_path = tmp_path / "mandarin.txt"
    prompt_path.write_text("這是一段普通話參考文本。", encoding="utf-8")
    monkeypatch.setenv("GPTSOVITS_REF_AUDIO_ENGINE_PATH_ZH", "/refs/mandarin.wav")
    monkeypatch.setenv("GPTSOVITS_REF_PROMPT_ZH", str(prompt_path))
    monkeypatch.delenv("GPTSOVITS_REF_PROMPT_LANG_ZH", raising=False)
    fallback = appmod._GPTSoVITSReferenceProfile(
        ref_audio_path="/refs/cantonese.wav",
        prompt_text="粵語參考文本。",
        prompt_lang="yue",
    )

    profile = appmod._reference_profile_from_env("zh", fallback)

    assert profile.ref_audio_path == "/refs/mandarin.wav"
    assert profile.prompt_text == "這是一段普通話參考文本。"
    assert profile.prompt_lang == "zh"


def test_load_project_env_loads_defaults_without_overriding_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CONTRACT_TTS_TEST_FROM_FILE=loaded\n"
        "CONTRACT_TTS_TEST_PRECEDENCE=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CONTRACT_TTS_TEST_FROM_FILE", raising=False)
    monkeypatch.setenv("CONTRACT_TTS_TEST_PRECEDENCE", "from-environment")

    appmod._load_project_env(env_file)

    assert os.getenv("CONTRACT_TTS_TEST_FROM_FILE") == "loaded"
    assert os.getenv("CONTRACT_TTS_TEST_PRECEDENCE") == "from-environment"


def test_project_path_from_env_supports_relative_and_absolute_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTRACT_TTS_TEST_PATH", "refs/custom.wav")
    assert appmod._project_path_from_env(
        "CONTRACT_TTS_TEST_PATH", "unused.wav"
    ) == appmod.ROOT / "refs" / "custom.wav"

    absolute_path = tmp_path / "custom.wav"
    monkeypatch.setenv("CONTRACT_TTS_TEST_PATH", str(absolute_path))
    assert appmod._project_path_from_env(
        "CONTRACT_TTS_TEST_PATH", "unused.wav"
    ) == absolute_path


def test_main_runs_combined_app_with_uvicorn(monkeypatch):
    call = {}

    def fake_run(application, **kwargs):
        call["application"] = application
        call["kwargs"] = kwargs

    monkeypatch.setattr("uvicorn.run", fake_run)

    appmod.main()

    assert call == {
        "application": appmod.app,
        "kwargs": {"host": "0.0.0.0", "port": 8000},
    }


def test_run_cleanup_evicts_expired_keeps_fresh(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    now = time.time()
    DAY = 86400
    # 过期原文（>90d）+ 过期音频（>30d）
    appmod.CONTRACT_STORE.put("coldcid", "old", now=now - 95 * DAY)
    appmod.cache.put(
        "coldkey",
        AudioArtifact(b"RIFFxxxx", AudioFormat.WAV),
        duration=1.0,
        now=now - 35 * DAY,
    )
    # 未过期对照
    appmod.CONTRACT_STORE.put("hotcid", "fresh", now=now)
    appmod.cache.put(
        "hotkey",
        AudioArtifact(b"RIFFyyyy", AudioFormat.WAV),
        duration=1.0,
        now=now,
    )

    appmod.run_cleanup()

    assert appmod.CONTRACT_STORE.get("coldcid") is None      # 过期原文被删
    assert not appmod.cache.has("coldkey")                   # 过期音频被删
    assert appmod.CONTRACT_STORE.get("hotcid") == "fresh"    # 未过期保留
    assert appmod.cache.has("hotkey")


def test_run_cleanup_swallows_errors(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(appmod.CONTRACT_STORE, "evict_expired", boom)
    appmod.run_cleanup()   # 不抛即通过（ADR-0007：崩了下轮照跑）
