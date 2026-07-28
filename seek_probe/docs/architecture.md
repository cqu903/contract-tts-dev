# seek_probe 架构说明(as-built)

> 本文描述**当前真实实现**(代码为准)。设计期的 spec 在 `docs/superpowers/specs/2026-07-25-cantonese-tts-seek-probe-design.md`,与代码的差异见文末"与 spec 的差异"。

## 0. 一句话

浏览器拖动合同进度条 → 后端把"位置"映射到第 N 段 → 命中缓存就直接放文件;未命中则把该段文本**归一化**(中文语境的数字/金额/日期/型号 → 粤语中文;英文地址/公司名 → L2 清洗后保留英文,由 `yue` 前端读成词)后调本地 GPT-SoVITS(粤语 `yue`)生成、落缓存、回传。所有段共用一段固定参考音色 → 任意 seek 顺序、缓存与否,前后音色一致。

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

1. **分句**(`segmenter.split_contract(text, target=20, soft_max=45, hard_max=50)`):硬边界为句末标点 `。！？；` 与换行;行内长句先按 `，、;` 子切,仍超 `hard_max` 再按 `：（《(` 拆;短碎片向 `target` 合并、封顶 `soft_max`;≤1 字的孤碎片折回前段。**确定性**——同文本永远同分段(缓存键稳定的前提)。
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
- **引擎可切换**(`app.make_engine`,`SEEK_PROBE_ENGINE` env):默认 `gptsovits`(本地,如上);`SEEK_PROBE_ENGINE=bailian` 切云端 `cosyvoice-v3-flash` + 原生粤语音色(`BAILIAN_VOICE`,默认 `longjiaxin_v3`)。两个 client 的 `synth(text)->AsyncIterator[bytes]` **同构**,§6 归一化、§3 seek、§4 缓存全部共用,只换引擎不动其它。
  - 云端 client(`bailian_cosyvoice_client.py`)是两步:POST `SpeechSynthesizer` 拿 JSON 里的 audio url → GET 下载流式字节;`trust_env=False` 绕代理;`DASHSCOPE_API_KEY` 必须设。云端引擎**不需参考音**(用系统音色),音色一致由固定 `voice` 保证。速率/音调走 API 默认(`rate=1.0`、`pitch=1.0`);cosyvoice HTTP API 支持 `input.rate/pitch/volume`,需要正式节奏时可扩展(未接)。
  - **TN 边界(关键)**:云端 cosyvoice 的自动 TN 只覆盖日期、基础金额→数值;**逐位(电话/身份证/型号)、`HK$→港幣`、罗马序号仍靠 §6 归一化**(实测云端会把这些读错)。所以**云端路径不能省 `normalizer.py`**,与本地同构(normalizer→引擎)。

## 6. 文本归一化(关键一层,`normalizer.py`,依赖 `cn2an`)

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
| 已是中文数字 | 不变 | `百分之二十`、`叁佰伍拾捌萬` 原样 |

**实现**(`normalize_for_tts`):全局预处理(剥控制字符、`HK$→港幣`、罗马序号)→ 把英文片段替换成 Private-Use-Area 占位符 → 对中文余部跑上表规则(日期 `2026年8月1日` 需 CJK 分隔符相邻,故不能简单按 ASCII/CJK 切)→ 还原英文片段。

> **为什么 `text_lang=yue` 而非 `auto_yue`**:实测 `auto_yue` 会把英文公司名**之后**的 CJK 误判成日语(共享汉字 zh/ja 歧义)。`yue` + L2 首字母大写即可让英文被读成词(不逐字母),且 CJK 永远粤语。所以用确定性 `yue`,不用会"猜语言"的 `auto_yue`。

## 7. 关键文件地图

| 文件 | 职责 |
|---|---|
| `seek_probe/backend/segmenter.py` | `split_contract`(target/soft_max/hard_max)、`estimate_duration`、`Segment` |
| `seek_probe/backend/contract.py` | `build_index`、`SegmentIndex/SegmentMeta`、`position_to_segment`、`_CONTRACT_FILES` |
| `seek_probe/backend/cache.py` | `cache_key`、`SegmentCache`(has/get/put + manifest) |
| `seek_probe/backend/normalizer.py` | `normalize_for_tts`(英文片段 L2 + 中文语境数字/金额/日期 → 粤语中文) |
| `seek_probe/backend/gptsovits_client.py` | `GPTSoVITSClient.synth`(httpx → 引擎 `/tts`,`text_lang=yue`,`trust_env=False`);本地粤语引擎(默认) |
| `seek_probe/backend/bailian_cosyvoice_client.py` | `BailianCosyVoiceClient.synth`(两步 POST+GET,`trust_env=False`);云端 cosyvoice 引擎,`SEEK_PROBE_ENGINE=bailian` 启用,`longjiaxin_v3` 等原生粤语音色 |
| `seek_probe/backend/app.py` | FastAPI:`/api/contract`、`/api/segment`、`/api/preload`、静态 `/`;`_CONTRACT_FILES`;`make_engine`(`SEEK_PROBE_ENGINE` 选本地/云端) |
| `seek_probe/frontend/{index.html,app.js}` | 进度条 + 播放/seek/预载 + `?contract=` 选择器 |
| `seek_probe/scripts/convert_contract_pdf.py` | **PDF→txt 转换器**:剥页眉页脚、行级 (y,x) 排序、y 间距合并、CJK 空格折叠 |
| `seek_probe/scripts/audit_reading_order.py` | **阅读顺序审计**:对比 sort vs native,标出顺序不一致的页 |
| `seek_probe/contracts/zacl0603.txt` | 当前合同语料(从 PDF 转换 + 手工校正,gitignored) |
| `seek_probe/contracts/sample_contract.txt` | 示例合同(书面中文) |
| `seek_probe/refs/cantonese_ref_trim.{wav,txt}` | 固定粤语参考音 + 转写(7s,本地、gitignored) |

## 8. 添加新合同 + 工具速查(换合同模板时照这个走)

```
1. 转换 PDF → txt(剥页眉页脚 + 行级阅读顺序):
   uv run python -m seek_probe.scripts.convert_contract_pdf \
       ~/Downloads/<新合同>.pdf -o seek_probe/contracts/<id>.txt
   # 看输出 "residual headers/footers" 应为 0;不为 0 说明页眉页脚模式不匹配,
   # 需在 convert_contract_pdf.DEFAULT_HEADER_PATTERNS / DEFAULT_FOOTER_PATTERNS 加模式。

2. 审计阅读顺序(标出 sort 与 native 不一致的页,只复核这些):
   uv run python -m seek_probe.scripts.audit_reading_order \
       ~/Downloads/<新合同>.pdf -o seek_probe/verify/audit.md
   # 打开 audit.md,对每个被标页对照 sort/native 两版,把读起来对的文本 patch 进 <id>.txt。
   # (两列布局用 native 对;行式表单用 sort 对;侧栏填空两种都可能要手工拼。)
   # ⚠️ patch 后别再重跑步骤 1(会覆盖手工校正)。

3. 注册合同:在 app.py 和 contract.py 的 _CONTRACT_FILES 各加一行 "<id>": .../contracts/<id>.txt。

4. 清缓存(归一化/分段变了,旧 wav 是孤儿):rm -f seek_probe/cache/*.wav

5. 抽测:跑 build_index 看 segment 数/中位长度;对地址段、公司名段、金额段各 normalize_for_tts
   一次,确认英文 L2、金额粤语、身份证逐位。
```

**工具速查**:

| 要做什么 | 用什么 |
|---|---|
| PDF 转成可读 txt(剥页眉页脚、重排阅读顺序) | `convert_contract_pdf.py` |
| 找出转换后哪些页阅读顺序可能有错 | `audit_reading_order.py` |
| 看某段会送什么文本给引擎 | `normalize_for_tts(seg.text)` 或 `zacl0603.normalized.txt` dump |
| 改完归一化/分段后清旧音频 | `rm seek_probe/cache/*.wav`(key 按归一化文本算,自动重生成) |
| 跑测试 | `uv run pytest -q` |

## 9. 约束与后续

- **参考音频必须 3–10 秒**(GPT-SoVITS 硬规则);当前用 `cantonese_ref_trim.wav`(7s)。
- `streaming_mode=False`:每段返回整段 WAV。冷 seek 延迟 ≈ 该段生成时间(M3 Max CPU RTF≈0.4,短段 ~1s);靠 §3 的预载 + §4 的缓存掩盖。
- `httpx trust_env=False`:本机有 clash 代理(`http_proxy=:7897`),否则 127.0.0.1 走代理 → 502。
- **含拉丁字母的文本**:触发 NLTK 英文前端,需 `~/nltk_data`(见 `engine-setup.md` 踩坑 #7)。
- **PDF 阅读顺序**:行级 `(y,x)` 排序对行式表单/内联金额正确;但对"两列 label/value"会错(见 §8 步骤 2 审计)。转换器是半自动——复杂布局靠审计 + 手工 patch `.txt`。换模板务必跑审计。
- **地区口音(HK/GZ)**:GPT-SoVITS 只有单一 `yue`(Jyutping),无地区开关;换参考音只改音色、不改发音。
- **长文(1 小时)**:本架构直接适用——1h ≈ 更多分段;静态内容靠 §4 内容寻址自动复用。

## 10. 与 spec 的差异(代码为准)

1. **TTS 回传**:spec 写"tee 流式 `StreamingResponse`";实际为"生成后响应 `Response` + 失败回 502/500"(为暴露引擎错误)。
2. **归一化层** `normalizer.py`(spec 未含):中文语境数字/金额/日期 → 粤语中文;英文地址/公司名 → L2 清洗保留英文(首字母大写 + 缩写展开)。缓存键基于**归一化后**的文本。
3. **`text_lang=yue` + L2**(非 spec 期决定):曾试 `auto_yue`(引擎自动切中英),实测会把英文后的 CJK 误读成日语 → 退回 `yue` + L2。
4. **PDF→txt 转换器 + 阅读顺序审计**(`scripts/`,spec 未含):合同源从手头 PDF 转换,剥页眉页脚、行级排序;审计工具标出顺序歧义页。
5. 缓存键由"段文本"改为"归一化段文本";`load_contract_text` 在 `contract.py` 定义但 `app.py` 用自带的 `_resolve_contract`(测试可注入),前者未被使用。
