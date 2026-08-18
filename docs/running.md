# 启动与参数说明

> 面向运维/新接手同事:怎么把对外服务跑起来、每个参数什么意思、出问题看哪里。
> 架构与数据流见 `architecture.md`;引擎安装见 `engine-setup.md`。设计决策见 `docs/adr/`(ADR-0001..0009)。
> Docker 单实例生产部署见 `docker-deployment.md`。

## 1. 系统组成

| 部件 | 进程 | 端口 | 必需性 |
|---|---|---|---|
| TTS 引擎 | 自托管 GPT-SoVITS (`api_v2.py`)、云端 Bailian CosyVoice 和/或 Microsoft Provider（Edge/Azure Driver） | 9880（GPT-SoVITS）；云端引擎使用出站 HTTPS/WSS | 取决于各语言 profile 配置；可同时使用 |
| 后端 | `uvicorn backend.app:app` | 8000 | 必需 |
| 上传 demo | 静态页(后端挂载) | 8000 | 可选(调用方可自带前端) |
| 原文存储 | `uploaded/<contract_id>.txt`(内容寻址,gitignored) | — | 自动 |
| 音频缓存 | `cache/<sha256>.<format>`(内容寻址,gitignored) | — | 自动；WAV/MP3 由 Audio Artifact 决定 |

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

### C. Microsoft Provider / Edge 或 Azure Driver

Microsoft 是与 GPT-SoVITS、CosyVoice 同级的稳定 Engine Provider；必须显式选择 `edge` 或正式 Azure Speech SDK 的 `azure` Driver。三个语言都使用 Edge 时：

```dotenv
CONTRACT_TTS_ENGINE=microsoft
MICROSOFT_TTS_DRIVER=edge
MICROSOFT_TTS_VOICE_YUE=zh-HK-WanLungNeural
MICROSOFT_TTS_RATE_YUE=+0%
MICROSOFT_TTS_VOICE_ZH=zh-CN-YunyangNeural
MICROSOFT_TTS_RATE_ZH=+0%
MICROSOFT_TTS_VOICE_EN=en-HK-SamNeural
MICROSOFT_TTS_RATE_EN=+0%
```

正式 Azure Speech 使用同一组三语言 voice/rate，并增加资源凭据和位置：

```dotenv
CONTRACT_TTS_ENGINE=microsoft
MICROSOFT_TTS_DRIVER=azure
AZURE_SPEECH_KEY=replace-with-your-azure-speech-key
AZURE_SPEECH_REGION=eastasia
# 可选：设置后优先于 Region，必须使用 Azure 提供的 HTTPS Endpoint
# AZURE_SPEECH_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
```

Key 与 Region 必须属于同一个 Azure Speech 资源。使用自定义域、主权云或 Azure 门户提供的资源 Endpoint 时设置 `AZURE_SPEECH_ENDPOINT`；代码把 Key+Endpoint 交给官方 SDK，不自行拼接 REST 地址。Key 不进入日志、错误详情、缓存 manifest 或 synthesis fingerprint。

也可以只为部分 Reading Language 选择 Microsoft，例如粤语和英语用 Edge、普通话继续使用 CosyVoice：

```dotenv
CONTRACT_TTS_ENGINE=cosyvoice
CONTRACT_TTS_ENGINE_YUE=microsoft
CONTRACT_TTS_ENGINE_EN=microsoft
MICROSOFT_TTS_DRIVER=edge
```

`voice` 与基准 `rate` 只能由服务端部署配置覆盖。Edge 的 `rate` 使用带符号整数百分比（例如 `-10%`、`+0%`、`+15%`）；Azure 还接受 SSML 小数百分比（例如 `+33.33%`、`-15.00%`）。修改引擎、Driver、voice 或 rate 后必须重启服务，运行中的 Engine Profile 不会热加载 `.env`。

服务启动、健康检查和默认测试只做本地配置校验，不访问 Edge/Azure，也不会在线检查 voice。部署验收时主动运行独立诊断：

```powershell
uv run python scripts/diagnose_microsoft_tts.py
# 可选输出目录
uv run python scripts/diagnose_microsoft_tts.py --output-dir .scratch/microsoft-edge-tts/diagnostics
```

诊断固定使用仓库内三条简短、无敏感信息的合同风格测试句，不读取真实 Contract、上传目录或 Segment Cache。命令会在联网前打印外发警告，逐语言显示实际 Driver、voice 和 rate，分别保存 `microsoft-<driver>-yue.mp3`、`microsoft-<driver>-zh.mp3`、`microsoft-<driver>-en.mp3`，并验证文件非空且具有 MP3 标识。某一种语言失败时另外两种仍会执行；任一失败使退出码为 `1`，全部成功为 `0`。请在部署验收环境人工试听三份文件；该真实网络诊断不属于默认 CI 门禁。旧 `diagnose_microsoft_edge_tts.py` 仅作为兼容入口保留。

Edge Driver 保留上游原生 MP3；Azure Driver 请求 `Audio24Khz48KBitRateMonoMp3`，两者 HTTP 均为 `audio/mpeg`。GPT-SoVITS 与 CosyVoice 继续输出 WAV/`audio/wav`。服务端不转码，客户端和 Segment Cache 都按 Audio Artifact 中的实际格式、媒体类型和扩展名处理。

### 打开 demo

http://127.0.0.1:8000 —— 粘贴合同 TXT →「上傳並切片」→ 拖进度条 seek / 播放。粤语默认使用 `1.1x`，播放器也提供 `1.0/1.1/1.15/1.25x` 手动档位。
(不再有 `?contract=` 选择器;合同改为上传进件。)

## 3. 参数一览

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CONTRACT_TTS_ENGINE` | `gptsovits` | 未单独配置语言时的回退引擎：`gptsovits` / `cosyvoice`（`bailian` 同义）/ `microsoft`。**切换需重启服务** |
| `CONTRACT_TTS_ENGINE_YUE` | 回退到 `CONTRACT_TTS_ENGINE` | 粤语 profile 独立引擎：`gptsovits`、`cosyvoice` 或 `microsoft` |
| `CONTRACT_TTS_ENGINE_ZH` | 回退到 `CONTRACT_TTS_ENGINE` | 普通话 profile 独立引擎 |
| `CONTRACT_TTS_ENGINE_EN` | 回退到 `CONTRACT_TTS_ENGINE` | 英语 profile 独立引擎 |
| `MICROSOFT_TTS_DRIVER` | 无 | 任一 profile 选择 `microsoft` 时必须显式设为 `edge` 或 `azure` |
| `MICROSOFT_TTS_VOICE_YUE` | `zh-HK-WanLungNeural` | Microsoft 粤语 voice；修改后重启，fingerprint 自动隔离旧缓存 |
| `MICROSOFT_TTS_RATE_YUE` | `+0%` | Microsoft 粤语基准语速；修改后重启，不修正预计时长 |
| `MICROSOFT_TTS_VOICE_ZH` | `zh-CN-YunyangNeural` | Microsoft 普通话 voice |
| `MICROSOFT_TTS_RATE_ZH` | `+0%` | Microsoft 普通话基准语速 |
| `MICROSOFT_TTS_VOICE_EN` | `en-HK-SamNeural` | Microsoft 英语 voice |
| `MICROSOFT_TTS_RATE_EN` | `+0%` | Microsoft 英语基准语速 |
| `AZURE_SPEECH_KEY` | 无 | `azure` Driver 必需；Azure Speech 资源 Key，视为 secret，不进入缓存或日志 |
| `AZURE_SPEECH_REGION` | 无 | 未配置 Endpoint 时必需；Azure Speech 资源的 Region 标识，例如 `eastasia` |
| `AZURE_SPEECH_ENDPOINT` | 无 | 可选 HTTPS 资源 Endpoint；设置后 SDK 使用 Endpoint 模式并优先于 Region |
| `GPTSOVITS_ENGINE_URL` | `http://127.0.0.1:9880` | GPT-SoVITS 服务地址；可为同机或远程主机 |
| `GPTSOVITS_REF_AUDIO` | `refs/cantonese_ref_trim.wav` | 三种语言共用的回退参考音（必须 3–10 秒） |
| `GPTSOVITS_REF_AUDIO_ENGINE_PATH` | 本地参考音路径 | GPT-SoVITS 在另一主机/容器时，该引擎能访问的参考音路径 |
| `GPTSOVITS_REF_PROMPT` | `refs/cantonese_ref_trim.txt` | 共用参考音的逐字转写文件 |
| `GPTSOVITS_REF_PROMPT_LANG` | `yue` | 共用参考音实际使用的语言，不是目标文本语言 |
| `GPTSOVITS_FRAGMENT_INTERVAL_YUE` | `0.05` | 粤语 GPT-SoVITS 片段静音秒数；降低官方默认的明显停顿 |
| `GPTSOVITS_TEXT_SPLIT_METHOD_YUE` | `cut0` | 粤语请求不在引擎内二次切句；合同已由 Template 切段 |
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
| `ENGINE_PROFILE_CACHE_VERSION_YUE` | `v2` | 粤语 profile 缓存版本;影响音频的配置变化时提升 |
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
| 验证 Microsoft | 运行 `uv run python scripts/diagnose_microsoft_tts.py`，确认退出码为 0 并人工试听三份 MP3；该命令会访问当前配置的 Edge 或 Azure |
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
| Microsoft 启动时报配置错误 | 确认 Driver 为 `edge`/`azure`，对应 voice 非空且 rate 是百分比；Edge 只接受整数，Azure 可使用 SSML 小数。Azure 还需 Key 以及 Region 或 HTTPS Endpoint；修改后重启 |
| Edge 诊断网络超时/连接失败 | 确认部署环境允许出站访问 Edge 在线服务，检查 DNS、代理、防火墙与 TLS；服务不会因此自动切换 Provider |
| Edge 报无效 voice 或上游拒绝 | 核对逐语言 voice 拼写与当前 Edge 可用性；运行诊断查看失败语言。启动阶段不会联网验证 voice |
| Edge 返回空输出或非 MP3 | 诊断会把该语言标记为失败且不写成功文件；记录依赖版本和错误信息，稍后重试或升级前先在验收环境验证 |
| Azure 报认证或地域错误 | 确认 Key、Region、Endpoint 来自同一 Speech 资源；Endpoint 必须是 HTTPS。SDK 取消原因会进入脱敏后的 502 detail |
| Azure 报配额/限流 | 在 Azure 门户检查 Speech 资源定价层、配额和指标；等待或申请配额后重试，系统不会自动切换 Edge |
| 已有 Segment 能播放但诊断/新 Segment 失败 | 缓存命中不会访问 Microsoft 服务；新 Segment 未命中才暴露网络、voice、凭据或上游问题。对照诊断结果与缓存命中情况排查 |
| 未缓存 Microsoft Segment 返回 502 | Edge/Azure 调用失败、拒绝、超时或输出无效；查看脱敏后的响应 detail 与诊断汇总。系统不会回退其他 Provider/Driver |

## 7. Microsoft TTS 生产边界

### 缓存和失败语义

Microsoft Engine Profile 的 synthesis fingerprint 覆盖 Driver、voice、规范化 rate、音频格式和 adapter 版本；Edge 另含 `edge-tts` 版本，Azure 另含 Speech SDK 版本、Region 和 Endpoint。任一字段变化都会进入新的 Cache Identity，自动隔离旧音频。Azure Key 是凭据而非合成设置，不进入 fingerprint；Key 轮换不会主动失效已缓存音频。`ENGINE_PROFILE_CACHE_VERSION_YUE/ZH/EN` 仍保留为人工额外失效开关。

缓存命中直接返回 Audio Artifact，不访问 Edge/Azure；未命中时才联网合成。任一 Microsoft Driver 失败都返回 `502`，不自动回退到另一个 Driver、GPT-SoVITS 或 CosyVoice，避免同一 Contract 混用数据边界、供应方和音色。SDK 取消原因可用于排障，但 Key 会在进入错误 detail 前脱敏。

### 数据外发与服务属性

选择 `microsoft` + `edge` 表示接受：归一化后的合同 Segment 会发送到外部 Edge 在线服务。真实 Segment 可能包含姓名、地址、金额、账号等 PII。当前 Edge Driver 基于第三方 `edge-tts`，没有本项目专属 API key、租户、固定地域、私有网络边界或 Azure 企业 SLA，不能描述为正式 Azure Speech 企业接入。上线前必须由安全、合规与业务负责人评估并接受这一数据处理边界；不能接受时不要为对应 profile 选择 Edge。

选择 `microsoft` + `azure` 表示归一化后的真实 Segment 会发送到 `AZURE_SPEECH_REGION` 或 `AZURE_SPEECH_ENDPOINT` 对应的 Azure Speech 资源。Key、Region/Endpoint 必须来自受组织管理的正式资源；数据位置、网络、配额、计费、服务条款和 SLA 以该 Azure 订阅与资源配置为准。微软的 [Speech Region 文档](https://learn.microsoft.com/azure/ai-services/speech-service/regions) 说明 Region 标识和区域内处理边界，[SpeechConfig API](https://learn.microsoft.com/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.speechconfig) 说明 subscription+region 与 subscription+endpoint 两种 SDK 配置方式。

诊断命令只外发仓库中固定的无敏感测试句，但正式服务会外发真实的归一化 Segment。服务不会在启动或健康检查阶段联网；只有显式运行诊断，或请求一个尚未缓存且选择 Microsoft 的 Segment，才会调用当前 Driver。

### 依赖版本和许可证

`pyproject.toml` 将 `edge-tts` 限制为 `>=7.2.8,<8`，`uv.lock` 当前解析并锁定 `7.2.8`。随部署制品维护第三方许可证清单和许可证副本：`edge-tts 7.2.8` 的包内 LICENSE 声明除 `src/edge_tts/srt_composer.py` 使用 MIT 外，其余文件使用 LGPLv3。每次升级都要重新检查实际安装包的版本与 LICENSE；若升级可能改变音频或协议行为，必须提升 `EDGE_ADAPTER_VERSION`（使 fingerprint 变化）、运行完整自动化测试，并重新执行和试听三语言诊断。

`pyproject.toml` 同时约束官方 `azure-cognitiveservices-speech>=1.50.0,<2`，`uv.lock` 当前锁定 `1.51.1`。部署制品必须保留安装包随附的 `LICENSE.md`、`REDIST.txt` 与 `ThirdPartyNotices.md`，并由发布流程确认 Microsoft Cognitive Services Speech SDK 的使用和再分发条款。升级 SDK 后重新检查这些文件；若版本可能改变音频或协议行为，提升 `AZURE_ADAPTER_VERSION`、运行完整测试并重新执行三语言诊断。

### 从 Edge 切换到正式 Azure Speech

1. 在 Azure 中创建受组织管理的 Speech 资源，确认 Region、网络、配额、计费、数据处理条款和 SLA。
2. 通过部署平台的 secret 注入 `AZURE_SPEECH_KEY`，设置匹配的 `AZURE_SPEECH_REGION`；只有 Azure 门户或云环境要求时才设置 HTTPS `AZURE_SPEECH_ENDPOINT`。
3. 保持 Engine Provider 为 `microsoft`，把 `MICROSOFT_TTS_DRIVER` 从 `edge` 改为 `azure`，重启服务。Template、合同 API 和三语言 voice/rate 配置无需改名。
4. 运行 `uv run python scripts/diagnose_microsoft_tts.py`，确认三种语言均为 `driver=azure`、退出码为 0，并人工试听 `microsoft-azure-*.mp3`。
5. 验证未缓存 Segment 返回 MP3/`audio/mpeg`，Edge 旧缓存不会被 Azure 命中；确认 401/403、Region 不匹配、无效 voice、429/配额和超时均返回脱敏后的 `502` 且没有自动回退。
