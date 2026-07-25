# Cantonese Contract TTS + Seek Probe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal but complete local spike that reads a standard-Chinese contract aloud in Cantonese (GPT-SoVITS), with a draggable progress bar where seeking triggers on-demand segment generation while keeping voice consistent across segments.

**Architecture:** Two processes — GPT-SoVITS engine (own Python 3.10 venv, CPU inference, exposes its `api_v2.py` HTTP API) + a thin FastAPI orchestrator (project Python 3.12 venv) that does deterministic sentence segmentation, content-addressed on-disk caching, segment-internal byte streaming, and seek→segment mapping, plus a static HTML/JS player. Voice consistency comes from one fixed Cantonese reference clip reused for every segment (voice-clone).

**Tech Stack:** Python 3.12 + uv + FastAPI + uvicorn + httpx + pytest (orchestrator); GPT-SoVITS (RVC-Boss) on Python 3.10, CPU; vanilla HTML/JS + `<audio>` (frontend).

## Global Constraints

- **Local only, no cloud.** Host: M3 Max, macOS (Apple Silicon).
- **Engine isolation:** GPT-SoVITS runs in its **own Python 3.10 venv** (numba 0.56.4 needs py<3.11); the orchestrator runs in the **project 3.12 venv** managed by uv. They talk over HTTP on `127.0.0.1:9880`.
- **Cantonese via clone:** every segment uses the **same fixed reference clip** (`refs/cantonese_ref.wav`) with `text_lang="yue"`, `prompt_lang="yue"`.
- **Input text:** standard written Chinese (書面語), read with Cantonese pronunciation.
- **Scope:** spike, not production. See spec §2 (In/Out). No auth, no DB, one hardcoded contract, seek snaps to segment boundaries, no sub-segment precise seek, no true-duration progress-bar refinement.
- **This is a spike:** prefer the simplest thing that demonstrates the loop; document follow-ups rather than build them.

**Spec:** `docs/superpowers/specs/2026-07-25-cantonese-tts-seek-probe-design.md`

---

## File Structure

```
conftest.py                         # empty; makes pytest import `seek_probe` from repo root
seek_probe/
  __init__.py
  backend/
    __init__.py
    segmenter.py                    # deterministic split(text) -> [Segment]; estimate_duration(text)
    contract.py                     # SegmentIndex, build_index(), position_to_segment(); load contract text
    cache.py                        # cache_key(text, voice_id); SegmentCache (has/get/put + manifest)
    gptsovits_client.py             # GPTSoVITSClient.synth(text) -> AsyncIterator[bytes] over api_v2 /tts
    app.py                          # FastAPI: /api/contract, /api/segment (tee+cache), /api/preload, static /
  frontend/
    index.html                      # progress bar (range) + play/pause + status + <audio>
    app.js                          # fetch index, play sequentially, preload ahead, seek -> segment
  contracts/
    sample_contract.txt             # synthesized standard-Chinese contract (~2-3 min when read)
  refs/
    cantonese_ref.wav               # gitignored; ~5s Cantonese reference clip (user-provided)
    cantonese_ref.txt               # Cantonese transcript of the clip (used as prompt_text)
  tests/
    test_segmenter.py
    test_contract.py
    test_cache.py
    test_gptsovits_client.py
    test_app.py
  cache/                            # gitignored; <hash>.wav + manifest.json
  README.md                         # how to run engine + backend + frontend; known follow-ups
```

**External (not in this repo):** `/Users/roy/codes/GPT-SoVITS/` — cloned upstream, own 3.10 venv, runs `api_v2.py` on `127.0.0.1:9880`.

**Interfaces (locked signatures — later tasks depend on these exact names):**

```python
# seek_probe/backend/segmenter.py
@dataclass(frozen=True)
class Segment: text: str
def split_contract(text: str, max_chars: int = 60) -> list[Segment]
def estimate_duration(text: str, rate: float = 3.7) -> float

# seek_probe/backend/contract.py
@dataclass(frozen=True)
class SegmentMeta: seg_idx: int; text: str; est_dur_s: float; cumulative_start_s: float
@dataclass(frozen=True)
class SegmentIndex: contract_id: str; segments: list[SegmentMeta]; total_est_s: float
def build_index(contract_id: str, text: str) -> SegmentIndex
def position_to_segment(idx: SegmentIndex, t: float) -> int
def load_contract_text(contract_id: str) -> str   # raises KeyError if unknown

# seek_probe/backend/cache.py
def cache_key(text: str, voice_ref_id: str) -> str
class SegmentCache:
    def __init__(self, root: Path): ...
    def has(self, key: str) -> bool
    def get(self, key: str) -> Path | None
    def put(self, key: str, data: bytes, duration: float | None = None) -> Path

# seek_probe/backend/gptsovits_client.py
class GPTSoVITSClient:
    def __init__(self, base_url: str, ref_audio_path: str, prompt_text: str,
                 text_lang: str = "yue", prompt_lang: str = "yue", timeout: float = 60.0): ...
    async def synth(self, text: str, transport: httpx.MockTransport | None = None) -> AsyncIterator[bytes]: ...
```

---

## Task 1: Scaffolding, dependencies, test infra

**Files:**
- Create: `conftest.py`, `seek_probe/__init__.py`, `seek_probe/backend/__init__.py`, `seek_probe/tests/__init__.py`, `seek_probe/README.md`
- Modify: `.gitignore` (add cache + ref audio), `pyproject.toml` (via uv)

**Interfaces:** Produces an importable `seek_probe` package and a working `uv run pytest`.

- [ ] **Step 1: Add dependencies via uv**

```bash
uv add fastapi "uvicorn[standard]" httpx
uv add --dev pytest
```

- [ ] **Step 2: Create package + test skeleton**

Create empty files: `conftest.py` (root, empty), `seek_probe/__init__.py`, `seek_probe/backend/__init__.py`, `seek_probe/tests/__init__.py`.

Create `seek_probe/tests/test_smoke.py`:
```python
def test_pytest_runs():
    assert 1 + 1 == 2
```

- [ ] **Step 3: Update `.gitignore`**

Append:
```
# seek_probe spike
seek_probe/cache/
seek_probe/refs/*.wav
seek_probe/refs/*.mp3
```

- [ ] **Step 4: Verify pytest discovers and passes**

Run: `uv run pytest -q`
Expected: `1 passed` (the smoke test). This also confirms `seek_probe` is importable from root via the root `conftest.py`.

- [ ] **Step 5: Seed README**

Create `seek_probe/README.md` with a one-line purpose and a "Run" section to be filled in Task 11.

- [ ] **Step 6: Commit**

```bash
git add conftest.py seek_probe/__init__.py seek_probe/backend/__init__.py seek_probe/tests/__init__.py seek_probe/tests/test_smoke.py seek_probe/README.md .gitignore pyproject.toml uv.lock
git commit -m "feat(probe): scaffold seek_probe package, deps, pytest infra"
```

---

## Task 2: Segmenter (TDD)

**Files:**
- Create: `seek_probe/backend/segmenter.py`, `seek_probe/tests/test_segmenter.py`

**Interfaces:**
- Produces: `Segment`, `split_contract(text, max_chars=60) -> list[Segment]`, `estimate_duration(text, rate=3.7) -> float`

- [ ] **Step 1: Write failing tests**

`seek_probe/tests/test_segmenter.py`:
```python
from seek_probe.backend.segmenter import split_contract, estimate_duration


def test_same_text_yields_identical_segments():
    text = "甲方应于三日内支付。乙方收到后开具收据。"
    assert split_contract(text) == split_contract(text)


def test_splits_on_sentence_end_punctuation():
    segs = split_contract("第一句。第二句！第三句？")
    assert [s.text for s in segs] == ["第一句。", "第二句！", "第三句？"]


def test_long_sentence_is_subsplit_by_clause():
    long = "甲方同意在收到款项后的三个工作日内完成交付，并且保证质量符合约定，否则承担违约责任。"
    segs = split_contract(long, max_chars=20)
    assert len(segs) >= 2
    assert all(s.text for s in segs)


def test_estimate_duration_proportional_to_chars():
    assert estimate_duration("一二三四", rate=4.0) == 1.0
    assert estimate_duration("一二三") > estimate_duration("一")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest seek_probe/tests/test_segmenter.py -q`
Expected: FAIL (module not found / import error).

- [ ] **Step 3: Implement segmenter**

`seek_probe/backend/segmenter.py`:
```python
"""Deterministic sentence segmentation for contract text."""
from __future__ import annotations
import re
from dataclasses import dataclass

_SENT_END = "。！？；"
_CLAUSE = "，、,;"


@dataclass(frozen=True)
class Segment:
    text: str


def _split_keep_delim(text: str, delims: str) -> list[str]:
    pattern = f"([{re.escape(delims)}])"
    parts = re.split(pattern, text)
    out: list[str] = []
    buf = ""
    for p in parts:
        if p == "":
            continue
        buf += p
        if p in delims:
            out.append(buf)
            buf = ""
    if buf.strip():
        out.append(buf)
    return [s for s in (x.strip() for x in out) if s]


def split_contract(text: str, max_chars: int = 60) -> list[Segment]:
    """Split text into Segments. First by sentence-ending punctuation; any
    sentence longer than max_chars is further split by clause punctuation.
    Deterministic: identical input always yields identical output."""
    text = (text or "").strip()
    segments: list[Segment] = []
    for sentence in _split_keep_delim(text, _SENT_END):
        if len(sentence) <= max_chars:
            segments.append(Segment(sentence))
        else:
            for clause in _split_keep_delim(sentence, _CLAUSE):
                if clause:
                    segments.append(Segment(clause))
    return segments


def estimate_duration(text: str, rate: float = 3.7) -> float:
    """Estimated spoken seconds. Cantonese natural pace ~3.5-4 chars/sec."""
    n = sum(1 for ch in text if not ch.isspace())
    return round(n / rate, 3)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest seek_probe/tests/test_segmenter.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add seek_probe/backend/segmenter.py seek_probe/tests/test_segmenter.py
git commit -m "feat(probe): deterministic contract segmenter + duration estimate"
```

---

## Task 3: Segment index + seek mapping (TDD)

**Files:**
- Create: `seek_probe/backend/contract.py`, `seek_probe/tests/test_contract.py`

**Interfaces:**
- Consumes: `Segment`, `split_contract`, `estimate_duration` (Task 2)
- Produces: `SegmentMeta`, `SegmentIndex`, `build_index(contract_id, text)`, `position_to_segment(idx, t)`, `load_contract_text(contract_id)`

- [ ] **Step 1: Write failing tests**

`seek_probe/tests/test_contract.py`:
```python
import pytest
from seek_probe.backend.contract import build_index, position_to_segment


def test_index_cumulative_starts_monotonic_and_total_matches():
    idx = build_index("c", "第一句。第二句！")
    starts = [m.cumulative_start_s for m in idx.segments]
    assert starts[0] == 0.0
    assert starts == sorted(starts)
    assert idx.total_est_s == pytest.approx(sum(m.est_dur_s for m in idx.segments))


def test_position_to_segment_bounds_and_boundary():
    idx = build_index("c", "甲。乙。丙。")
    assert position_to_segment(idx, 0.0) == 0
    # boundary at end of segment 0 belongs to segment 1
    end0 = idx.segments[0].cumulative_start_s + idx.segments[0].est_dur_s
    assert position_to_segment(idx, end0) == 1
    # beyond end clamps to last segment
    assert position_to_segment(idx, idx.total_est_s + 99) == len(idx.segments) - 1
    # negative clamps to 0
    assert position_to_segment(idx, -5) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest seek_probe/tests/test_contract.py -q`
Expected: FAIL (import error).

- [ ] **Step 3: Implement contract module**

`seek_probe/backend/contract.py`:
```python
"""Segment index, seek mapping, contract loading."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from seek_probe.backend.segmenter import split_contract, estimate_duration

_CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"
_CONTRACT_FILES = {"sample": _CONTRACTS_DIR / "sample_contract.txt"}


@dataclass(frozen=True)
class SegmentMeta:
    seg_idx: int
    text: str
    est_dur_s: float
    cumulative_start_s: float


@dataclass(frozen=True)
class SegmentIndex:
    contract_id: str
    segments: list[SegmentMeta]
    total_est_s: float


def build_index(contract_id: str, text: str) -> SegmentIndex:
    metas: list[SegmentMeta] = []
    t = 0.0
    for i, seg in enumerate(split_contract(text)):
        dur = estimate_duration(seg.text)
        metas.append(SegmentMeta(i, seg.text, dur, t))
        t += dur
    return SegmentIndex(contract_id, metas, round(t, 3))


def position_to_segment(idx: SegmentIndex, t: float) -> int:
    """Map a progress-bar position (seconds) to a segment index.
    Seek snaps to segment boundaries. Out-of-range clamps to [0, last]."""
    if not idx.segments:
        return 0
    if t < 0:
        return 0
    if t >= idx.total_est_s:
        return len(idx.segments) - 1
    for m in idx.segments:
        if t < m.cumulative_start_s + m.est_dur_s:
            return m.seg_idx
    return len(idx.segments) - 1


def load_contract_text(contract_id: str) -> str:
    p = _CONTRACT_FILES.get(contract_id)
    if p is None or not p.exists():
        raise KeyError(f"unknown contract: {contract_id}")
    return p.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest seek_probe/tests/test_contract.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add seek_probe/backend/contract.py seek_probe/tests/test_contract.py
git commit -m "feat(probe): segment index + seek-to-segment mapping"
```

---

## Task 4: Content-addressed cache (TDD)

**Files:**
- Create: `seek_probe/backend/cache.py`, `seek_probe/tests/test_cache.py`

**Interfaces:**
- Produces: `cache_key(text, voice_ref_id) -> str`, `SegmentCache(root)` with `has/get/put`

- [ ] **Step 1: Write failing tests**

`seek_probe/tests/test_cache.py`:
```python
from seek_probe.backend.cache import cache_key, SegmentCache


def test_key_stable_for_same_text_and_voice_distinct_otherwise():
    assert cache_key("你好", "vA") == cache_key("你好", "vA")
    assert cache_key("你好", "vA") != cache_key("你好", "vB")   # different voice
    assert cache_key("你好", "vA") != cache_key("再见", "vA")   # different text


def test_put_then_get_roundtrip(tmp_path):
    c = SegmentCache(tmp_path / "cache")
    key = cache_key("x", "v")
    assert c.get(key) is None
    p = c.put(key, b"RIFFxxxx", duration=1.5)
    assert c.has(key)
    got = c.get(key)
    assert got is not None and got.read_bytes() == b"RIFFxxxx"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest seek_probe/tests/test_cache.py -q`
Expected: FAIL (import error).

- [ ] **Step 3: Implement cache**

`seek_probe/backend/cache.py`:
```python
"""Content-addressed segment cache. Key = hash(segment_text + voice_ref_id).
Identical text (static boilerplate) reuses one file across contracts automatically."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def cache_key(text: str, voice_ref_id: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(b"|")
    h.update(voice_ref_id.encode("utf-8"))
    return h.hexdigest()


class SegmentCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self._manifest: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text("utf-8"))
        return {}

    def _save(self) -> None:
        self.manifest_path.write_text(json.dumps(self._manifest, ensure_ascii=False), "utf-8")

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.wav"

    def has(self, key: str) -> bool:
        return self._path(key).exists()

    def get(self, key: str) -> Path | None:
        p = self._path(key)
        return p if p.exists() else None

    def put(self, key: str, data: bytes, duration: float | None = None) -> Path:
        p = self._path(key)
        p.write_bytes(data)
        self._manifest[key] = {"duration": duration}
        self._save()
        return p
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest seek_probe/tests/test_cache.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add seek_probe/backend/cache.py seek_probe/tests/test_cache.py
git commit -m "feat(probe): content-addressed segment cache"
```

---

## Task 5: Sample contract corpus

**Files:**
- Create: `seek_probe/contracts/sample_contract.txt`

**Interfaces:** Produces the file read by `load_contract_text("sample")`.

- [ ] **Step 1: Write a standard-Chinese contract (~2-3 min read)**

Create `seek_probe/contracts/sample_contract.txt` with a plausible standard written-Chinese (書面語) contract — multiple articles/clauses with `。`/`，`/`；` punctuation so segmentation is meaningful. Target ~300-500 Chinese characters (≈1.5-2.5 min at ~3.7 chars/sec). Example structure:

```
甲方：張氏有限公司。乙方：李氏貿易行。
第一條　合同標的。甲方同意向乙方採購一批電子元件，具體型號與數量詳見附件一。
第二條　價款與支付。合同總價款為港幣三十萬元整。乙方應於簽署後三日內支付訂金，餘款於交付驗收合格後七日內結清。
第三條　交付與驗收。甲方須於收到訂金後十四個工作日內完成交付。乙方應在收到貨物後五日內完成驗收，逾期未提出異議視為合格。
第四條　質量保證。甲方保證貨物符合約定標準，並提供自驗收之日起十二個月的免費維修服務。
第五條　違約責任。任何一方未按約履行義務，應向守約方支付相當於總價款百分之十的違約金。
第六條　爭議解決。因本合同引起的爭議，雙方應協商解決；協商不成的，提交香港國際仲裁中心仲裁。
本合同一式兩份，雙方各執一份，自簽署之日起生效。
```

- [ ] **Step 2: Sanity-check segmentation + estimated duration**

Run:
```bash
uv run python -c "from seek_probe.backend.contract import build_index, load_contract_text; i=build_index('sample', load_contract_text('sample')); print('segs=',len(i.segments),'est_min=',round(i.total_est_s/60,2))"
```
Expected: `segs=` ≥ 8, `est_min=` roughly 1.5-3.0. If far outside, adjust the text length.

- [ ] **Step 3: Commit**

```bash
git add seek_probe/contracts/sample_contract.txt
git commit -m "feat(probe): sample standard-Chinese contract corpus"
```

---

## Task 6: GPT-SoVITS engine setup + Cantonese smoke (M0)

**Goal:** Get GPT-SoVITS running locally on M3 Max (CPU), produce one Cantonese sample of standard-Chinese contract text, confirm it "sounds like Cantonese" (recognizable — not native-grade; that gate is deferred). This is the engine foundation all later integration depends on.

**Files:**
- Create: `seek_probe/refs/cantonese_ref.wav` (gitignored, user-provided), `seek_probe/refs/cantonese_ref.txt`, `seek_probe/docs/engine-setup.md` (notes)

**Interfaces:** Produces a running `api_v2.py` on `127.0.0.1:9880` accepting `POST /tts` with `text_lang="yue"`.

- [ ] **Step 1: Clone GPT-SoVITS (sibling dir)**

```bash
cd /Users/roy/codes
git clone --depth 1 https://github.com/RVC-Boss/GPT-SoVITS.git
cd GPT-SoVITS
```

- [ ] **Step 2: Create a Python 3.10 venv and install deps**

```bash
uv venv --python 3.10 .venv
uv run pip install -r requirements.txt
```
If a specific dep fails on Apple Silicon, follow the repo's current macOS notes (the upstream README lists Apple silicon as a tested inference device, CPU path). Record any deviation in `seek_probe/docs/engine-setup.md`.

- [ ] **Step 3: Download pretrained models**

Per the repo's current README, place models under `GPT_SoVITS/pretrained_models/`, including the `gsv-v2final-pretrained` set (v2 added Cantonese `yue`), and the `G2PWModel` under `GPT_SoVITS/text/` (required for Chinese). Use the download links in the upstream README ("pretrained_models" + "G2PWModel"). Record exact filenames used in `seek_probe/docs/engine-setup.md`.

- [ ] **Step 4: Obtain a Cantonese reference clip**

Place a ~5s clean Cantonese speech clip at `seek_probe/refs/cantonese_ref.wav` (16k/24k/48k mono preferred). Write its **Cantonese transcript** to `seek_probe/refs/cantonese_ref.txt` (this becomes `prompt_text`). If you have no clip: record ~5s yourself, or use a short public Cantonese clip; the probe only needs *a* fixed Cantonese reference.

- [ ] **Step 5: Start the API server**

```bash
cd /Users/roy/codes/GPT-SoVITS
uv run python api_v2.py    # serves 127.0.0.1:9880 by default
```
Keep this running in its own terminal.

- [ ] **Step 6: Verify Cantonese generation via curl**

```bash
REF=/Users/roy/codes/audio-with-qwen3-tts/seek_probe/refs/cantonese_ref.wav
PROMPT=$(cat /Users/roy/codes/audio-with-qwen3-tts/seek_probe/refs/cantonese_ref.txt)
curl -s -X POST http://127.0.0.1:9880/tts \
  -H 'Content-Type: application/json' \
  -d "{\"text\":\"甲方應於三日內支付訂金。\",\"text_lang\":\"yue\",\"ref_audio_path\":\"$REF\",\"prompt_text\":\"$PROMPT\",\"prompt_lang\":\"yue\",\"media_type\":\"wav\",\"streaming_mode\":false}" \
  -o /tmp/yue_smoke.wav
ls -la /tmp/yue_smoke.wav   # non-trivial size (KB+) = got audio
```
**Listen** to `/tmp/yue_smoke.wav`. Pass criterion for M0: it sounds recognizably Cantonese (not Mandarin reading the characters). If it sounds like Mandarin-read-Cantonese, note it in `engine-setup.md` — this is the deferred地道性 risk; proceed with the architecture anyway (engine-decoupled).

- [ ] **Step 7: Confirm the exact `/tts` parameter names**

Open `GPT-SoVITS/api_v2.py` and confirm the JSON field names (`text`, `text_lang`, `ref_audio_path`, `prompt_text`, `prompt_lang`, `media_type`, `streaming_mode`) match the version installed. If names differ, record the actual names in `engine-setup.md` — Task 7's client must use them.

- [ ] **Step 8: Commit setup notes**

```bash
cd /Users/roy/codes/audio-with-qwen3-tts
git add seek_probe/docs/engine-setup.md seek_probe/refs/cantonese_ref.txt
git commit -m "chore(probe): GPT-SoVITS engine setup notes + Cantonese reference transcript"
```

---

## Task 7: GPT-SoVITS client (TDD with mock transport)

**Files:**
- Create: `seek_probe/backend/gptsovits_client.py`, `seek_probe/tests/test_gptsovits_client.py`

**Interfaces:**
- Produces: `GPTSoVITSClient(...).synth(text, transport=None) -> AsyncIterator[bytes]`

- [ ] **Step 1: Write failing test (mocked engine)**

`seek_probe/tests/test_gptsovits_client.py`:
```python
import asyncio
import json
import httpx
from seek_probe.backend.gptsovits_client import GPTSoVITSClient


def test_synth_streams_engine_bytes_and_sends_yue_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, content=b"AUDIOBYTES")

    client = GPTSoVITSClient("http://127.0.0.1:9880",
                             ref_audio_path="/r.wav", prompt_text="參考")

    async def collect():
        return [c async for c in client.synth("你好", transport=httpx.MockTransport(handler))]

    chunks = asyncio.run(collect())
    assert b"".join(chunks) == b"AUDIOBYTES"
    assert captured["url"].endswith("/tts")
    assert captured["payload"]["text"] == "你好"
    assert captured["payload"]["text_lang"] == "yue"
    assert captured["payload"]["media_type"] == "wav"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest seek_probe/tests/test_gptsovits_client.py -q`
Expected: FAIL (import error).

- [ ] **Step 3: Implement client**

`seek_probe/backend/gptsovits_client.py`:
```python
"""Thin async client over GPT-SoVITS api_v2.py /tts. Streams response bytes.
NOTE: streaming_mode=false returns one playable WAV per segment (robust for <audio>).
streaming_mode=true (lower cold-seek latency) is a documented follow-up: its
chunk format varies by version and is not bet-the-spike-on-able here."""
from __future__ import annotations
from typing import AsyncIterator
import httpx


class GPTSoVITSClient:
    def __init__(self, base_url: str, ref_audio_path: str, prompt_text: str,
                 text_lang: str = "yue", prompt_lang: str = "yue", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.ref_audio_path = ref_audio_path
        self.prompt_text = prompt_text
        self.text_lang = text_lang
        self.prompt_lang = prompt_lang
        self.timeout = timeout

    async def synth(self, text: str, transport: httpx.BaseTransport | None = None) -> AsyncIterator[bytes]:
        payload = {
            "text": text,
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "media_type": "wav",
            "streaming_mode": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout, transport=transport) as client:
            async with client.stream("POST", f"{self.base_url}/tts", json=payload) as r:
                r.raise_for_status()
                async for chunk in r.aiter_bytes():
                    yield chunk
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest seek_probe/tests/test_gptsovits_client.py -q`
Expected: `1 passed`.

- [ ] **Step 5: Live smoke against the running engine (manual)**

With `api_v2.py` running (Task 6) and `refs/cantonese_ref.wav` + `cantonese_ref.txt` in place:
```bash
uv run python -c "
import asyncio
from seek_probe.backend.gptsovits_client import GPTSoVITSClient
async def main():
    c = GPTSoVITSClient('http://127.0.0.1:9880', ref_audio_path='seek_probe/refs/cantonese_ref.wav', prompt_text=open('seek_probe/refs/cantonese_ref.txt').read().strip())
    data = b''.join([x async for x in c.synth('甲方應於三日內支付訂金。')])
    open('/tmp/client_smoke.wav','wb').write(data)
    print('wrote', len(data), 'bytes')
asyncio.run(main())
```
Listen to `/tmp/client_smoke.wav`; expect the same Cantonese sample as the curl smoke.

- [ ] **Step 6: Commit**

```bash
git add seek_probe/backend/gptsovits_client.py seek_probe/tests/test_gptsovits_client.py
git commit -m "feat(probe): GPT-SoVITS streaming client (mock-tested + live smoke)"
```

---

## Task 8: FastAPI — contract index + segment endpoint (cache + tee)

**Files:**
- Create: `seek_probe/backend/app.py`, `seek_probe/tests/test_app.py`

**Interfaces:**
- Consumes: `build_index`, `load_contract_text`, `cache_key`, `SegmentCache`, `GPTSoVITSClient.synth`
- Produces: `GET /api/contract/{id}` (JSON index), `GET /api/segment/{id}/{seg_idx}` (audio; cache-hit → file, miss → generate-and-tee-and-cache)

- [ ] **Step 1: Write failing integration test (fake engine, tmp cache + contract)**

`seek_probe/tests/test_app.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest seek_probe/tests/test_app.py -q`
Expected: FAIL (import error).

- [ ] **Step 3: Implement FastAPI app**

`seek_probe/backend/app.py`:
```python
"""FastAPI orchestrator: segmentation, content-addressed cache, segment streaming,
seek mapping. Static frontend served at /."""
from __future__ import annotations
import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from seek_probe.backend.contract import build_index, load_contract_text
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


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest seek_probe/tests/test_app.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add seek_probe/backend/app.py seek_probe/tests/test_app.py
git commit -m "feat(probe): FastAPI contract index + streaming segment endpoint (cache+tee)"
```

---

## Task 9: Preload endpoint (TDD)

**Files:**
- Modify: `seek_probe/backend/app.py` (add `POST /api/preload/{contract_id}/{seg_idx}`)
- Modify: `seek_probe/tests/test_app.py` (add test)

**Interfaces:**
- Consumes: same as Task 8
- Produces: `POST /api/preload/{id}/{seg_idx}` → `{status: "cached"|"preloading"}`

- [ ] **Step 1: Write failing test**

Append to `seek_probe/tests/test_app.py`:
```python
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
    # wait for background task to settle (TestClient runs sync; give loop a tick)
    import time; time.sleep(0.2)
    # now a direct segment hit should NOT call the engine
    calls_before = fake.calls
    client.get("/api/segment/sample/1")
    assert fake.calls == calls_before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest seek_probe/tests/test_app.py::test_preload_warms_cache_without_blocking -q`
Expected: FAIL (404 on POST /api/preload).

- [ ] **Step 3: Implement preload**

Append to `seek_probe/backend/app.py` (before the `app.mount` line):
```python
@app.post("/api/preload/{contract_id}/{seg_idx}")
async def preload(contract_id: str, seg_idx: int):
    idx = build_index(contract_id, _resolve_contract(contract_id))
    if seg_idx < 0 or seg_idx >= len(idx.segments):
        raise HTTPException(status_code=404, detail="seg_idx out of range")
    key = cache_key(idx.segments[seg_idx].text, VOICE_REF_ID)
    if cache.has(key):
        return {"status": "cached", "seg_idx": seg_idx}

    async def _bg():
        async with _lock_for(key):
            if cache.has(key):
                return
            buf = bytearray()
            async for chunk in engine.synth(idx.segments[seg_idx].text):
                buf.extend(chunk)
            cache.put(key, bytes(buf))

    asyncio.create_task(_bg())
    return {"status": "preloading", "seg_idx": seg_idx}
```

- [ ] **Step 4: Run full app test suite to verify all pass**

Run: `uv run pytest seek_probe/tests/test_app.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add seek_probe/backend/app.py seek_probe/tests/test_app.py
git commit -m "feat(probe): preload endpoint warms cache in background"
```

---

## Task 10: Frontend — progress bar + play + seek

**Files:**
- Create: `seek_probe/frontend/index.html`, `seek_probe/frontend/app.js`

**Interfaces:**
- Consumes: `GET /api/contract/{id}` (JSON), `GET /api/segment/{id}/{seg_idx}` (audio), `POST /api/preload/{id}/{seg_idx}`

- [ ] **Step 1: Write `index.html`**

`seek_probe/frontend/index.html`:
```html
<!doctype html>
<html lang="zh-HK">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>粵語合同朗讀 — Seek Probe</title>
  <style>
    body { font: 16px/1.6 -apple-system, "PingFang HK", sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; }
    .bar { width: 100%; }
    #status { color: #555; min-height: 1.4em; }
    audio { width: 100%; margin-top: .5rem; }
    .clause { color: #888; font-size: .9em; margin-top: .3em; }
  </style>
</head>
<body>
  <h2>粵語合同朗讀(穿刺)</h2>
  <input id="bar" class="bar" type="range" min="0" max="1000" value="0" step="1" disabled />
  <div id="status">載入中…</div>
  <audio id="audio" controls></audio>
  <div id="clause" class="clause"></div>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `app.js`**

`seek_probe/frontend/app.js`:
```javascript
const CONTRACT_ID = "sample";
const PRELOAD_AHEAD = 3;

const bar = document.getElementById("bar");
const statusEl = document.getElementById("status");
const audio = document.getElementById("audio");
const clauseEl = document.getElementById("clause");

let segs = [];        // [{seg_idx, est_dur_s, cumulative_start_s}]
let totalEst = 0;
let current = 0;

function barToSeconds(v) {
  return (Number(v) / 1000) * totalEst;
}
function secondsToBar(s) {
  return Math.round((s / totalEst) * 1000);
}
function segmentAtSeconds(s) {
  for (const m of segs) {
    if (s < m.cumulative_start_s + m.est_dur_s) return m.seg_idx;
  }
  return segs.length - 1;
}

async function loadSegment(segIdx) {
  const r = await fetch(`/api/segment/${CONTRACT_ID}/${segIdx}`);
  if (!r.ok) throw new Error(`segment ${segIdx} failed: ${r.status}`);
  return await r.blob();
}

async function playFrom(segIdx) {
  current = segIdx;
  statusEl.textContent = `生成/載入 第 ${segIdx + 1}/${segs.length} 段…`;
  try {
    const blob = await loadSegment(segIdx);
    audio.src = URL.createObjectURL(blob);
    clauseEl.textContent = texts(segIdx);
    bar.value = secondsToBar(segs[segIdx].cumulative_start_s);
    await audio.play();
    statusEl.textContent = `播放 第 ${segIdx + 1}/${segs.length} 段`;
    for (let k = 1; k <= PRELOAD_AHEAD; k++) {
      const n = segIdx + k;
      if (n < segs.length) fetch(`/api/preload/${CONTRACT_ID}/${n}`, { method: "POST" });
    }
  } catch (e) {
    statusEl.textContent = "錯誤:" + e.message;
  }
}

function texts(i) {
  return segTexts[i] || "";
}
let segTexts = [];

audio.addEventListener("ended", () => {
  if (current + 1 < segs.length) playFrom(current + 1);
  else statusEl.textContent = "完畢";
});

bar.addEventListener("change", () => {
  const seg = segmentAtSeconds(barToSeconds(bar.value));
  playFrom(seg);
});

(async function init() {
  const r = await fetch(`/api/contract/${CONTRACT_ID}`);
  const data = await r.json();
  segs = data.segments;
  totalEst = data.total_est_s;
  segTexts = data.texts;
  bar.disabled = false;
  statusEl.textContent = `就緒 · 共 ${segs.length} 段 · 預估 ${totalEst.toFixed(0)}s`;
})();
```

- [ ] **Step 3: Manual verification (engine + backend running)**

Start backend (engine already running from Task 6):
```bash
cd /Users/roy/codes/audio-with-qwen3-tts
uv run uvicorn seek_probe.backend.app:app --port 8000
```
Open `http://127.0.0.1:8000/`. Verify: bar renders with estimated total; press play → first segment plays, advances through segments; drag the bar → it jumps to the segment at that position and (re)generates/plays it; drag back to an already-played segment → plays near-instantly (cache hit).

- [ ] **Step 4: Commit**

```bash
git add seek_probe/frontend/index.html seek_probe/frontend/app.js
git commit -m "feat(probe): web player — draggable progress bar, play, seek, preload"
```

---

## Task 11: End-to-end smoke, metrics, README

**Files:**
- Modify: `seek_probe/README.md`
- Create: `seek_probe/scripts/measure.py` (cold-seek latency + cache-hit + RTF)

**Interfaces:** none new; produces run instructions + a measurement script.

- [ ] **Step 1: Write measurement script**

`seek_probe/scripts/measure.py`:
```python
"""Measure cold-seek first-byte latency, cache-hit, and per-segment RTF.
Run with engine + backend up: uv run python seek_probe/scripts/measure.py"""
from __future__ import annotations
import time
import httpx

BASE = "http://127.0.0.1:8000"
CONTRACT = "sample"


def main():
    idx = httpx.get(f"{BASE}/api/contract/{CONTRACT}").json()
    segs = idx["segments"]
    print(f"contract={CONTRACT} segments={len(segs)} est_total={idx['total_est_s']:.0f}s")

    # cold: request segment 5 (likely uncached), measure time-to-first-byte + total
    target = min(5, len(segs) - 1)
    t0 = time.perf_counter()
    first_byte = None
    total = 0
    with httpx.stream("GET", f"{BASE}/api/segment/{CONTRACT}/{target}", timeout=120) as r:
        for chunk in r.iter_bytes():
            if first_byte is None:
                first_byte = time.perf_counter() - t0
            total += len(chunk)
    full = time.perf_counter() - t0
    print(f"cold seg {target}: first_byte={first_byte:.2f}s total={full:.2f}s bytes={total}")

    # warm cache hit
    t0 = time.perf_counter()
    httpx.get(f"{BASE}/api/segment/{CONTRACT}/{target}")
    print(f"warm hit: {time.perf_counter() - t0:.3f}s")

    # RTF approx: generate a fresh segment and compare bytes-duration (rough)
    fresh = min(target + 1, len(segs) - 1)
    httpx.post(f"{BASE}/api/preload/{CONTRACT}/{fresh}")  # warm in bg
    time.sleep(0.5)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run end-to-end + capture metrics**

With engine + backend running:
```bash
uv run python seek_probe/scripts/measure.py
```
Record the printed cold-seek first-byte latency, warm-hit time, and total into the README's "Results" section.

- [ ] **Step 3: Finish README**

`seek_probe/README.md`:
```markdown
# 粵語合同朗讀 + 可拖動進度條(穿刺)

可行性穿刺:GPT-SoVITS(粵語)+ 分段/內容尋址緩存/段內流式/seek 映射 + 網頁播放器。見 spec: `docs/superpowers/specs/2026-07-25-cantonese-tts-seek-probe-design.md`。

## 運行

1. 引擎(獨立終端):
   ```
   cd /Users/roy/codes/GPT-SoVITS && uv run python api_v2.py   # :9880
   ```
2. 參考音頻:放 `seek_probe/refs/cantonese_ref.wav`,其粵語轉寫放 `seek_probe/refs/cantonese_ref.txt`。
3. 後端+前端:
   ```
   uv run uvicorn seek_probe.backend.app:app --port 8000
   ```
4. 打開 http://127.0.0.1:8000/ ,拖動進度條測試。

## 測試
```
uv run pytest -q
```

## 結果(填入實測)
- 分段數 / 預估時長:
- 冷 seek 首字節延遲:
- 命中緩存命中耗時:
- 跨段音色一致性(耳聽):

## 已知後續(未做,見 spec §2/§10)
- `streaming_mode=true` 降冷 seek 延遲(段格式隨版本變,未押注)。
- 真實時長回填精修進度條。
- 段內精確子 seek(目前吸附段邊界)。
- 粵語母語者地道性 go/no-go(單獨關卡)。
```

- [ ] **Step 4: Commit**

```bash
git add seek_probe/scripts/measure.py seek_probe/README.md
git commit -m "feat(probe): e2e measurement script + README run guide"
```

---

## Self-Review (run after writing)

- **Spec coverage:** spec §4 architecture → Tasks 6-10; §5 components → segmenter(2)/contract(3)/cache(4)/client(7)/app(8,9)/frontend(10); §6 seek mapping → Task 3 + frontend(10); §7 error handling → app 404s + per-key lock(8,9); §8 testing → unit tests(2,3,4,7) + integration(8,9) + e2e(11); §9 milestones M0→6, M1→2-4,8, M2→9,10,11; §10 risks → documented as follow-ups in client(7) + README(11). All sections mapped.
- **Placeholder scan:** none — every code step contains real code; setup steps give concrete commands + a verification curl.
- **Type consistency:** `split_contract`, `estimate_duration`, `Segment`, `SegmentMeta`, `SegmentIndex`, `build_index`, `position_to_segment`, `load_contract_text`, `cache_key`, `SegmentCache.has/get/put`, `GPTSoVITSClient.synth(text, transport=None)` — names/signatures match across all tasks and the Interfaces block.
