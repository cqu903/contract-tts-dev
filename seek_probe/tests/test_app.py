from fastapi.testclient import TestClient
import seek_probe.backend.app as appmod
from seek_probe.backend.cache import SegmentCache
from seek_probe.backend.gptsovits_client import GPTSoVITSClient
from seek_probe.backend.bailian_cosyvoice_client import BailianCosyVoiceClient


class FakeEngine:
    def __init__(self):
        self.calls = 0

    async def synth(self, text, transport=None):
        self.calls += 1
        yield f"audio:{text}".encode()


def test_contract_index_and_segment_caches_after_first_call(tmp_path, monkeypatch):
    contract = tmp_path / "c.txt"
    contract.write_text("第一句。第二句！", encoding="utf-8")
    monkeypatch.setattr(appmod, "_CONTRACT_FILES", {"sample": contract})
    monkeypatch.setattr(appmod, "cache", SegmentCache(tmp_path / "cache"))
    fake = FakeEngine()
    monkeypatch.setattr(appmod, "engine", fake)

    client = TestClient(appmod.app)

    r = client.get("/api/contract/sample")
    assert r.status_code == 200
    data = r.json()
    assert data["total_est_s"] > 0 and len(data["segments"]) == 2

    r1 = client.get("/api/segment/sample/0")
    assert r1.status_code == 200 and fake.calls == 1

    r2 = client.get("/api/segment/sample/0")   # cache hit
    assert r2.status_code == 200 and fake.calls == 1


def test_unknown_contract_404(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "_CONTRACT_FILES", {})
    monkeypatch.setattr(appmod, "cache", SegmentCache(tmp_path / "cache"))
    monkeypatch.setattr(appmod, "engine", FakeEngine())
    client = TestClient(appmod.app)
    assert client.get("/api/contract/nope").status_code == 404


def test_preload_warms_cache_without_blocking(tmp_path, monkeypatch):
    contract = tmp_path / "c.txt"
    contract.write_text("第一句。第二句！", encoding="utf-8")
    monkeypatch.setattr(appmod, "_CONTRACT_FILES", {"sample": contract})
    monkeypatch.setattr(appmod, "cache", SegmentCache(tmp_path / "cache"))
    fake = FakeEngine()
    monkeypatch.setattr(appmod, "engine", fake)
    client = TestClient(appmod.app)

    r = client.post("/api/preload/sample/1")
    assert r.status_code == 200
    assert r.json()["status"] in {"preloading", "cached"}
    # BackgroundTasks run before TestClient returns the response, so cache is warm now
    calls_before = fake.calls
    client.get("/api/segment/sample/1")
    assert fake.calls == calls_before


def test_make_engine_bailian_reads_api_key_and_default_voice(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-x")
    e = appmod.make_engine("bailian")
    assert isinstance(e, BailianCosyVoiceClient)
    assert e.api_key == "sk-x"
    assert e.voice == "longjiaxin_v3"   # native Cantonese voice (粤语/英文)


def test_make_engine_defaults_to_gptsovits():
    assert isinstance(appmod.make_engine("gptsovits"), GPTSoVITSClient)
