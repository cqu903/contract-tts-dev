# Cantonese Contract TTS Service

对外合同朗读服务：调用方 `POST` 一份合同 TXT + `template_id`，拿回内容寻址的 `contract_id`，再按段取音频、自己播放、支持 seek。可选择 GPT-SoVITS（本地）、百炼 CosyVoice（云端）或 Microsoft Provider。

- **设计决策：** `docs/adr/`（ADR-0001..0009）+ `CONTEXT.md`（领域语言）
- **启动与运维：** `docs/running.md`
- **引擎安装（本地 GPT-SoVITS）：** `docs/engine-setup.md`

## 运行

### A. 本地 GPT-SoVITS（默认）
1. 起引擎（独立仓库 / 独立终端，见 `docs/engine-setup.md`）：
   ```
   cd /path/to/GPT-SoVITS && uv run python api_v2.py   # 监听 :9880
   ```
2. 起服务：
   ```
   uv run uvicorn backend.app:app --port 8000
   ```
3. 打开 http://127.0.0.1:8000 → 粘贴合同 TXT →「上傳並切片」→ 拖进度条 seek / 播放

### B. 云端 Bailian CosyVoice（无需本地引擎 / 参考音）
```
DASHSCOPE_API_KEY=sk-... CONTRACT_TTS_ENGINE=bailian uv run uvicorn backend.app:app --port 8000
```

### C. Microsoft Provider / Edge 或 Azure Driver

在 `.env` 中设置：

```
CONTRACT_TTS_ENGINE_YUE=microsoft
MICROSOFT_TTS_DRIVER=edge
MICROSOFT_TTS_VOICE_YUE=zh-HK-WanLungNeural
MICROSOFT_TTS_RATE_YUE=+0%
MICROSOFT_TTS_VOICE_ZH=zh-CN-YunyangNeural
MICROSOFT_TTS_RATE_ZH=+0%
MICROSOFT_TTS_VOICE_EN=en-HK-SamNeural
MICROSOFT_TTS_RATE_EN=+0%
```

将 `CONTRACT_TTS_ENGINE` 设为 `microsoft` 可供三种语言全局使用，也可以只设置 `CONTRACT_TTS_ENGINE_YUE`、`_ZH` 或 `_EN` 与其它 Provider 混合部署。

启用 Edge Driver 会把归一化后的合同 Segment（可能包含 PII）发送到 Edge 在线服务；当前 Driver 没有本项目专属 API key、租户或地域保证。它不自动回退到其他引擎，未缓存段的上游失败返回 `502`。

正式 Azure Speech 使用同一个 `microsoft` Provider，只替换 Driver 并增加 Azure 资源凭据：

```dotenv
MICROSOFT_TTS_DRIVER=azure
AZURE_SPEECH_KEY=replace-with-your-azure-speech-key
AZURE_SPEECH_REGION=eastasia
# AZURE_SPEECH_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
```

Azure Driver 使用官方 Speech SDK，将 Segment 发送到配置的 Azure Speech 资源；Region、Endpoint、voice、rate、音频格式和 SDK/adapter 版本进入缓存指纹，Key 不进入日志或缓存。

修改上述部署配置后需要重启服务。上线前可运行独立三语言诊断（会把仓库内固定、无敏感信息的测试句发送到当前 Microsoft Driver，并保存三份 MP3）：

```powershell
uv run python scripts/diagnose_microsoft_tts.py
```

完整的诊断、数据外发、故障排查、依赖许可证和 Azure 生产切换说明见 `docs/running.md`。

Docker 单实例部署已提供 `Dockerfile` 与 `compose.yaml`，包括非 root 运行、只读根文件系统、持久化 volumes、健康检查和日志轮转。Azure 环境模板及完整构建、诊断、备份、更新说明见 `deploy/azure.env.example` 与 `docs/docker-deployment.md`。

## 对外接口
- `POST /api/contracts`  `{text, template_id}` → `{contract_id, total_est_s, segments}`
- `GET /api/contracts/{id}` · `GET /api/contracts/{id}/segments/{n}`（WAV 为 `audio/wav`，Microsoft MP3 为 `audio/mpeg`）· `POST /api/contracts/{id}/segments/{n}/preload`

当前接受 `template_id=xcash_yue`、`xcash_zh`、`xcash_en`；`xcash` 作为 `xcash_yue` 的兼容别名。Template 会选择独立的切分、归一化、Engine Profile 和缓存身份。详见 `CONTEXT.md` 与 ADR-0001..0009。

## 测试
```
uv run pytest -q
```
