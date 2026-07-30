# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作提供指引。

## 沟通语言

**本项目使用中文沟通。** 与用户的所有交流（解释、总结、提问、状态汇报）一律使用中文。代码注释、标识符、提交信息沿用既有约定（现有注释以中文为主）。

## 这是什么

一个**可行性探针**：用**粤语**朗读香港贷款 / 金融合同，带可拖动进度条，基于 **GPT-SoVITS**（本地）或 **百炼 CosyVoice**（云端）。核心思路：把全文确定性切片、把 seek 位置映射到第 N 段、内容寻址音频让静态样板只生成一次处处复用、并在合成前一刻对每段做归一化（数字 / 日期 / 金额 → 粤语读法）。所有代码在 `seek_probe/` 下。

这是 **spike / 探针代码**，不是生产代码。决策以"证明可行"优先于健壮性；引擎被刻意解耦，以便把音色质量风险单独隔离。

## 命令

全部在仓库根目录用 **`uv`** 运行（Python 3.12，`.python-version` 声明；`tool.uv.package = false` —— 这不是可安装的包）。

```bash
uv run pytest -q                         # 测试（62 个），含 FastAPI TestClient + normalizer/segmenter/cache
uv run pytest seek_probe/tests/test_normalizer.py -q     # 单个文件
uv run pytest seek_probe/tests/test_segmenter.py::test_name -q   # 单个测试

uv run uvicorn seek_probe.backend.app:app --port 8000 --reload   # 后端 + 静态前端，开 http://127.0.0.1:8000

# 云端引擎替代本地 GPT-SoVITS（无需本地引擎 / 参考音）：
DASHSCOPE_API_KEY=sk-... SEEK_PROBE_ENGINE=bailian uv run uvicorn seek_probe.backend.app:app --port 8000

# 不起服务，看某段经过归一化后实际喂给引擎的文本：
uv run python -c "from seek_probe.backend.normalizer import normalize_for_tts; print(normalize_for_tts('<段文本>'))"

# 把每个注册合同的原始切片结果落到 contracts/<id>.segments.txt，便于调参：
SEEK_PROBE_DUMP_SEGMENTS=1 uv run uvicorn seek_probe.backend.app:app --port 8000
```

**本地 TTS 引擎是另一个独立仓库**，位于 `/Users/roy/codes/GPT-SoVITS`，跑在它自己的 **Python 3.10** venv 里：`cd /Users/roy/codes/GPT-SoVITS && uv run python api_v2.py`（监听 `:9880`）。安装步骤与众多 M0 踩坑见 `seek_probe/docs/engine-setup.md`。**测试不依赖引擎**（客户端已 mock）。

## 架构（全局视角）

浏览器 ↔ FastAPI 后端（`seek_probe/backend/app.py`）↔ 外部 TTS 引擎，中间夹一层磁盘缓存。权威 as-built 描述见 `seek_probe/docs/architecture.md`；运维 / 参数见 `seek_probe/docs/running.md`。

**逐段流水线**（系统的主干，全部在 `seek_probe/backend/`）：

```
合同 TXT → split_contract (segmenter.py, 确定性)        → build_index (contract.py: 段 + 预估时长 + 累积起点)
        → normalize_for_tts (normalizer.py, 逐段按需)   → engine.synth (gptsovits_client | bailian_cosyvoice_client)
        → cache.put (cache.py)                          → Response(audio/wav)
```

模块职责：
- **`segmenter.py`** —— `split_contract(text)` → `Segment` 列表。硬边界 = `。！？；` + 换行；行内子句按 `，、;` 切，仍超长再按 `：（《(` 拆；短碎片向 `TARGET=20` 合并、`SOFT_MAX=45` 封顶、超过 `HARD_MAX=50` 强拆。**确定性** —— 同文本永远同分段（缓存键稳定的前提）。
- **`contract.py`** —— `build_index`（段 + 累积时间 + `total_est_s`）、`position_to_segment`（seek → 吸附段边界）。也持有一份 `_CONTRACT_FILES`（见陷阱）。
- **`normalizer.py`** —— `normalize_for_tts`。按语言分流：英文片段（地址 / 公司名）做 L2 清洗（全大写 → 首字母大写、展开 `FLT→Flat`/`BLK→Block`/`39/F→39th Floor`、数字保留）并保持英文，由 `yue` 前端读成词；中文语境的数字 / 金额 / 日期 / 身份证 / 罗马序号 → 粤语中文（`cn2an`）。依赖 `cn2an`。
- **`cache.py`** —— `cache_key(text, voice_ref_id)` + `SegmentCache`。内容寻址：相同文本在所有合同里复用同一个文件。
- **`app.py`** —— FastAPI。端点：`GET /api/contract/{id}`（段 + 文本 + 时间）、`GET /api/segment/{id}/{n}`（音频，per-key `asyncio.Lock` 二次查缓存做并发去重）、`POST /api/preload/{id}/{n}`（后台预热后 K=3 段）。静态前端挂在 `/`。
- **`frontend/app.js`** —— 把 `range(0..1000)` 进度条映射到 `[0, total_est_s]`（音频没生成也能拖）、定位到所属段、播完 `ended` 自动续、同时触发预载。

**换引擎代价很小（设计如此）：** 两个 client 都实现 `synth(text) -> AsyncIterator[bytes]`；`app.make_engine(SEEK_PROBE_ENGINE)` 选其一。归一化、seek、缓存全部共用。

## 关键陷阱（不直观，会踩）

- **合同要注册两次。** 新增合同必须同时改 `app.py` 和 `contract.py` 两处的 `_CONTRACT_FILES`。漏一处，该合同会静默无法解析（404）。合同**只接受 TXT、只读**（系统永不回写）；真实合同含 PII 已 gitignore（仅 `sample_contract.txt` 被跟踪）。
- **缓存键不含引擎 / 音色** —— 只有 `sha256(归一化文本 + VOICE_REF_ID)`。切换引擎 / 音色（`SEEK_PROBE_ENGINE` / `BAILIAN_VOICE`）或换参考音**而不清缓存，会返回错误 / 陈旧音频**。先 `rm -f seek_probe/cache/*.wav`。换本地参考音还必须改 `app.py` 里的 `VOICE_REF_ID`。
- **`httpx(trust_env=False)` 是承重墙**，两个引擎 client 都靠它。开发机开着 clash 代理（`:7897`）；不 `trust_env=False`，`127.0.0.1` / dashscope 请求会走代理 → 502。改 httpx 调用时务必保留。
- **云端路径不能省归一化。** CosyVoice 自带 TN 只覆盖日期和基础金额；逐位读法（电话 / 身份证 / 型号）、`HK$→港幣`、罗马序号仍要靠 `normalizer.py`。本地与云端路径结构完全一致（归一化 → 引擎）。
- **生成后响应，不是边生成边 tee 流。** `get_segment` 先把整段字节收齐，*再*返回 `Response`。这是有意为之：引擎失败时能回明确的 `502`/`500`，而不是被浏览器吞成空的 `200`（表现为模糊的 "Load failed"）。`streaming_mode=true`（降冷 seek 延迟）是已记录的非目标 —— 其分块格式随版本变。
- **`text_lang="yue"`，不是 `auto_yue`。** 实测：`auto_yue` 会把英文公司名*之后*的 CJK 误判成日语（共享汉字歧义）。`yue` + L2 首字母大写即可让英文被读成词、CJK 恒为粤语。

## 约定

- 测试对 `app.py` 用 FastAPI `TestClient`（通过 `app.make_engine` / `_resolve_contract` 注入依赖），HTTP client 已 mock —— 不需要真引擎。
- 当引擎读错某个字（多音字、问题 token）时，**在 `normalizer.py` 里修**（同音字替换 / token 改写 —— 已有 `還→環`、`注：→注，` 先例），**绝不改合同原文**。
- 深层设计上下文在 `docs/superpowers/`（`specs/` 设计 spec、`plans/` 实施计划）。`seek_probe/docs/architecture.md` §10 记录了代码有意偏离 spec 的地方。
