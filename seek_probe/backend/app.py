"""FastAPI orchestrator: segmentation, content-addressed cache, segment streaming,
seek mapping. Static frontend served at /."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from seek_probe.backend.contract import build_index, dump_segments
from seek_probe.backend.cache import cache_key, SegmentCache
from seek_probe.backend.gptsovits_client import GPTSoVITSClient
from seek_probe.backend.bailian_cosyvoice_client import BailianCosyVoiceClient
from seek_probe.backend.normalizer import normalize_for_tts

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
CACHE_DIR = ROOT / "cache"

# --- probe config (hardcoded) ---
ENGINE_URL = "http://127.0.0.1:9880"
# NOTE: GPT-SoVITS rejects reference clips outside 3-10s; use the trimmed 7s ref.
REF_AUDIO = str(ROOT / "refs" / "cantonese_ref_trim.wav")
REF_PROMPT = (ROOT / "refs" / "cantonese_ref_trim.txt").read_text(encoding="utf-8").strip() \
    if (ROOT / "refs" / "cantonese_ref_trim.txt").exists() else ""
VOICE_REF_ID = "cantonese_ref_v1"

# --- engine selection ---
# Both clients share the synth(text) -> AsyncIterator[bytes] contract; normalization
# stays at the app layer (shared normalizer.py), so swapping engines needs no other change.
# SEEK_PROBE_ENGINE = "gptsovits" (local, default) | "bailian" (cloud cosyvoice).
ENGINE_NAME = os.getenv("SEEK_PROBE_ENGINE", "gptsovits")
BAILIAN_VOICE = os.getenv("BAILIAN_VOICE", "longjiaxin_v3")  # native Cantonese (粤语/英文)


def make_engine(name: str | None = None):
    """Build the TTS engine. name=None -> read SEEK_PROBE_ENGINE env (default gptsovits)."""
    name = name or ENGINE_NAME
    if name == "bailian":
        return BailianCosyVoiceClient(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            voice=BAILIAN_VOICE,
        )
    return GPTSoVITSClient(ENGINE_URL, REF_AUDIO, REF_PROMPT)


_CONTRACT_FILES = {
    "sample": ROOT / "contracts" / "sample_contract.txt",
    "zacl0603": ROOT / "contracts" / "zacl0603.txt",
    "xcash": ROOT / "contracts" / "xcash.txt",
}

# SEEK_PROBE_DUMP_SEGMENTS=1: at startup, dump each registered contract's raw
# segmentation to contracts/<id>.segments.txt (verbatim segmenter output, for
# inspection and tuning). Off by default; no effect on serving.
if os.getenv("SEEK_PROBE_DUMP_SEGMENTS") == "1":
    for _cid, _path in _CONTRACT_FILES.items():
        if not _path.exists():
            print(f"[dump_segments] skip missing contract file: {_path}", flush=True)
            continue
        _out = dump_segments(build_index(_cid, _path.read_text(encoding="utf-8")),
                             _path.with_suffix(".segments.txt"))
        print(f"[dump_segments] {_cid} -> {_out}", flush=True)

cache = SegmentCache(CACHE_DIR)
engine = make_engine()

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
    tts_text = normalize_for_tts(seg_text)   # Arabic numbers -> Chinese for correct reading
    key = cache_key(tts_text, VOICE_REF_ID)

    cached = cache.get(key)
    if cached is not None:
        return FileResponse(cached, media_type="audio/wav")
    # Generate fully, THEN respond: on engine failure we can return a proper
    # error (502/500) instead of an empty 200 that the browser masks as "Load failed".
    try:
        async with _lock_for(key):               # concurrent identical requests -> one gen
            cached_again = cache.get(key)        # double-check after lock
            if cached_again is not None:
                return FileResponse(cached_again, media_type="audio/wav")
            buf = bytearray()
            async for chunk in engine.synth(tts_text):
                buf.extend(chunk)
            data = bytes(buf)
            cache.put(key, data)
        return Response(data, media_type="audio/wav")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"engine {e.response.status_code}: {e.response.text[:160]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tts failed: {e}")


@app.post("/api/preload/{contract_id}/{seg_idx}")
async def preload(contract_id: str, seg_idx: int, background_tasks: BackgroundTasks):
    idx = build_index(contract_id, _resolve_contract(contract_id))
    if seg_idx < 0 or seg_idx >= len(idx.segments):
        raise HTTPException(status_code=404, detail="seg_idx out of range")
    tts_text = normalize_for_tts(idx.segments[seg_idx].text)
    key = cache_key(tts_text, VOICE_REF_ID)
    if cache.has(key):
        return {"status": "cached", "seg_idx": seg_idx}

    async def _bg():
        try:
            async with _lock_for(key):
                if cache.has(key):
                    return
                buf = bytearray()
                async for chunk in engine.synth(tts_text):
                    buf.extend(chunk)
                cache.put(key, bytes(buf))
        except Exception as e:
            print(f"[preload seg {seg_idx}] failed: {e}", flush=True)

    background_tasks.add_task(_bg)
    return {"status": "preloading", "seg_idx": seg_idx}


# frontend/ is created in Task 10; guard so importing app (Task 8/9 tests) doesn't crash before then
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
