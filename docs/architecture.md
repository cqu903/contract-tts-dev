# 架构说明(as-built,对外服务)

> 本文描述**当前真实实现**(代码为准)。设计决策见 `docs/adr/`(ADR-0001..0009)+ `CONTEXT.md`(领域语言)。

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
缓存键 sha256(Template + 归一化文本 + Engine Profile + 版本 + 合成指纹)   (ADR-0008/0009)
  ├── 命中 → Response 回放格式感知的 Audio Artifact
  └── 未命中 → engine.synth (§5) → 落缓存 → 回传
```

要点:**归一化不是批量预处理**,而是合成前一刻对单段执行;切片结果不持久化;持久化产物是 `uploaded/*.txt`(原文,90d)与 `cache/*.{wav,mp3}`(音频,30d 滑动窗口)。

## 1. 拓扑(后端 + 可配置 Provider + 磁盘存储/缓存 + 浏览器)

```
┌──────────┐  HTTP   ┌────────────────────┐   引擎协议   ┌──────────────────────────┐
│ 浏览器    │───────▶│ FastAPI 后端        │───────────▶│ GPT-SoVITS（本地）         │
│ HTML/JS  │◀───────│ py3.12 / :8000      │◀───────────│ CosyVoice（云端）           │
│ +<audio> │ 音频    │ 上传/切片/归一化/    │    音频     │ Microsoft Edge/Azure（云端）│
└──────────┘         │ 缓存/seek 映射       │            └──────────────────────────┘
                     └────────────────────┘
       磁盘: uploaded/<cid>.txt(原文) + cache/<sha256>.<format> + manifest.json
```

- **Engine Provider**:按 Reading Language 选择 GPT-SoVITS、CosyVoice 或稳定的 Microsoft Provider；Microsoft Provider 内再显式选择 Edge/Azure Driver。只有 GPT-SoVITS 需要本地独立引擎进程。
- **GPT-SoVITS 引擎进程**:本地 GPT-SoVITS 仓库(独立 py3.10 venv,安装见 `docs/engine-setup.md`),常驻 `api_v2.py`,暴露 `POST /tts`。
- **后端进程**:本项目 py3.12 venv,`uvicorn backend.app:app --port 8000`。
- **存储**:`uploaded/`(原文,gitignored)、`cache/`(音频,gitignored)。
- 浏览器与后端走 `:8000`;GPT-SoVITS 使用 `:9880`(`httpx trust_env=False`,绕过本机 clash 代理)，CosyVoice 与 Microsoft Driver 使用出站云服务连接。

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
  │                                          ◀── Response(200, artifact.media_type) ┘
  │                                          Microsoft 上游失败 → 502;其它引擎按 adapter 语义映射
浏览器拿到音频 blob → SegmentAudioBuffer 保存 → audio.src = blob → 播放
  │ 同时 GET /api/contracts/{id}/segments/{seg_idx+1..+k} → 下载并保存后面 K 段 blob
  ▼ 播完该段 → "ended" → 直接复用已下载 blob → 自动 playFrom(seg_idx+1)
```

## 3. seek 逻辑(`contract.py` / `segmenter.py` / 前端 `app.js`)

1. **分句**(`segmenter.split_contract(text, target=20, soft_max=45, hard_max=50)`):硬边界为句末标点 `。！？；` 与换行;行内长句先按 `，、;` 子切,仍超 `hard_max` 再按 `：（《(` 拆;短碎片向 `target` 合并、封顶 `soft_max`;≤1 字的孤碎片折回前段。**确定性**——同文本永远同分段(缓存键稳定的前提)。
2. **段索引**(`contract.build_index(contract_id, text)`):每段 `{seg_idx, text, est_dur_s, cumulative_start_s}`,总和 `total_est_s`。`est_dur_s` 按 Template 转换后的实际朗读文本估算（英语按词数，普通话/粤语按非空白字符），避免金额、日期和编号展开后进度条持续漂移。
3. **进度条**:前端把一个 `range(0..1000)` 映射到 `[0, total_est_s]`,**音频还没生成就能拖**(连续流式给不了的可拖动时间轴)。
4. **位置→段**(`contract.position_to_segment(idx, t)` / 前端 `segmentAtSeconds`):找 `cumulative_start_s ≤ t < 下一段`。**seek 吸附段边界**——拖到一段中间也从该段头播(段很短 ~5–13s,合同场景可接受;省掉子段精确 seek)。
5. **预载**:浏览器通过 `SegmentAudioBuffer` 提前 GET 后面 K=3 段并保存 Promise/Blob；顺序播放切段时不再等待网络。上传时后端仍预热 seg 0，`POST .../preload` 继续作为外部预热接口保留。

## 4. 音频缓存逻辑(内容寻址,`cache.py`)

- **key** = `sha256(canonical Template ID + 归一化段文本 + Engine Profile ID + profile cache version + synthesis fingerprint)`。只有完整身份都相同才允许跨 Contract 复用；换 Template、引擎 profile、版本、Driver、音色、语速或格式都不会命中旧音频(ADR-0008/0009)。
- 命中(`cache.get`)→ 回放文件;`get` 命中时刷新 `last_access_at`。
- 未命中 → 生成、`cache.put`、回传。
- **并发去重**:`_synth_and_cache` 用 per-key `asyncio.Lock` + 进锁后二次查缓存,同一未命中段的并发请求只生成一次。
- **静态内容自动复用**:合同的静态 boilerplate 在所有合同里文本相同 → 同 key → 一处生成、处处复用(等价免费"预生成")。
- **淘汰**(ADR-0004):30 天滑动窗口——`last_access_at` 超 30 天的条目由 `evict_expired` 删(命中即续期)。**清理触发**(ADR-0007):服务启动清一次 + 进程内 asyncio 周期任务每天 1 次(`run_cleanup()`,原文 90d + 音频 30d 合并;evict 同步直调、阻塞 ~27ms/天,故意的——见 ADR-0007)。
- 存储:`cache/<sha256>.<format>` + `cache/manifest.json`；manifest 同时记录时间、duration、canonical `audio_format`、`media_type` 和 `file_extension`，只有三项格式元数据完全一致的非空文件才会命中。

## 5. TTS 生成逻辑(`gptsovits_client.py` / `bailian_cosyvoice_client.py` / `microsoft_tts.py` / `app.py`)

- 段文本先经当前 Template 的 normalizer（`normalize_for_tts`、`normalize_for_tts_zh` 或 `normalize_for_tts_en`）→ `tts_text`。
- 本地 GPT-SoVITS 为三个 Template 分别使用 `text_lang=yue/zh/en`；目标语言与参考音 `prompt_lang` 分离，普通话和英语默认复用粤语参考音进行跨语言合成，也可配置原生参考音。云端 Bailian 为三个 Template 分别绑定 `BAILIAN_VOICE`、`BAILIAN_VOICE_ZH` 和 `BAILIAN_VOICE_EN`。Microsoft Provider 为三个 Reading Language 分别绑定 voice/rate，并在内部选择 Edge 或 Azure Driver。
- 所有 Provider 的 `engine.synth(tts_text)` 接口统一为异步字节流，并显式声明 canonical `audio_format` 和 `synthesis_fingerprint`。GPT-SoVITS 与 CosyVoice 形成 WAV Audio Artifact；Microsoft Edge/Azure 形成 MP3 Audio Artifact。
- **生成后响应**:`get_segment` 先把整段字节收齐并形成 Audio Artifact，再按其 media type 返回——**不是 tee 边生成边回传**。Microsoft 上游失败统一映射为 `502` 且不自动回退；其它 Provider 保持各自现有错误语义。
- **音色一致**:每个 Engine Profile 固定自己的参考音或云端 voice；同一 Template 任意 seek 顺序、缓存命中或新生成都使用同一音色。
- **引擎按语言切换**：`CONTRACT_TTS_ENGINE` 是兼容回退值，`CONTRACT_TTS_ENGINE_YUE/ZH/EN` 可让每个 Template profile 独立选择 `gptsovits`、`cosyvoice`（内部规范化为 `bailian` adapter）或 `microsoft`。三个 Provider 的合成接口同构，§6 归一化、§3 seek、§4 缓存全部共用。缓存键使用 Template、归一化文本、按语言选出的 Engine Profile ID、独立 cache version 和 synthesis fingerprint；只切一种语言的 Provider、Driver 或合成配置会自动进入新的缓存命名空间。
  - 云端 client(`bailian_cosyvoice_client.py`)内部有两个 adapter：`BAILIAN_TRANSPORT=http` 时 POST `SpeechSynthesizer` 取得 audio URL 后下载；`BAILIAN_TRANSPORT=wss` 时通过 DashScope SDK 调用 WebSocket TTS，并在线程中执行同步 SDK 以免阻塞事件循环。`DASHSCOPE_API_KEY` 必须设置；端点、模型、音色与 Key 必须属于同一地域。云端引擎**不需参考音**。
  - Microsoft Provider(`microsoft_tts.py`)内部有 Edge 与 Azure Driver：Edge 使用第三方 `edge-tts`；Azure 使用官方 Speech SDK、正式资源 Key 和 Region 或 HTTPS Endpoint。两个 Driver 都输出 MP3、失败不互相切换，具体数据边界和验收步骤见 `docs/running.md`。
  - **TN 边界(关键)**:云端 cosyvoice 的自动 TN 只覆盖日期、基础金额→数值;**逐位(电话/身份证/型号)、`HK$→港幣`、罗马序号仍靠 §6 归一化**(实测云端会把这些读错)。所以**云端路径不能省 `normalizer.py`**,与本地同构。

## 6. 文本归一化(关键一层,`normalizer.py` / `normalizers.py`,依赖 `cn2an`)

Registry 为三个 Template 绑定独立 normalizer。下表描述原有 `xcash_yue` 规则；
`xcash_zh` 的 normalizer 按语义处理经过真实日期/时间校验的多格式日期、币种金额、百分比、楼层、结构标记和逐位编号；连续英文姓名、公司名和地址会先受保护并做英文 L2 清洗（如 `FLT→Flat`、`15/F→15th Floor`、全大写地名转词形），避免普通话数字规则改写地址或 TTS 逐字母拼读。繁体转简体由普通话引擎 adapter 在请求前最后一步完成，不改动上传原文和页面显示文本；
`xcash_en` 保留英文词汇和专有名词，复用上述地址缩写与大小写清洗，并展开 ISO/港式/英文月份日期、24 小时时间、金额与分币、百分比、单位、楼层、结构标记及逐位编号。英普切分器会把 PDF/Word 提取后独占一行的 `(a)`、`(ii)` 等标记与下一段正文合并，避免生成无意义的短音频。

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
| `backend/engines/gptsovits_client.py` | `GPTSoVITSClient.synth`（httpx → 引擎 `/tts`，`text_lang` 按目标语言设置，`prompt_lang` 按参考音设置，普通话请求前转简体，`trust_env=False`） |
| `backend/engines/bailian_cosyvoice_client.py` | `BailianCosyVoiceClient.synth`(两步 POST+GET,`trust_env=False`);云端按 Template 绑定对应 voice |
| `backend/{normalizer,normalizers,segmenter,segmenters,cn_numbers,contract,cache,...}.py` | 旧 import 路径的兼容导出，不放业务实现 |
| `backend/app.py` | FastAPI:`POST /api/contracts`、`GET /api/contracts/{id}`、`.../segments/{n}`、`.../preload`、静态 `/`; Template Registry 与 profile 选择;`_synth_and_cache`/`_load_idx_or_404`;`run_cleanup`/`_periodic_cleanup`(启动 + 每 24h 定期清理,ADR-0007) |
| `frontend/{index.html,app.js,playback.mjs}` | 上传 demo(textarea + 进度条 + 分语言速度档位 + 浏览器音频缓冲/播放/seek) |
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
