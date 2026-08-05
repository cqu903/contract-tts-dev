# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作提供指引。

## 沟通语言

**本项目使用中文沟通。** 与用户的所有交流（解释、总结、提问、状态汇报）一律使用中文。代码注释、标识符、提交信息沿用既有约定（现有注释以中文为主）。

## 这是什么

一个**对外粤语合同 TTS 服务**（由可行性探针演进而来）：调用方上传香港贷款 / 金融合同 TXT，服务用**粤语**朗读，带可拖动进度条与按段 seek。基于 **GPT-SoVITS**（本地）或 **百炼 CosyVoice**（云端）。核心思路：把全文确定性切片、把 seek 位置映射到第 N 段、内容寻址音频让静态样板只生成一次处处复用、并在合成前一刻对每段做归一化（数字 / 日期 / 金额 → 粤语读法）。代码在 `` 下；设计决策见 `docs/adr/`(ADR-0001..0007) + `CONTEXT.md`。

> 起源于 spike，v1 仍带探针气质：决策以"证明可行"优先于健壮性；引擎被刻意解耦，以便把音色质量风险单独隔离。

## 命令

全部在仓库根目录用 **`uv`** 运行（Python 3.12，`tool.uv.package = false` —— 不可安装包，直接跑源码）。完整参数 / 排障见 `docs/running.md`。

```bash
uv run pytest -q                                       # 测试（不依赖引擎，已 mock）
uv run uvicorn backend.app:app --port 8000  # 起服务，开 http://127.0.0.1:8000
# 云端引擎：DASHSCOPE_API_KEY=sk-... CONTRACT_TTS_ENGINE=bailian uv run uvicorn backend.app:app --port 8000
# 看某段归一化后实际喂引擎的文本：
uv run python -c "from backend.normalizer import normalize_for_tts; print(normalize_for_tts('<段文本>'))"
```

**本地 TTS 引擎**是独立仓库 `/path/to/GPT-SoVITS`（Python 3.10 venv）：`cd /path/to/GPT-SoVITS && uv run python api_v2.py`（监听 `:9880`）。安装步骤与踩坑见 `docs/engine-setup.md`。**测试不依赖引擎**（客户端已 mock）。

## 架构（全局视角）

浏览器 ↔ FastAPI 后端（`backend/app.py`）↔ 外部 TTS 引擎，中间夹一层内容寻址磁盘缓存。**权威 as-built 见 `docs/architecture.md`**（数据流主线、seek 逻辑、缓存、归一化表、文件地图、约束）；运维 / 参数见 `docs/running.md`。本节只给指针与最关键的形状。

主干（`backend/`）：上传合同 TXT → 确定性切片（`segmenter.split_contract`）→ 逐段按需归一化（`normalizer.normalize_for_tts`）→ `engine.synth` → 内容寻址缓存（`cache.SegmentCache`）→ `audio/wav`。

**换引擎代价很小（设计如此）：** 两个 client 都实现 `synth(text) -> AsyncIterator[bytes]`；`app.make_engine(CONTRACT_TTS_ENGINE)` 选其一。归一化、seek、缓存全部共用。

## 关键陷阱（不直观，会踩）

- **合同改外部上传，不再预注册。** 对外入口 `POST /api/contracts`（JSON `{text, template_id}`）→ `contract_id = sha256(template_id | 原文)`，原文落盘 `uploaded/<cid>.txt`（内容寻址、90 天 creation TTL，见 ADR-0001/0004）。`app.py` / `contract.py` 的 `_CONTRACT_FILES` 与 `load_contract_text` 已删；`template_id` 必传、v1 仅接受 `xcash`（未知 → 400，见 ADR-0005）。真实合同含 PII：`contracts/*` 与 `uploaded/` 均 gitignore（仅 `sample_contract.txt` 被跟踪）。
- **缓存键 = 归一化文本 + 引擎（ADR-0006）。** `cache_key = sha256(归一化文本 + ENGINE_NAME)` —— 切换引擎（`CONTRACT_TTS_ENGINE`）**不会**脏读：旧引擎缓存自动失效、由 30 天滑动窗口清理，无需手动 `rm`。音色是引擎内部固定属性、**不在键里**：换本地参考音（`refs/cantonese_ref_trim.*`）或云端音色（`BAILIAN_VOICE`）**不会**自动失效缓存——须手动 bump `CONTRACT_TTS_ENGINE`（如 `gptsovits-v2`）或清 `cache/`，否则旧音最长存活 30 天。
- **过期清理是后台任务，不是 cron（ADR-0007）。** 服务启动清一次 + 进程内 asyncio 周期任务每 24h 清一次（原文 90d PII + 音频 30d，合并成单次 `run_cleanup()`）。evict 同步直调、阻塞事件循环 ~27ms/天——**这是故意的**（丢 `to_thread` 会引入 manifest 跨线程竞态、需加锁，不值）；规模增长致阻塞可感知时再上分批 / to_thread。
- **`httpx(trust_env=False)` 是承重墙**，两个引擎 client 都靠它。开发机开着 clash 代理（`:7897`）；不 `trust_env=False`，`127.0.0.1` / dashscope 请求会走代理 → 502。改 httpx 调用时务必保留。
- **云端路径不能省归一化。** CosyVoice 自带 TN 只覆盖日期和基础金额；逐位读法（电话 / 身份证 / 型号）、`HK$→港幣`、罗马序号仍要靠 `normalizer.py`。本地与云端路径结构完全一致（归一化 → 引擎）。
- **生成后响应，不是边生成边 tee 流。** `get_segment` 先把整段字节收齐，*再*返回 `Response`。这是有意为之：引擎失败时能回明确的 `502`/`500`，而不是被浏览器吞成空的 `200`（表现为模糊的 "Load failed"）。`streaming_mode=true`（降冷 seek 延迟）是已记录的非目标 —— 其分块格式随版本变。
- **`text_lang="yue"`，不是 `auto_yue`。** 实测：`auto_yue` 会把英文公司名*之后*的 CJK 误判成日语（共享汉字歧义）。`yue` + L2 首字母大写即可让英文被读成词、CJK 恒为粤语。

## 约定

- 测试对 `app.py` 用 FastAPI `TestClient`，靠 `monkeypatch.setattr(appmod, "engine" / "cache" / "CONTRACT_STORE")` 注入依赖（见 `tests/test_app.py`），HTTP client 已 mock —— 不需要真引擎。
- 当引擎读错某个字（多音字、问题 token）时，**在 `normalizer.py` 里修**（同音字替换 / token 改写 —— 已有 `還→環`、`注：→注，` 先例），**绝不改合同原文**。
- 深层设计上下文在 `docs/adr/`（ADR-0001..0007）与 `CONTEXT.md`（领域语言）；`docs/architecture.md` 是 as-built，可能滞后于最新代码——以代码为准。

## Agent skills

### Issue tracker

Issues and specs live as local Markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo using root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.
