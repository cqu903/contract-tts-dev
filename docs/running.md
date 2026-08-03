# 启动与参数说明

> 面向运维/新接手同事:怎么把对外服务跑起来、每个参数什么意思、出问题看哪里。
> 架构与数据流见 `architecture.md`;引擎安装见 `engine-setup.md`。设计决策见 `docs/adr/`(ADR-0001..0008)。

## 1. 系统组成

| 部件 | 进程 | 端口 | 必需性 |
|---|---|---|---|
| TTS 引擎 | 本地 GPT-SoVITS (`api_v2.py`) 或云端 Bailian CosyVoice(无本地进程) | 9880(本地) | 二选一 |
| 后端 | `uvicorn backend.app:app` | 8000 | 必需 |
| 上传 demo | 静态页(后端挂载) | 8000 | 可选(调用方可自带前端) |
| 原文存储 | `uploaded/<contract_id>.txt`(内容寻址,gitignored) | — | 自动 |
| 音频缓存 | `cache/<sha256>.wav`(内容寻址,gitignored) | — | 自动 |

## 2. 启动

### A. 本地 GPT-SoVITS(默认)

```bash
# 终端 1:引擎(安装见 engine-setup.md)
cd /path/to/GPT-SoVITS && uv run python api_v2.py   # 监听 :9880

# 终端 2:后端 + 前端
uv run uvicorn backend.app:app --port 8000
```

需要参考音 `refs/cantonese_ref_trim.wav` + 同名转写 txt(7 秒,gitignored)。

### B. 云端 Bailian CosyVoice(无需本地引擎/参考音)

PowerShell 推荐使用本地 `.env` 文件；应用启动时会自动加载项目根目录下的 `.env`：

```powershell
Copy-Item .env.example .env
# 编辑 .env，填写 DASHSCOPE_API_KEY 和需要覆盖的 voice
uv run uvicorn backend.app:app --port 8000
```

`.env` 包含密钥并已被 Git 忽略；`.env.example` 只保存可提交的配置模板。系统或进程中已经设置的环境变量优先于 `.env`。
修改 `.env` 后需要重启服务，应用启动时才会重新读取 Engine Profile。

也可以直接设置进程环境变量：

```bash
export DASHSCOPE_API_KEY=sk-...
CONTRACT_TTS_ENGINE=bailian uv run uvicorn backend.app:app --port 8000
```

### 打开 demo

http://127.0.0.1:8000 —— 粘贴合同 TXT →「上傳並切片」→ 拖进度条 seek / 播放。
(不再有 `?contract=` 选择器;合同改为上传进件。)

## 3. 参数一览

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CONTRACT_TTS_ENGINE` | `gptsovits` | 引擎:`gptsovits`(本地)/ `bailian`(云端)。**切换需重启服务** |
| `DASHSCOPE_API_KEY` | 无 | `bailian` 引擎必需 |
| `BAILIAN_VOICE` | `longjiaxin_v3` | 云端粤语音色;更换时同步提升 `ENGINE_PROFILE_CACHE_VERSION_YUE` |
| `BAILIAN_VOICE_ZH` | `longxiaochun` | 云端普通话音色;更换时提升 `ENGINE_PROFILE_CACHE_VERSION_ZH` |
| `BAILIAN_VOICE_EN` | `longanyang` | 云端英语音色;更换时提升 `ENGINE_PROFILE_CACHE_VERSION_EN` |
| `ENGINE_PROFILE_CACHE_VERSION_YUE` | `v1` | 粤语 profile 缓存版本;影响音频的配置变化时提升 |
| `ENGINE_PROFILE_CACHE_VERSION_ZH` | `v1` | 普通话 profile 缓存版本;换 voice/model/参数时提升 |
| `ENGINE_PROFILE_CACHE_VERSION_EN` | `v1` | 英语 profile 缓存版本;换 voice/model/参数时提升 |

### 硬编码常量(`backend/app.py` 顶部,改需动代码)

| 常量 | 值 | 说明 |
|---|---|---|
| `ENGINE_URL` | `http://127.0.0.1:9880` | 本地引擎地址 |
| `REF_AUDIO` / `REF_PROMPT` | `refs/cantonese_ref_trim.{wav,txt}` | 本地引擎参考音(必须 3–10 秒) |
| `TEMPLATE_REGISTRY` | `xcash_yue`, `xcash_zh`, `xcash_en` | 接受的 `template_id`; `xcash` 是 `xcash_yue` 别名 |

本地 GPT-SoVITS 第一阶段只提供 `xcash_yue`;在本地模式选择 `xcash_zh` 或
`xcash_en` 会在上传阶段返回 `503`。云端 Bailian 在配置 API key 后提供三个
独立 profile。

> 合同由调用方 `POST /api/contracts {text, template_id}` 上传,**不再预注册、无 `?contract=`**。

## 4. 它是怎么工作的

上传 → 确定性切片 → 逐段按需归一化 → 内容寻址缓存 → 音频。数据流主线与各环节细节见 `architecture.md` §0.5 / §2(此处不重复)。

## 5. 常见运维操作

| 要做什么 | 怎么做 |
|---|---|
| 换引擎 | 改 `CONTRACT_TTS_ENGINE` **重启服务**(无需手动清缓存;键含引擎,旧引擎缓存自动失效、由 30 天滑动窗口清理——ADR-0006) |
| 换本地参考音 | 替换 `refs/cantonese_ref_trim.*` 后提升 `ENGINE_PROFILE_CACHE_VERSION_YUE`，使旧音频不再命中；完整步骤见 `engine-setup.md` §4 |
| 过期项清理 | **自动**:服务启动清一次 + 后台每 24h 清一次(原文 90d / 音频 30d,ADR-0007);正常无需手动 `rm` |
| 看某段实际喂引擎的文本 | `python -c "from backend.normalizer import normalize_for_tts; print(normalize_for_tts('<段文本>'))"` |
| 看切片结果 | 对上传后的 contract_id 调 `contract.dump_segments(build_index(cid, text), path)` |
| 跑测试 | `uv run pytest -q` |

## 6. 排障

| 症状 | 原因与处理 |
|---|---|
| 取段音频 **500** | 本地引擎没起(:9880 连接失败);或代理劫持(代码已 `trust_env=False`,改 httpx 时保留) |
| 取段音频 **502** | 引擎在但回错状态(看响应 detail) |
| `POST /api/contracts` **400** | `template_id` 未注册,或 text 为空 |
| `POST /api/contracts` **503** | Template 已注册但对应 Engine Profile 未配置 |
| `GET /api/contracts/{id}` **404** | contract_id 未知,或原文已被 90 天 TTL 清理 → 重新上传 |
| 云端合成偶发 429 | cosyvoice-v3-flash 限流 3 QPM,预载并发排队,稍等重试 |
| 浏览器音频时长显示巨大 | cosyvoice wav 头时长字段占位,按 EOF 播放,不影响功能 |
| `uv run pytest` 报 `No module named 'cn2an'` | `.venv` 陈旧 → `uv sync --reinstall` |
| 某字读错(多音字) | 在 `normalizer.py` 加同音字/替换(先例 `還→環`、`注：→注，`),勿改合同原文 |
