# 架构说明(as-built,对外服务)

> 本文描述**当前真实实现**(代码为准)。设计决策见 `docs/adr/`(ADR-0001..0008)+ `CONTEXT.md`(领域语言)。

## 0. 一句话

调用方 POST 上传合同 TXT + `template_id` → 后端按 Template 选择合同语言、确定性切片、normalizer 和 Engine Profile → 算内容寻址 `contract_id`、回发段清单 → 前端按累积时长画可拖进度条 → 取某段音频时,后端只对 TTS 输入做对应语言的归一化，调 profile 引擎合成、落缓存、回传。原文和展示文本始终不变。

## 0.5 数据处理主线(上传 → 出声)

```
POST /api/contracts {text, template_id}      (xcash_yue / xcash_zh / xcash_en; xcash 为别名)
  │  contract_id = sha256(template_id | 原文)            内容寻址(ADR-0001/0005)
  ▼
原文落盘 uploaded/<contract_id>.txt            (90 天 creation TTL,ADR-0004)
  ▼
切片 split_contract (§3)                       确定性;取段时按需重切,不持久化段
  │  (可选落盘观察:dump_segments(build_index(cid,text), path))
  ▼
按需逐段归一化(按 Template 选择 normalizer)      只在某段将要合成时执行,不批量
  │  显示文本 = 原始段文本(不回传调用方);归一化文本只喂引擎
  ▼
缓存键 sha256(Template + 归一化文本 + Engine Profile + 版本)   (ADR-0008)
  ├── 命中 → Response 回放 wav
  └── 未命中 → engine.synth (§5) → 落缓存 → 回传
```

要点:**归一化不是批量预处理**,而是合成前一刻对单段执行;切片结果不持久化;持久化产物是 `uploaded/*.txt`(原文,90d)与 `cache/*.wav`(音频,30d 滑动窗口)。

## 1. 拓扑(两进程 + 磁盘存储/缓存 + 浏览器)

```
┌──────────┐  HTTP   ┌────────────────────┐   HTTP    ┌──────────────────┐
│ 浏览器    │───────▶│ FastAPI 后端        │─────────▶│ GPT-SoVITS 引擎   │
│ HTML/JS  │◀───────│ py3.12 / :8000      │◀─────────│ api_v2.py :9880   │
│ +<audio> │ 音频    │ 上传/切片/归一化/    │  音频     │ py3.10, CPU       │
└──────────┘         │ 缓存/seek 映射       │           │ text_lang=yue     │
                     └────────────────────┘           └──────────────────┘
       磁盘: uploaded/<cid>.txt(原文) + cache/<sha256>.wav + manifest.json
```

- **引擎进程**:本地 GPT-SoVITS 仓库(独立 py3.10 venv,安装见 `docs/engine-setup.md`),常驻 `api_v2.py`,暴露 `POST /tts`。
- **后端进程**:本项目 py3.12 venv,`uvicorn backend.app:app --port 8000`。
- **存储**:`uploaded/`(原文,gitignored)、`cache/`(音频,gitignored)。
- 浏览器与后端走 `:8000`;后端调引擎走 `:9880`(`httpx trust_env=False`,绕过本机 clash 代理)。

## 2. 一次 seek 的完整时序

```
用户拖进度条到 t 秒
  │
  ▼ app.js: segmentAtSeconds(t) → seg_idx          (按段累积预估时长定位)
  │
浏览器  GET /api/contracts/{id}/segments/{seg_idx}  ────▶ 后端
  │                                                       │
  │                                          text = ContractStore.get(id); 缺 → 404
  │                                          idx = build_index(id, text); seg_idx 越界 → 404
  │                                          profile = Template Registry[contract.template_id]
  │                                          tts_text = profile.normalizer(seg.text)
  │                                          key = sha256(Template + tts_text + Profile + version)
  │                                                       │
  │                                          ┌─── 命中?───┐
  │                                          是           否
  │                                          │            加锁(_synth_and_cache) → 二次查
  │                                          │            仍 miss → engine.synth → cache.put
  │                                          ◀── Response(200, audio/wav) ──────────┘
  │                                          引擎 HTTP 错 → 502;连接失败/其它 → 500
浏览器拿到 wav blob → audio.src = blob → 播放
  │ 同时 POST /api/contracts/{id}/segments/{seg_idx+1..+k}/preload → 后台预热后面 K 段
  ▼ 播完该段 → "ended" → 自动 playFrom(seg_idx+1)
```

## 3. seek 逻辑(`contract.py` / `segmenter.py` / 前端 `app.js`)

1. **分句**(`segmenter.split_contract(text, target=20, soft_max=45, hard_max=50)`):硬边界为句末标点 `。！？；` 与换行;行内长句先按 `，、;` 子切,仍超 `hard_max` 再按 `：（《(` 拆;短碎片向 `target` 合并、封顶 `soft_max`;≤1 字的孤碎片折回前段。**确定性**——同文本永远同分段(缓存键稳定的前提)。
2. **段索引**(`contract.build_index(contract_id, text)`):每段 `{seg_idx, text, est_dur_s, cumulative_start_s}`,总和 `total_est_s`。`est_dur_s` 按字数 ÷ 3.7 字/秒估算。
3. **进度条**:前端把一个 `range(0..1000)` 映射到 `[0, total_est_s]`,**音频还没生成就能拖**(连续流式给不了的可拖动时间轴)。
4. **位置→段**(`contract.position_to_segment(idx, t)` / 前端 `segmentAtSeconds`):找 `cumulative_start_s ≤ t < 下一段`。**seek 吸附段边界**——拖到一段中间也从该段头播(段很短 ~5–13s,合同场景可接受;省掉子段精确 seek)。
5. **预载**:播放某段时,后台 `POST /api/contracts/{id}/segments/{n}/preload` 预热后面 K=3 段,让顺序播放/小幅前 seek 命中缓存;上传时预热 seg 0。

## 4. 音频缓存逻辑(内容寻址,`cache.py`)

- **key** = `sha256(canonical Template ID + 归一化段文本 + Engine Profile ID + profile cache version)`。只有四项都相同才允许跨 Contract 复用；换 Template、引擎 profile 或版本都不会命中旧音频(ADR-0008)。
- 命中(`cache.get`)→ 回放文件;`get` 命中时刷新 `last_access_at`。
- 未命中 → 生成、`cache.put`、回传。
- **并发去重**:`_synth_and_cache` 用 per-key `asyncio.Lock` + 进锁后二次查缓存,同一未命中段的并发请求只生成一次。
- **静态内容自动复用**:合同的静态 boilerplate 在所有合同里文本相同 → 同 key → 一处生成、处处复用(等价免费"预生成")。
- **淘汰**(ADR-0004):30 天滑动窗口——`last_access_at` 超 30 天的条目由 `evict_expired` 删(命中即续期)。**清理触发**(ADR-0007):服务启动清一次 + 进程内 asyncio 周期任务每天 1 次(`run_cleanup()`,原文 90d + 音频 30d 合并;evict 同步直调、阻塞 ~27ms/天,故意的——见 ADR-0007)。
- 存储:`cache/<sha256>.wav` + `cache/manifest.json`(key → `{created_at, last_access_at, duration}`)。

## 5. TTS 生成逻辑(`gptsovits_client.py` / `bailian_cosyvoice_client.py` / `app.py`)

- 段文本先经当前 Template 的 normalizer（`normalize_for_tts`、`normalize_for_tts_zh` 或 `normalize_for_tts_en`）→ `tts_text`。
- `xcash_yue` 的本地 profile 使用 GPT-SoVITS `text_lang="yue"`；普通话/英语 profile 在本地模式不可用。云端 Bailian 为三个 Template 分别绑定 `BAILIAN_VOICE`、`BAILIAN_VOICE_ZH` 和 `BAILIAN_VOICE_EN`。
- `engine.synth(tts_text)` 的两个 client 接口统一为异步字节流；本地 GPT-SoVITS 发送语言参数，云端 Bailian 发送 profile voice。引擎返回**整段 WAV**。
- **生成后响应**:`get_segment` 先把整段字节收齐再 `Response(200, audio/wav)`——**不是 tee 边生成边回传**。引擎失败能回明确错误(`httpx.HTTPStatusError → 502`;连接失败/其它 `→ 500`),不会被浏览器吞成模糊的 `Load failed`。
- **音色一致**:每个 Engine Profile 固定自己的参考音或云端 voice；同一 Template 任意 seek 顺序、缓存命中或新生成都使用同一音色。
- **引擎可切换**(`app.make_engine`,`CONTRACT_TTS_ENGINE` env):默认 `gptsovits`(本地、仅粤语);`CONTRACT_TTS_ENGINE=bailian` 切云端 CosyVoice。两个 client 的 `synth(text)->AsyncIterator[bytes]` **同构**,§6 归一化、§3 seek、§4 缓存全部共用。缓存键使用 Template、归一化文本、Engine Profile ID 和独立 profile cache version；更改协议、地域、voice/model/参数时提升受影响的 `ENGINE_PROFILE_CACHE_VERSION_*`。
  - 云端 client(`bailian_cosyvoice_client.py`)内部有两个 adapter：`BAILIAN_TRANSPORT=http` 时 POST `SpeechSynthesizer` 取得 audio URL 后下载；`BAILIAN_TRANSPORT=wss` 时通过 DashScope SDK 调用 WebSocket TTS，并在线程中执行同步 SDK 以免阻塞事件循环。`DASHSCOPE_API_KEY` 必须设置；端点、模型、音色与 Key 必须属于同一地域。云端引擎**不需参考音**。
  - **TN 边界(关键)**:云端 cosyvoice 的自动 TN 只覆盖日期、基础金额→数值;**逐位(电话/身份证/型号)、`HK$→港幣`、罗马序号仍靠 §6 归一化**(实测云端会把这些读错)。所以**云端路径不能省 `normalizer.py`**,与本地同构。

## 6. 文本归一化(关键一层,`normalizer.py` / `normalizers.py`,依赖 `cn2an`)

Registry 为三个 Template 绑定独立 normalizer。下表描述原有 `xcash_yue` 规则；
`xcash_zh` 的 normalizer 保持原有职责，只处理普通话数字、日期、金额、时间和编号读法；繁体转简体由普通话百炼 TTS 引擎适配层在远程请求前最后一步完成，不改动上传原文和页面显示文本；
`xcash_en` 保留英文词汇和专有名词，并展开日期、金额、百分比、单位及逐位编号。

显示文本保持原始(给客户看);只改喂给 TTS 的文本。核心是**按语言分流**:

**英文片段(含 ≥3 字母英文单词、且无 CJK 的极大片段)** → L2 清洗后**保留英文**,由 `yue` 前端读成词(不转中文):
- 全大写 → 首字母大写(`ZERO FINANCE → Zero Finance`),否则 yue 前端会逐字母读。
- 结构缩写展开:`FLT→Flat`、`BLK→Block`、`39/F→39th Floor`(英文 g2p 不认缩写,会逐字母)。
- **数字不转中文**(地址里的 `08/39/5` 跟着英文读)。

**其余(中文语境)** → 粤语归一化(GPT-SoVITS 数字前端不稳,`2,864,000` 会被读成 `28640`):

| 输入 | 归一化为 | 例 |
|---|---|---|
| `N%` | `百分之<N中文>` | `5.25% → 百分之五點二五`;`0.5% → 百分之零點五` |
| `YYYY年M月D日` | 年逐位 + 月/日数值 | `2026年8月15日 → 二零二六年八月十五日` |
| `YYYY年` / `M月` / `D日` | 逐位 / 数值 | `2026年 → 二零二六年`;`8月 → 八月` |
| `HH:MM` | `H時M分` | `23:31 → 二十三時三十一分` |
| `D/M/YYYY` | `YYYY年M月D日` | `28/08/2024 → 二零二四年八月二十八日` |
| 分隔符数字串(电话/账号/牌照) | **逐位** | `024-363-529959882 → 零二四…`;`0954/2024 → 零九五四…` |
| 裸 ≥6 位(非金额) | 逐位 | `25310333 → 二五三一…`(身份证/电话,非基数) |
| 拉丁字母+数字(型号) | 字母+逐位 | `XR-7200 → XR-七二零零`;`A100 → A一零零` |
| `HK$ / $` 金额 | `港幣<基数>` | `HK$126,000.00 → 港幣十二万六千`(尾零 drop) |
| 其余裸数字(金额/数量) | 数值(cn2an) | `12,000件 → 一万二千件` |
| 罗马序号 | 中文 | `第III部 → 第三部`;`(ii) →（二）` |
| 還 多音字 | 同音字替换(引擎误读 haan4) | `償還 → 償環`;`還款 → 環款` |
| `注：`/`註：` 前缀 | 逗号(该 token 使引擎误读后词) | `注：港幣 → 注，港幣` |
| 已是中文数字 | 不变 | `百分之二十`、`叁佰伍拾捌萬` 原样 |

**实现**(`normalize_for_tts`):全局预处理(剥控制字符、`HK$→港幣`、罗马序号)→ 把英文片段替换成 Private-Use-Area 占位符 → 对中文余部跑上表规则 → 还原英文片段。

> **为什么 `text_lang=yue` 而非 `auto_yue`**:实测 `auto_yue` 会把英文公司名**之后**的 CJK 误判成日语(共享汉字 zh/ja 歧义)。`yue` + L2 首字母大写即可让英文被读成词(不逐字母),且 CJK 永远粤语。

## 7. 关键文件地图

| 文件 | 职责 |
|---|---|
| `backend/text/segmenter.py` | 粤语合同切分、`Segment` 和粤语时长估算 |
| `backend/text/mandarin_segmenter.py` | 普通话独立句末/分句/长段兜底规则与时长估算 |
| `backend/text/segmenters.py` | 英文句末及单词边界切分与时长估算 |
| `backend/text/normalizer.py` / `normalizers.py` | 粤语、普通话和英语的独立 TTS normalizer |
| `backend/text/cn_numbers.py` | 粤语与普通话 normalizer 共用的中文数字逐位/基数转换 |
| `backend/storage/contract.py` | `compute_contract_id(text, template_id)`、`ContractStore`(原文磁盘存储 + 90d TTL)、`build_index`、`SegmentIndex/SegmentMeta`、`position_to_segment`、`dump_segments` |
| `backend/storage/cache.py` | `cache_key(template_id, text, engine_profile_id, cache_version)`、`SegmentCache`(has/get/put + manifest + `evict_expired`) |
| `backend/engines/gptsovits_client.py` | `GPTSoVITSClient.synth`(httpx → 引擎 `/tts`,`text_lang` 按 profile 设置,`trust_env=False`);本地第一阶段仅粤语 |
| `backend/engines/bailian_cosyvoice_client.py` | `BailianCosyVoiceClient.synth`(两步 POST+GET,`trust_env=False`);云端按 Template 绑定对应 voice |
| `backend/{normalizer,normalizers,segmenter,segmenters,cn_numbers,contract,cache,...}.py` | 旧 import 路径的兼容导出，不放业务实现 |
| `backend/app.py` | FastAPI:`POST /api/contracts`、`GET /api/contracts/{id}`、`.../segments/{n}`、`.../preload`、静态 `/`; Template Registry 与 profile 选择;`_synth_and_cache`/`_load_idx_or_404`;`run_cleanup`/`_periodic_cleanup`(启动 + 每 24h 定期清理,ADR-0007) |
| `frontend/{index.html,app.js}` | 上传 demo(textarea + 进度条 + 播放/seek/预载) |
| `contracts/sample_contract.txt` | 示例合同(demo 素材,唯一跟踪的合同) |
| `refs/cantonese_ref_trim.{wav,txt}` | 固定粤语参考音 + 转写(7s,本地、wav gitignored) |

## 8. 上传合同 / 工具速查

合同由调用方 **POST 上传**(不再预注册):

```
POST /api/contracts  json={"text": "<合同原文>", "template_id": "xcash"}
→ {"contract_id": "<sha256>", "total_est_s": ..., "segments": [{seg_idx, est_dur_s, cumulative_start_s}, ...]}
```

- `template_id` 必传，接受 `xcash_yue`、`xcash_zh`、`xcash_en`，`xcash` 为 `xcash_yue` 别名(未知 → 400)。
- 同原文 → 同 `contract_id`(内容寻址,可复用;`sha256(template_id | 原文)`)。
- 上传后台预热 seg 0;不回传段文本(调用方已有原文)。

**工具速查**:

| 要做什么 | 用什么 |
|---|---|
| 看某段会送什么文本给引擎 | 按 Template 调用对应 normalizer（`backend.normalizers` 或 `backend.normalizer`） |
| 看切片结果 | `dump_segments(build_index(cid, text), path)` |
| 跑测试 | `uv run pytest -q` |

## 9. 约束与后续

- **单实例**(ADR-0003):per-key 锁 `_locks` 与后台清理任务(ADR-0007)都是进程内;缓存/原文是本地盘;多实例需换分布式锁 + 共享存储 + 避免多副本重复扫。
- **不校验归属**(ADR-0002):`contract_id` 作 bearer 凭证、裸 URL,接受 IDOR 残余风险。
- **留存**(ADR-0004):原文 90d creation TTL、音频 30d 滑动窗口(命中续期)。
- **参考音频必须 3–10 秒**(GPT-SoVITS 硬规则);当前用 `cantonese_ref_trim.wav`(7s)。
- `streaming_mode=False`:每段返回整段 WAV。冷 seek 延迟 ≈ 该段生成时间(M3 Max CPU RTF≈0.4,短段 ~1s);靠预载 + 缓存掩盖。
- `httpx trust_env=False`:本机有 clash 代理(`:7897`),否则 127.0.0.1 走代理 → 502。
- **含拉丁字母的文本**:触发 NLTK 英文前端,需 `~/nltk_data`(见 `engine-setup.md`)。
- **地区口音(HK/GZ)**:GPT-SoVITS 只有单一 `yue`(Jyutping),无地区开关;换参考音只改音色、不改发音。
- **长文(1 小时)**:本架构直接适用——1h ≈ 更多分段;静态内容靠 §4 内容寻址自动复用。

## 10. 设计决策出处

权威设计在 `docs/adr/`(ADR-0001..0007)+ `CONTEXT.md`。几处与"显而易见"做法不同的关键取舍:

1. **TTS 回传**:"生成后响应 `Response` + 失败回 502/500",而非 tee 流式 `StreamingResponse`——为暴露引擎错误。
2. **归一化层** `normalizer.py`:中文语境数字/金额/日期 → 粤语中文;英文地址/公司名 → L2 清洗保留英文。缓存键基于**归一化后**的文本。
3. **`text_lang=yue` + L2**(非 `auto_yue`):避免英文后的 CJK 被引擎误判日语。
4. **缓存键 = Template + 归一化文本 + Engine Profile + 版本**(ADR-0008):不同语言、音色和 profile 配置严格隔离；旧格式缓存不参与新请求命中。
5. **contract_id = sha256(template_id | 原文)**(ADR-0005):同原文按不同模板分段得不同 id。
6. **过期清理 = 启动清 + 进程内 asyncio 每天 1 次**(ADR-0007):evict 同步直调、阻塞事件循环 ~27ms/天——**故意的**(丢 `to_thread` 会引入 manifest 竞态、需加锁);规模增长致阻塞可感知再优化。
