# 启动与参数说明

> 面向运维/新接手同事:怎么把对外服务跑起来、每个参数什么意思、出问题看哪里。
> 架构与数据流见 `architecture.md`;引擎安装见 `engine-setup.md`。设计决策见 `docs/adr/`(ADR-0001..0008)。

## 1. 系统组成

| 部件 | 进程 | 端口 | 必需性 |
|---|---|---|---|
| TTS 引擎 | 自托管 GPT-SoVITS (`api_v2.py`) 和/或云端 Bailian CosyVoice | 9880（GPT-SoVITS） | 取决于各语言 profile 配置；可同时使用 |
| 后端 | `uvicorn backend.app:app` | 8000 | 必需 |
| 上传 demo | 静态页(后端挂载) | 8000 | 可选(调用方可自带前端) |
| 原文存储 | `uploaded/<contract_id>.txt`(内容寻址,gitignored) | — | 自动 |
| 音频缓存 | `cache/<sha256>.wav`(内容寻址,gitignored) | — | 自动 |

## 2. 启动

若三个语言全部使用同一种引擎，只启动下面对应的一套即可；混合配置时需要同时启动 GPT-SoVITS，并为使用 CosyVoice 的 profile 配置百炼 Key。

### A. 本地 GPT-SoVITS(默认)

```bash
# 终端 1:引擎(安装见 engine-setup.md)
cd /path/to/GPT-SoVITS && uv run python api_v2.py   # 监听 :9880

# 终端 2:后端 + 前端
uv run uvicorn backend.app:app --port 8000
```

默认使用参考音 `refs/cantonese_ref_trim.wav` + 同名粤语转写 txt（约 7 秒）。粤语直接合成；普通话和英语使用 GPT-SoVITS 跨语言合成。也可为普通话、英语配置各自的原生参考音。

### B. 云端 Bailian CosyVoice(无需本地引擎/参考音)

PowerShell 推荐使用本地 `.env` 文件；应用启动时会自动加载项目根目录下的 `.env`：

```powershell
Copy-Item .env.example .env
# 编辑 .env，填写 DASHSCOPE_API_KEY 和需要覆盖的 voice
uv run uvicorn backend.app:app --port 8000
```

百炼传输协议由 `.env` 选择。中国内地旧 HTTP 接口示例：

```dotenv
BAILIAN_TRANSPORT=http
BAILIAN_HTTP_BASE_URL=https://dashscope.aliyuncs.com
BAILIAN_MODEL=cosyvoice-v3-flash
```

新加坡 WebSocket 接口示例：

```dotenv
BAILIAN_TRANSPORT=wss
BAILIAN_WS_URL=wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference
BAILIAN_MODEL=cosyvoice-v3-flash
BAILIAN_WORKSPACE_ID=
```

若控制台提供业务空间专属 API Host，应使用对应的 `wss://.../api-ws/v1/inference`
地址并填写 `BAILIAN_WORKSPACE_ID`。API Key、端点、模型和音色必须属于同一地域。

也可以在 IntelliJ IDEA / PyCharm 中右键运行 `backend/app.py`；其内置入口会在
`127.0.0.1:8000` 同时启动 API 和静态前端。

`.env` 包含密钥并已被 Git 忽略；`.env.example` 只保存可提交的配置模板。系统或进程中已经设置的环境变量优先于 `.env`。
修改 `.env` 后需要重启服务，应用启动时才会重新读取 Engine Profile。

也可以直接设置进程环境变量：

```bash
export DASHSCOPE_API_KEY=sk-...
CONTRACT_TTS_ENGINE=bailian uv run uvicorn backend.app:app --port 8000
```

新加坡节点只支持 WebSocket TTS 时，可先独立运行诊断脚本，不经过合同切分、
归一化或缓存：

```powershell
uv run python scripts/debug_bailian_singapore_tts.py --check-config
uv run python scripts/debug_bailian_singapore_tts.py
```

脚本默认使用已验证的新加坡公共 WebSocket 地址；若控制台提供了专属 API Host，
通过 `--url` 指定其 `wss://.../api-ws/v1/inference` 地址。可用 `--model`、
`--voice`、`--text` 和 `--output` 覆盖测试参数，脚本不会输出完整 API Key。

### 打开 demo

http://127.0.0.1:8000 —— 粘贴合同 TXT →「上傳並切片」→ 拖进度条 seek / 播放。
(不再有 `?contract=` 选择器;合同改为上传进件。)

## 3. 参数一览

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CONTRACT_TTS_ENGINE` | `gptsovits` | 未单独配置语言时的回退引擎：`gptsovits` / `cosyvoice`（`bailian` 同义）。**切换需重启服务** |
| `CONTRACT_TTS_ENGINE_YUE` | 回退到 `CONTRACT_TTS_ENGINE` | 粤语 profile 独立引擎：`gptsovits` 或 `cosyvoice`（`bailian` 同义） |
| `CONTRACT_TTS_ENGINE_ZH` | 回退到 `CONTRACT_TTS_ENGINE` | 普通话 profile 独立引擎 |
| `CONTRACT_TTS_ENGINE_EN` | 回退到 `CONTRACT_TTS_ENGINE` | 英语 profile 独立引擎 |
| `GPTSOVITS_ENGINE_URL` | `http://127.0.0.1:9880` | GPT-SoVITS 服务地址；可为同机或远程主机 |
| `GPTSOVITS_REF_AUDIO` | `refs/cantonese_ref_trim.wav` | 三种语言共用的回退参考音（必须 3–10 秒） |
| `GPTSOVITS_REF_AUDIO_ENGINE_PATH` | 本地参考音路径 | GPT-SoVITS 在另一主机/容器时，该引擎能访问的参考音路径 |
| `GPTSOVITS_REF_PROMPT` | `refs/cantonese_ref_trim.txt` | 共用参考音的逐字转写文件 |
| `GPTSOVITS_REF_PROMPT_LANG` | `yue` | 共用参考音实际使用的语言，不是目标文本语言 |
| `GPTSOVITS_REF_AUDIO_ZH/EN` | 无 | 可选普通话/英语专属参考音；未配置时回退共用粤语参考音 |
| `GPTSOVITS_REF_AUDIO_ENGINE_PATH_ZH/EN` | 无 | 专属参考音在远程 GPT-SoVITS 主机上的路径 |
| `GPTSOVITS_REF_PROMPT_ZH/EN` | 无 | 专属参考音的逐字转写文件 |
| `GPTSOVITS_REF_PROMPT_LANG_ZH/EN` | `zh/en` | 配置专属参考音时的参考音语言；可显式覆盖 |
| `DASHSCOPE_API_KEY` | 无 | `bailian` 引擎必需 |
| `BAILIAN_TRANSPORT` | `http` | 百炼协议：`http` 或 `wss`；新加坡使用 `wss` |
| `BAILIAN_HTTP_BASE_URL` | `https://dashscope.aliyuncs.com` | HTTP SpeechSynthesizer 基础地址 |
| `BAILIAN_WS_URL` | `wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference` | WebSocket TTS 地址 |
| `BAILIAN_MODEL` | `cosyvoice-v3-flash` | 百炼模型；更换时提升所有受影响 profile 的缓存版本 |
| `BAILIAN_WORKSPACE_ID` | 无 | 可选业务空间 ID；使用专属 API Host 时按控制台配置 |
| `BAILIAN_VOICE` | `longjiaxin_v3` | 云端粤语音色;更换时同步提升 `ENGINE_PROFILE_CACHE_VERSION_YUE` |
| `BAILIAN_VOICE_ZH` | `longxiaochun` | 云端普通话音色;更换时提升 `ENGINE_PROFILE_CACHE_VERSION_ZH` |
| `BAILIAN_VOICE_EN` | `longanyang` | 云端英语音色;更换时提升 `ENGINE_PROFILE_CACHE_VERSION_EN` |
| `ENGINE_PROFILE_CACHE_VERSION_YUE` | `v1` | 粤语 profile 缓存版本;影响音频的配置变化时提升 |
| `ENGINE_PROFILE_CACHE_VERSION_ZH` | `v1` | 普通话 profile 缓存版本;换 voice/model/参数时提升 |
| `ENGINE_PROFILE_CACHE_VERSION_EN` | `v1` | 英语 profile 缓存版本;换 voice/model/参数时提升 |

### 代码内固定配置

| 常量 | 值 | 说明 |
|---|---|---|
| `TEMPLATE_REGISTRY` | `xcash_yue`, `xcash_zh`, `xcash_en` | 接受的 `template_id`; `xcash` 是 `xcash_yue` 别名 |

本地 GPT-SoVITS 和配置 API key 后的云端 Bailian 都提供三个独立 profile。GPT-SoVITS 的 `xcash_zh` 使用 `text_lang=zh`（中英混合），`xcash_en` 使用 `text_lang=en`；目标语言与参考音的 `prompt_lang` 独立。

三个 profile 可混合选择引擎。例如粤语、英语用 GPT-SoVITS，普通话使用 CosyVoice：

```dotenv
CONTRACT_TTS_ENGINE=gptsovits
CONTRACT_TTS_ENGINE_YUE=gptsovits
CONTRACT_TTS_ENGINE_ZH=cosyvoice
CONTRACT_TTS_ENGINE_EN=gptsovits
```

使用 `cosyvoice` 的 profile 必须配置 `DASHSCOPE_API_KEY`；没有 Key 时只禁用对应 profile，其他 GPT-SoVITS profile 仍可使用。切换某个 profile 的引擎后，Engine Profile ID 会变化，缓存会自动隔离，无需清除其他语言缓存。

> 合同由调用方 `POST /api/contracts {text, template_id}` 上传,**不再预注册、无 `?contract=`**。

## 4. 它是怎么工作的

上传 → 确定性切片 → 逐段按需归一化 → 内容寻址缓存 → 音频。数据流主线与各环节细节见 `architecture.md` §0.5 / §2(此处不重复)。

## 5. 常见运维操作

| 要做什么 | 怎么做 |
|---|---|
| 换引擎 | 改全局或对应语言的 `CONTRACT_TTS_ENGINE_*` 后重启；键含 profile 引擎，旧音频自动不再命中并由 30 天滑动窗口清理 |
| 换本地参考音 | 替换共用参考音时提升三个 profile 的缓存版本；只换 `ZH/EN` 专属参考音时仅提升对应版本。完整步骤见 `engine-setup.md` §4 |
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
