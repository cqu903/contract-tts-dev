"""FastAPI orchestrator: segmentation, content-addressed cache, segment streaming,
seek mapping. Static frontend served at /."""
from __future__ import annotations
import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from seek_probe.backend.contract import build_index
from seek_probe.backend.cache import cache_key, SegmentCache
from seek_probe.backend.gptsovits_client import GPTSoVITSClient

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
CACHE_DIR = ROOT / "cache"

# --- probe config (hardcoded) ---
ENGINE_URL = "http://127.0.0.1:9880"
REF_AUDIO = str(ROOT / "refs" / "cantonese_ref.wav")
REF_PROMPT = (ROOT / "refs" / "cantonese_ref.txt").read_text(encoding="utf-8").strip() \
    if (ROOT / "refs" / "cantonese_ref.txt").exists() else ""
VOICE_REF_ID = "cantonese_ref_v1"

_CONTRACT_FILES = {"sample": ROOT / "contracts" / "sample_contract.txt"}

cache = SegmentCache(CACHE_DIR)
engine = GPTSoVITSClient(ENGINE_URL, REF_AUDIO, REF_PROMPT)

app = FastAPI(title="Cantonese Contract TTS Seek Probe")

# per-key generation lock: concurrent identical requests generate once
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(key: str) -> asyncio.Lock:
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def _resolve_contract(contract_id: str) -> str:
    p = _CONTRACT_FILES.get(contract_id)
    if p is None or not p.exists():
        raise HTTPException(status_code=404, detail=f"unknown contract: {contract_id}")
    return p.read_text(encoding="utf-8")


@app.get("/api/contract/{contract_id}")
def get_contract(contract_id: str):
    idx = build_index(contract_id, _resolve_contract(contract_id))
    return {
        "contract_id": contract_id,
        "total_est_s": idx.total_est_s,
        "segments": [
            {"seg_idx": m.seg_idx, "est_dur_s": m.est_dur_s, "cumulative_start_s": m.cumulative_start_s}
            for m in idx.segments
        ],
        "texts": [m.text for m in idx.segments],
    }


@app.get("/api/segment/{contract_id}/{seg_idx}")
async def get_segment(contract_id: str, seg_idx: int):
    idx = build_index(contract_id, _resolve_contract(contract_id))
    if seg_idx < 0 or seg_idx >= len(idx.segments):
        raise HTTPException(status_code=404, detail="seg_idx out of range")
    seg_text = idx.segments[seg_idx].text
    key = cache_key(seg_text, VOICE_REF_ID)

    cached = cache.get(key)
    if cached is not None:
        return FileResponse(cached, media_type="audio/wav")

    async def streamed():
        async with _lock_for(key):
            cached_again = cache.get(key)        # double-check after lock
            if cached_again is not None:
                yield cached_again.read_bytes()
                return
            buf = bytearray()
            try:
                async for chunk in engine.synth(seg_text):
                    buf.extend(chunk)
                    yield chunk                  # tee: forward to client ASAP
            finally:
                if buf:
                    cache.put(key, bytes(buf))

    return StreamingResponse(streamed(), media_type="audio/wav")


# frontend/ is created in Task 10; guard so importing app (Task 8/9 tests) doesn't crash before then
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
