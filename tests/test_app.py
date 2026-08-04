import hashlib
import os
import time
from dataclasses import replace

from fastapi.testclient import TestClient
import backend.app as appmod
from backend.cache import SegmentCache
from backend.contract import ContractStore
from backend.gptsovits_client import GPTSoVITSClient
from backend.bailian_cosyvoice_client import BailianCosyVoiceClient


class FakeEngine:
    def __init__(self):
        self.calls = 0

    async def synth(self, text, transport=None):
        self.calls += 1
        yield f"audio:{text}".encode()


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


def test_unknown_template_id_returns_400(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(appmod.app)
    r = client.post("/api/contracts", json={"text": "x", "template_id": "bogus"})
    assert r.status_code == 400


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


def test_new_pipeline_does_not_hit_legacy_cache_key(tmp_path, monkeypatch):
    fake = _setup(tmp_path, monkeypatch)
    client = TestClient(appmod.app)
    cid = _upload(client, text="第一句。第二句！")

    from backend.normalizer import normalize_for_tts

    tts_text = normalize_for_tts("第二句！")
    legacy_key = hashlib.sha256(
        f"{tts_text}|{appmod.ENGINE_NAME}".encode("utf-8")
    ).hexdigest()
    appmod.cache.put(legacy_key, b"legacy-audio")
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
    assert isinstance(appmod.make_engine("gptsovits"), GPTSoVITSClient)


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
        "kwargs": {"host": "127.0.0.1", "port": 8000},
    }


def test_run_cleanup_evicts_expired_keeps_fresh(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    now = time.time()
    DAY = 86400
    # 过期原文（>90d）+ 过期音频（>30d）
    appmod.CONTRACT_STORE.put("coldcid", "old", now=now - 95 * DAY)
    appmod.cache.put("coldkey", b"RIFFxxxx", duration=1.0, now=now - 35 * DAY)
    # 未过期对照
    appmod.CONTRACT_STORE.put("hotcid", "fresh", now=now)
    appmod.cache.put("hotkey", b"RIFFyyyy", duration=1.0, now=now)

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
