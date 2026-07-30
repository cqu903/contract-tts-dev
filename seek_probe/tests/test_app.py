from fastapi.testclient import TestClient
import seek_probe.backend.app as appmod
from seek_probe.backend.cache import SegmentCache
from seek_probe.backend.contract import ContractStore
from seek_probe.backend.gptsovits_client import GPTSoVITSClient
from seek_probe.backend.bailian_cosyvoice_client import BailianCosyVoiceClient


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


def test_make_engine_defaults_to_gptsovits():
    assert isinstance(appmod.make_engine("gptsovits"), GPTSoVITSClient)
