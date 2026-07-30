"""FastAPI orchestrator for the external Cantonese contract-TTS service.

Callers POST a contract TXT + template_id, get back a content-addressed contract_id,
then fetch per-segment audio and seek. See CONTEXT.md and docs/adr/0001..0006.

Pipeline: upload → compute_contract_id → store raw text → build_index (deterministic
split) → normalize_for_tts (per segment, on demand) → engine.synth → content-addressed
cache → audio/wav. Seek maps a progress position onto a segment boundary.
"""
from __future__ import annotations
import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from seek_probe.backend.contract import build_index, compute_contract_id, ContractStore, SegmentIndex
from seek_probe.backend.cache import cache_key, SegmentCache
from seek_probe.backend.gptsovits_client import GPTSoVITSClient
from seek_probe.backend.bailian_cosyvoice_client import BailianCosyVoiceClient
from seek_probe.backend.normalizer import normalize_for_tts

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
CACHE_DIR = ROOT / "cache"
UPLOADED_DIR = ROOT / "uploaded"

# --- 探针配置（硬编码） ---
ENGINE_URL = "http://127.0.0.1:9880"
# NOTE: GPT-SoVITS 拒绝 3-10s 以外的参考音；用裁好的 7s 参考。
REF_AUDIO = str(ROOT / "refs" / "cantonese_ref_trim.wav")
REF_PROMPT = (ROOT / "refs" / "cantonese_ref_trim.txt").read_text(encoding="utf-8").strip() \
    if (ROOT / "refs" / "cantonese_ref_trim.txt").exists() else ""
VOICE_REF_ID = "cantonese_ref_v1"

# --- 引擎选择 ---
# 两个 client 都实现 synth(text) -> AsyncIterator[bytes]；归一化留在 app 层（共用
# normalizer.py），换引擎无需改动别处。
# SEEK_PROBE_ENGINE = "gptsovits"（本地，默认）| "bailian"（云端 cosyvoice）。
ENGINE_NAME = os.getenv("SEEK_PROBE_ENGINE", "gptsovits")
BAILIAN_VOICE = os.getenv("BAILIAN_VOICE", "longjiaxin_v3")  # 原生粤语（粤语/英文）

# 已知如何切片/归一化的模板。v1：仅 xcash（ADR-0005）。
KNOWN_TEMPLATES = {"xcash"}


def make_engine(name: str | None = None):
    """构造 TTS 引擎。name=None -> 读 SEEK_PROBE_ENGINE 环境变量（默认 gptsovits）。"""
    name = name or ENGINE_NAME
    if name == "bailian":
        return BailianCosyVoiceClient(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            voice=BAILIAN_VOICE,
        )
    return GPTSoVITSClient(ENGINE_URL, REF_AUDIO, REF_PROMPT)


class ContractUpload(BaseModel):
    text: str
    template_id: str


cache = SegmentCache(CACHE_DIR)
CONTRACT_STORE = ContractStore(UPLOADED_DIR)
engine = make_engine()


@asynccontextmanager
async def lifespan(app):
    # 启动时清一次过期项（ADR-0004：音频 30 天滑动窗口、原文 90 天）。
    # 放 lifespan 而非模块级，避免 import（如测试）时误清开发机上的真实数据。
    now = time.time()
    cache.evict_expired(now)
    CONTRACT_STORE.evict_expired(now)
    yield


app = FastAPI(title="Cantonese Contract TTS Service", lifespan=lifespan)

# per-key 生成锁：并发的相同请求只合成一次
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(key: str) -> asyncio.Lock:
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def _load_idx_or_404(contract_id: str, seg_idx: int | None = None) -> SegmentIndex:
    """取原文并切片；contract_id 未知 → 404；seg_idx 给定且越界 → 404。"""
    text = CONTRACT_STORE.get(contract_id)
    if text is None:
        raise HTTPException(status_code=404, detail="unknown contract")
    idx = build_index(contract_id, text)
    if seg_idx is not None and (seg_idx < 0 or seg_idx >= len(idx.segments)):
        raise HTTPException(status_code=404, detail="seg_idx out of range")
    return idx


async def _synth_and_cache(key: str, tts_text: str) -> bytes:
    """合成音频并写入缓存，返回字节。命中缓存则直接读回；未命中则在 per-key 锁内
    合成（并发的相同请求只合成一次）。"""
    cached = cache.get(key)
    if cached is not None:
        return cached.read_bytes()
    async with _lock_for(key):
        cached_again = cache.get(key)            # 拿锁后二次查，去并发重复合成
        if cached_again is not None:
            return cached_again.read_bytes()
        buf = bytearray()
        async for chunk in engine.synth(tts_text):
            buf.extend(chunk)
        data = bytes(buf)
        cache.put(key, data)
        return data


def _index_response(idx: SegmentIndex) -> dict:
    # 不回传段文本——调用方手里已有上传的原文，回传只会让 PII 多过一趟网（ADR-0001）。
    return {
        "contract_id": idx.contract_id,
        "total_est_s": idx.total_est_s,
        "segments": [
            {"seg_idx": m.seg_idx, "est_dur_s": m.est_dur_s, "cumulative_start_s": m.cumulative_start_s}
            for m in idx.segments
        ],
    }


async def _warm_segment(contract_id: str, seg_idx: int) -> None:
    """后台把某段音频合成入缓存（上传时用于预热 seg 0）。"""
    try:
        idx = _load_idx_or_404(contract_id, seg_idx)
        tts_text = normalize_for_tts(idx.segments[seg_idx].text)
        key = cache_key(tts_text, VOICE_REF_ID, ENGINE_NAME)
        await _synth_and_cache(key, tts_text)
    except Exception as e:
        print(f"[warm seg {seg_idx}] failed: {e}", flush=True)


@app.post("/api/contracts")
def upload_contract(body: ContractUpload, background_tasks: BackgroundTasks):
    if body.template_id not in KNOWN_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"unknown template_id: {body.template_id}")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")
    cid = compute_contract_id(body.text, body.template_id)
    CONTRACT_STORE.put(cid, body.text)
    idx = build_index(cid, body.text)
    # 预热 seg 0，让首次播放即点即响（前端上传后立即加载 seg 0）
    background_tasks.add_task(_warm_segment, cid, 0)
    return _index_response(idx)


@app.get("/api/contracts/{contract_id}")
def get_contract(contract_id: str):
    return _index_response(_load_idx_or_404(contract_id))


@app.get("/api/contracts/{contract_id}/segments/{seg_idx}")
async def get_segment(contract_id: str, seg_idx: int):
    idx = _load_idx_or_404(contract_id, seg_idx)
    tts_text = normalize_for_tts(idx.segments[seg_idx].text)   # 阿拉伯数字 → 中文，确保读法正确
    key = cache_key(tts_text, VOICE_REF_ID, ENGINE_NAME)
    # 整段合成完再返回：引擎失败时能回明确的 502/500，而不是被浏览器吞成空 200（"Load failed"）。
    try:
        data = await _synth_and_cache(key, tts_text)
        return Response(data, media_type="audio/wav")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"engine {e.response.status_code}: {e.response.text[:160]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tts failed: {e}")


@app.post("/api/contracts/{contract_id}/segments/{seg_idx}/preload")
async def preload(contract_id: str, seg_idx: int, background_tasks: BackgroundTasks):
    idx = _load_idx_or_404(contract_id, seg_idx)
    tts_text = normalize_for_tts(idx.segments[seg_idx].text)
    key = cache_key(tts_text, VOICE_REF_ID, ENGINE_NAME)
    if cache.has(key):
        return {"status": "cached", "seg_idx": seg_idx}

    async def _bg():
        try:
            await _synth_and_cache(key, tts_text)
        except Exception as e:
            print(f"[preload seg {seg_idx}] failed: {e}", flush=True)

    background_tasks.add_task(_bg)
    return {"status": "preloading", "seg_idx": seg_idx}


# frontend/ 是上传 demo；守卫一下，frontend 缺失时 import app（测试）也不崩
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
