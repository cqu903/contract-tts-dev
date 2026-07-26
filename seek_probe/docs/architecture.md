# seek_probe 架构说明(as-built)

> 本文描述**当前真实实现**(代码为准)。设计期的 spec 在 `docs/superpowers/specs/2026-07-25-cantonese-tts-seek-probe-design.md`,与代码的差异见文末"与 spec 的差异"。

## 0. 一句话

浏览器拖动合同进度条 → 后端把"位置"映射到第 N 段 → 命中缓存就直接放文件;未命中则把该段文本**归一化(数字/金额/日期/型号 → 中文)**后调本地 GPT-SoVITS(粤语 `yue`)生成、落缓存、回传。所有段共用一段固定参考音色 → 任意 seek 顺序、缓存与否,前后音色一致。

## 1. 拓扑(两进程 + 磁盘缓存 + 浏览器)

```
┌──────────┐  HTTP   ┌────────────────────┐   HTTP    ┌──────────────────┐
│ 浏览器    │───────▶│ FastAPI 后端        │─────────▶│ GPT-SoVITS 引擎   │
│ HTML/JS  │◀───────│ py3.12 / :8000      │◀─────────│ api_v2.py :9880   │
│ +<audio> │ 音频    │ 分句/归一化/缓存/    │  音频     │ py3.10, CPU       │
└──────────┘         │ seek 映射            │           │ text_lang=yue     │
                     └────────────────────┘           └──────────────────┘
                            │ 磁盘缓存 cache/<sha256>.wav + manifest.json
```

- **引擎进程**:`/Users/roy/codes/GPT-SoVITS` 独立 py3.10 venv,常驻 `api_v2.py`,暴露 `POST /tts`。
- **后端进程**:本项目 py3.12 venv,`uvicorn seek_probe.backend.app:app --port 8000`。
- **缓存**:`seek_probe/cache/`(gitignored)。
- 浏览器与后端走 `:8000`;后端调引擎走 `:9880`(`httpx trust_env=False`,绕过本机 clash 代理)。

## 2. 一次 seek 的完整时序

```
用户拖进度条到 t 秒
  │
  ▼ app.js: segmentAtSeconds(t) → seg_idx          (按段累积预估时长定位)
  │
浏览器  GET /api/segment/{contract}/{seg_idx}  ──────▶ 后端
  │                                                       │
  │                                          tts_text = normalize_for_tts(seg.text)
  │                                          key = sha256(tts_text + voice_ref_id)
  │                                                       │
  │                                          ┌─── 命中?───┐
  │                                          是           否
  │                                          │            │
  │                                 FileResponse(文件)   加锁 → 二次查缓存
  │                                          │            │ 仍miss → engine.synth(tts_text)
  │                                          │            │ → 收齐字节 → cache.put → Response(200, audio/wav)
  │                                          │            │ 引擎 HTTP 错 → 502;其它异常 → 500
  │                                          ◀────────────┘
浏览器拿到 wav blob → audio.src = blob → 播放
  │ 同时 POST /api/preload/{contract}/{seg_idx+1..+k} → 后台预热后面 K 段
  ▼ 播完该段 → "ended" → 自动 playFrom(seg_idx+1)
```

## 3. seek 逻辑(`contract.py` / `segmenter.py` / 前端 `app.js`)

1. **分句**(`segmenter.split_contract(text, max_chars=60)`):按句末标点 `。！？；` 切,过长句再按 `，、` 子切。**确定性**——同文本永远同分段(缓存键稳定的前提)。
2. **段索引**(`contract.build_index(contract_id, text)`):每段 `{seg_idx, text, est_dur_s, cumulative_start_s}`,总和 `total_est_s`。`est_dur_s` 按字数 ÷ 3.7 字/秒估算。
3. **进度条**:前端把一个 `range(0..1000)` 映射到 `[0, total_est_s]`,**音频还没生成就能拖**(连续流式给不了的可拖动时间轴)。
4. **位置→段**(`contract.position_to_segment(idx, t)` / 前端 `segmentAtSeconds`):找 `cumulative_start_s ≤ t < 下一段`。**seek 吸附段边界**——拖到一段中间也从该段头播(段很短 ~5–13s,合同场景可接受;省掉子段精确 seek)。
5. **预载**:播放某段时,后台 `POST /api/preload` 预热后面 K=3 段,让顺序播放/小幅前 seek 命中缓存。

## 4. 音频缓存逻辑(内容寻址,`cache.py`)

- **key** = `sha256(归一化段文本 + "|" + voice_ref_id)`。文本相同 + 同音色 → 同 key。
- 命中(`cache.get(key)`)→ 直接 `FileResponse` 回放文件(亚毫秒)。
- 未命中 → 生成、`cache.put` 落盘、`Response` 回传。
- **并发去重**:`get_segment` 用 per-key `asyncio.Lock` + 进锁后二次查缓存,同一未命中段的并发请求只生成一次。
- **静态内容自动复用**:合同的静态 boilerplate 在所有合同里文本相同 → 同 key → 一处生成、处处复用(等价免费"预生成")。
- 存储:`cache/<sha256>.wav` + `cache/manifest.json`(key→{duration})。

## 5. TTS 生成逻辑(`gptsovits_client.py` / `app.py`)

- 段文本先经 `normalize_for_tts`(见 §6)→ `tts_text`。
- `engine.synth(tts_text)`:`POST {ENGINE_URL}/tts`,`json={text, text_lang="yue", ref_audio_path, prompt_text, prompt_lang="yue", media_type="wav", streaming_mode=False}`,`httpx` `trust_env=False`。引擎返回**整段 WAV**(`streaming_mode=False`)。
- **生成后响应**:`get_segment` 先把整段字节收齐再 `Response(200, audio/wav)`——**不是 tee 边生成边回传**。这样引擎失败能回明确错误(`httpx.HTTPStatusError → 502`,其它 `→ 500`),不会被浏览器吞成模糊的 `Load failed`。
- **音色一致**:所有段共用 `REF_AUDIO = refs/cantonese_ref_trim.wav`(7s)+ `VOICE_REF_ID`。固定参考 = 任意 seek 顺序、缓存命中或新生成,都是同一个人声。

## 6. 文本归一化(关键一层,`normalizer.py`,依赖 `cn2an`)

GPT-SoVITS 的数字前端不稳:`2,864,000` 会被读成 `28640`(尾零+千分位逗号丢)。所以**显示文本保持原始阿拉伯数字(给客户看),只把喂给 TTS 的文本预先转中文**。规则(按顺序):

| 输入 | 归一化为 | 例 |
|---|---|---|
| `N%` | `百分之<N中文>` | `5.25% → 百分之五點二五`;`0.5% → 百分之零點五` |
| `YYYY年M月D日` | 年逐位 + 月/日数值 | `2026年8月15日 → 二零二六年八月十五日` |
| `YYYY年` | 逐位 | `2026年 → 二零二六年` |
| `M月` / `D日` | 数值 | `8月 → 八月`;`30日 → 三十日` |
| 拉丁字母+连字符+数字(型号/编号) | **逐位** | `XR-7200 → XR-七二零零`(不是"七千二百") |
| 其余裸数字(金额/数量/时长) | 数值(cn2an) | `2,864,000元 → 二百八十六万四千元`;`12,000件 → 一万二千件` |
| 已是中文数字 | 不变 | `百分之二十`、`叁佰伍拾捌萬` 原样 |

## 7. 关键文件地图

| 文件 | 职责 |
|---|---|
| `seek_probe/backend/segmenter.py` | `split_contract`、`estimate_duration`、`Segment` |
| `seek_probe/backend/contract.py` | `build_index`、`SegmentIndex/SegmentMeta`、`position_to_segment` |
| `seek_probe/backend/cache.py` | `cache_key`、`SegmentCache`(has/get/put + manifest) |
| `seek_probe/backend/normalizer.py` | `normalize_for_tts`(数字/金额/日期/型号 → 中文) |
| `seek_probe/backend/gptsovits_client.py` | `GPTSoVITSClient.synth`(httpx → 引擎 `/tts`,`trust_env=False`) |
| `seek_probe/backend/app.py` | FastAPI:`/api/contract`、`/api/segment`、`/api/preload`、静态 `/` |
| `seek_probe/frontend/{index.html,app.js}` | 进度条 + 播放/seek/预载 |
| `seek_probe/contracts/sample_contract.txt` | 合同语料(书面中文,含数字/金额/日期) |
| `seek_probe/refs/cantonese_ref_trim.{wav,txt}` | 固定粤语参考音 + 转写(7s,本地、gitignored) |

## 8. 约束与后续

- **参考音频必须 3–10 秒**(GPT-SoVITS 硬规则);当前用 `cantonese_ref_trim.wav`(7s)。
- `streaming_mode=False`:每段返回整段 WAV。冷 seek 延迟 ≈ 该段生成时间(M3 Max CPU RTF≈0.4,短段 ~1s);靠 §3 的预载 + §4 的缓存掩盖。
- `httpx trust_env=False`:本机有 clash 代理(`http_proxy=:7897`),否则 127.0.0.1 走代理 → 502。
- **含拉丁字母的文本**:触发 NLTK 英文前端,需 `~/nltk_data`(见 `engine-setup.md` 踩坑 #7)。
- **地区口音(HK/GZ)**:GPT-SoVITS 只有单一 `yue`(Jyutping),无地区开关;换参考音只改音色、不改发音。要 HK/GZ 切换,最实际是"地区 → 对应参考音"映射(音色层)。
- **长文(1 小时)**:本架构直接适用——1h ≈ 更多分段;静态内容靠 §4 内容寻址自动复用;整体可后台预生成后交付(见 spec §10)。

## 9. 与 spec 的差异(代码为准)

1. **TTS 回传**:spec 写"tee 流式 `StreamingResponse`";实际为"生成后响应 `Response` + 失败回 502/500"(为暴露引擎错误)。
2. **新增归一化层** `normalizer.py`(spec 未含),TTS 路径多一道 `normalize_for_tts`;缓存键基于**归一化后**的文本。
3. 缓存键由"段文本"改为"归一化段文本";`load_contract_text` 在 `contract.py` 定义但 `app.py` 用自带的 `_resolve_contract`(测试可注入),前者未被使用。
