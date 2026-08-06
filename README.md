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

### C. Microsoft Provider / Edge Driver（粤语）

在 `.env` 中设置：

```
CONTRACT_TTS_ENGINE_YUE=microsoft
MICROSOFT_TTS_DRIVER=edge
MICROSOFT_TTS_VOICE_YUE=zh-HK-WanLungNeural
MICROSOFT_TTS_RATE_YUE=+0%
```

启用 Edge Driver 会把归一化后的合同 Segment（可能包含 PII）发送到 Edge 在线服务；当前 Driver 没有本项目专属 API key、租户或地域保证。它不自动回退到其他引擎，未缓存段的上游失败返回 `502`。

## 对外接口
- `POST /api/contracts`  `{text, template_id}` → `{contract_id, total_est_s, segments}`
- `GET /api/contracts/{id}` · `GET /api/contracts/{id}/segments/{n}`（WAV 为 `audio/wav`，Edge MP3 为 `audio/mpeg`）· `POST /api/contracts/{id}/segments/{n}/preload`

当前接受 `template_id=xcash_yue`、`xcash_zh`、`xcash_en`；`xcash` 作为 `xcash_yue` 的兼容别名。Template 会选择独立的切分、归一化、Engine Profile 和缓存身份。详见 `CONTEXT.md` 与 ADR-0001..0008。

## 测试
```
uv run pytest -q
```
