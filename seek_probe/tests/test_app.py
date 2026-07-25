from fastapi.testclient import TestClient
import seek_probe.backend.app as appmod
from seek_probe.backend.cache import SegmentCache


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
