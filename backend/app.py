"""FastAPI orchestrator for the external multilingual contract-TTS service.

Callers POST a contract TXT + template_id, get back a content-addressed contract_id,
then fetch per-segment audio and seek. See CONTEXT.md and docs/adr/0001..0007.

Pipeline: upload → canonical Template lookup → compute_contract_id → store raw text
and Template metadata → profile-specific deterministic split → profile-specific
normalization → selected Engine Profile → content-addressed cache → audio/wav.
Seek maps a progress position onto a segment boundary.
"""
from __future__ import annotations
import asyncio
import os
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.storage.contract import (
    ContractStore,
    SegmentIndex,
    build_index,
    compute_contract_id,
)
from backend.storage.cache import SegmentCache, cache_key
from backend.engines.gptsovits_client import GPTSoVITSClient
from backend.engines.bailian_cosyvoice_client import BailianCosyVoiceClient
from backend.templates import (
    TemplateProfile,
    build_template_registry,
    canonical_template_id,
)

ROOT = Path(__file__).resolve().parent.parent


def _load_project_env(dotenv_path: Path = ROOT / ".env") -> None:
    """Load local defaults without replacing explicitly configured environment."""
    load_dotenv(dotenv_path=dotenv_path, override=False)


_load_project_env()

FRONTEND_DIR = ROOT / "frontend"
CACHE_DIR = ROOT / "cache"
UPLOADED_DIR = ROOT / "uploaded"


def _project_path_from_env(name: str, default: str) -> Path:
    """Resolve an environment-configured path relative to the project root."""
    path = Path(os.getenv(name, default)).expanduser()
    return path if path.is_absolute() else ROOT / path


# --- 本地引擎配置 ---
ENGINE_URL = os.getenv("GPTSOVITS_ENGINE_URL", "http://127.0.0.1:9880")
# NOTE: GPT-SoVITS 拒绝 3-10s 以外的参考音；用裁好的 7s 参考。
REF_AUDIO_PATH = _project_path_from_env(
    "GPTSOVITS_REF_AUDIO", "refs/cantonese_ref_trim.wav"
)
REF_PROMPT_PATH = _project_path_from_env(
    "GPTSOVITS_REF_PROMPT", "refs/cantonese_ref_trim.txt"
)
REF_AUDIO = str(REF_AUDIO_PATH)
REF_PROMPT = (
    REF_PROMPT_PATH.read_text(encoding="utf-8").strip()
    if REF_PROMPT_PATH.exists()
    else ""
)

# --- 引擎选择 ---
# 两个 client 都实现 synth(text) -> AsyncIterator[bytes]；归一化留在 app 层（共用
# normalizer.py），换引擎无需改动别处。
# CONTRACT_TTS_ENGINE = "gptsovits"（本地，默认）| "bailian"（云端 cosyvoice）。
ENGINE_NAME = os.getenv("CONTRACT_TTS_ENGINE", "gptsovits")
BAILIAN_VOICE = os.getenv("BAILIAN_VOICE", "longjiaxin_v3")  # 原生粤语
BAILIAN_VOICE_ZH = os.getenv("BAILIAN_VOICE_ZH", "longxiaochun")
BAILIAN_VOICE_EN = os.getenv("BAILIAN_VOICE_EN", "longanyang")
ENGINE_LANGUAGE_SETTINGS = {
    "yue": {"voice": BAILIAN_VOICE, "text_lang": "yue", "prompt_lang": "yue"},
    "zh": {"voice": BAILIAN_VOICE_ZH, "text_lang": "zh", "prompt_lang": "zh"},
    "en": {"voice": BAILIAN_VOICE_EN, "text_lang": "en", "prompt_lang": "en"},
}
ENGINE_PROFILE_CACHE_VERSIONS = {
    language: os.getenv(f"ENGINE_PROFILE_CACHE_VERSION_{language.upper()}", "v1")
    for language in ENGINE_LANGUAGE_SETTINGS
}


def make_engine(name: str | None = None, reading_language: str = "yue"):
    """构造 TTS 引擎。name=None -> 读 CONTRACT_TTS_ENGINE 环境变量（默认 gptsovits）。"""
    name = name or ENGINE_NAME
    settings = ENGINE_LANGUAGE_SETTINGS[reading_language]
    if name == "bailian":
        return BailianCosyVoiceClient(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            voice=settings["voice"],
        )
    return GPTSoVITSClient(
        ENGINE_URL,
        REF_AUDIO,
        REF_PROMPT,
        text_lang=settings["text_lang"],
        prompt_lang=settings["prompt_lang"],
    )


class ContractUpload(BaseModel):
    text: str
    template_id: str


cache = SegmentCache(CACHE_DIR)
CONTRACT_STORE = ContractStore(UPLOADED_DIR)
engine = make_engine()
TEMPLATE_REGISTRY = build_template_registry(
    engine_name=ENGINE_NAME,
    api_key=os.getenv("DASHSCOPE_API_KEY", ""),
    engine_provider=lambda: engine,
    engine_providers={
        "zh": lambda: make_engine(ENGINE_NAME, "zh"),
        "en": lambda: make_engine(ENGINE_NAME, "en"),
    },
    cache_versions=ENGINE_PROFILE_CACHE_VERSIONS,
)


# --- 过期清理（ADR-0007）---
# 启动时清一次 + 进程内 asyncio 周期任务（每天 1 次）。evict 同步直调、阻塞
# ~27ms/天（benchmark：稳态 ~25k 音频 + ~1.5k 原文 manifest），可接受；不丢 to_thread
# （会引入 manifest 跨线程竞态、需加锁）。规模增长致阻塞可感知时再上分批 / to_thread。
_CLEANUP_INTERVAL_S = 86400  # 每天一次（硬编码 v1）


def run_cleanup() -> None:
    """跑一次过期清理：原文（90d）+ 音频（30d）。同步直调（ADR-0007）；
    任一失败记日志、不抛（崩了下个周期照跑，最坏退化成只有启动清）。"""
    now = time.time()
    try:
        rm_text = CONTRACT_STORE.evict_expired(now)
        rm_audio = cache.evict_expired(now)
        if rm_text or rm_audio:
            print(f"[cleanup] evicted {rm_text} text / {rm_audio} audio", flush=True)
    except Exception as e:
        print(f"[cleanup] failed: {e}", flush=True)


async def _periodic_cleanup() -> None:
    """周期清理协程：每 _CLEANUP_INTERVAL_S 秒跑一次 run_cleanup（ADR-0007）。"""
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL_S)
        run_cleanup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时清一次过期项（ADR-0004），复用 run_cleanup（ADR-0007）。
    # 放 lifespan 而非模块级，避免 import（如测试）时误清开发机上的真实数据。
    run_cleanup()
    # 周期清理任务：挂 app.state 持引用防 GC；shutdown 时取消。
    app.state.cleanup_task = asyncio.create_task(_periodic_cleanup())
    try:
        yield
    finally:
        app.state.cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.cleanup_task


app = FastAPI(title="Cantonese Contract TTS Service", lifespan=lifespan)

# per-key 生成锁：并发的相同请求只合成一次
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(key: str) -> asyncio.Lock:
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def _profile_for_input(template_id: str) -> TemplateProfile:
    try:
        canonical = canonical_template_id(template_id, TEMPLATE_REGISTRY)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"unknown template_id: {template_id}")
    profile = TEMPLATE_REGISTRY[canonical]
    if not profile.engine_profile.available:
        raise HTTPException(status_code=503, detail=f"template profile unavailable: {canonical}")
    return profile


def _load_idx_or_404(contract_id: str, seg_idx: int | None = None) -> tuple[SegmentIndex, TemplateProfile]:
    """取原文并切片；contract_id 未知 → 404；seg_idx 给定且越界 → 404。"""
    text = CONTRACT_STORE.get(contract_id)
    template_id = CONTRACT_STORE.get_template_id(contract_id)
    if text is None or template_id is None:
        raise HTTPException(status_code=404, detail="unknown contract")
    profile = TEMPLATE_REGISTRY.get(template_id)
    if profile is None or not profile.engine_profile.available:
        raise HTTPException(status_code=404, detail="unknown contract")
    idx = build_index(
        contract_id,
        text,
        splitter=profile.splitter,
        duration_estimator=profile.duration_estimator,
    )
    if seg_idx is not None and (seg_idx < 0 or seg_idx >= len(idx.segments)):
        raise HTTPException(status_code=404, detail="seg_idx out of range")
    return idx, profile


def _cache_identity(profile: TemplateProfile, tts_text: str) -> str:
    engine_profile = profile.engine_profile
    return cache_key(
        profile.id,
        tts_text,
        engine_profile.id,
        engine_profile.cache_version,
    )


def _engine_for(profile: TemplateProfile):
    return profile.engine_profile.engine_provider()


async def _synth_and_cache(key: str, tts_text: str, selected_engine) -> bytes:
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
        async for chunk in selected_engine.synth(tts_text):
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
        idx, profile = _load_idx_or_404(contract_id, seg_idx)
        tts_text = profile.normalizer(idx.segments[seg_idx].text)
        key = _cache_identity(profile, tts_text)
        await _synth_and_cache(key, tts_text, _engine_for(profile))
    except Exception as e:
        print(f"[warm seg {seg_idx}] failed: {e}", flush=True)


@app.post("/api/contracts")
def upload_contract(body: ContractUpload, background_tasks: BackgroundTasks):
    profile = _profile_for_input(body.template_id)
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")
    cid = compute_contract_id(body.text, profile.id)
    CONTRACT_STORE.put(cid, body.text, template_id=profile.id)
    idx = build_index(
        cid,
        body.text,
        splitter=profile.splitter,
        duration_estimator=profile.duration_estimator,
    )
    # 预热 seg 0，让首次播放即点即响（前端上传后立即加载 seg 0）
    background_tasks.add_task(_warm_segment, cid, 0)
    return _index_response(idx)


@app.get("/api/contracts/{contract_id}")
def get_contract(contract_id: str):
    idx, _profile = _load_idx_or_404(contract_id)
    return _index_response(idx)


@app.get("/api/contracts/{contract_id}/segments/{seg_idx}")
async def get_segment(contract_id: str, seg_idx: int):
    idx, profile = _load_idx_or_404(contract_id, seg_idx)
    tts_text = profile.normalizer(idx.segments[seg_idx].text)
    key = _cache_identity(profile, tts_text)
    # 整段合成完再返回：引擎失败时能回明确的 502/500，而不是被浏览器吞成空 200（"Load failed"）。
    try:
        data = await _synth_and_cache(key, tts_text, _engine_for(profile))
        return Response(data, media_type="audio/wav")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"engine {e.response.status_code}: {e.response.text[:160]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tts failed: {e}")


@app.post("/api/contracts/{contract_id}/segments/{seg_idx}/preload")
async def preload(contract_id: str, seg_idx: int, background_tasks: BackgroundTasks):
    idx, profile = _load_idx_or_404(contract_id, seg_idx)
    tts_text = profile.normalizer(idx.segments[seg_idx].text)
    key = _cache_identity(profile, tts_text)
    if cache.has(key):
        return {"status": "cached", "seg_idx": seg_idx}

    async def _bg():
        try:
            await _synth_and_cache(key, tts_text, _engine_for(profile))
        except Exception as e:
            print(f"[preload seg {seg_idx}] failed: {e}", flush=True)

    background_tasks.add_task(_bg)
    return {"status": "preloading", "seg_idx": seg_idx}


# frontend/ 是上传 demo；守卫一下，frontend 缺失时 import app（测试）也不崩
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
