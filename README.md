# Cantonese Contract TTS Service

对外粤语合同朗读服务：调用方 `POST` 一份合同 TXT + `template_id`，拿回内容寻址的 `contract_id`，再按段取音频、自己播放、支持 seek。基于 GPT-SoVITS（本地）或百炼 CosyVoice（云端）。

- **设计决策：** `docs/adr/`（ADR-0001..0007）+ `CONTEXT.md`（领域语言）
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
DASHSCOPE_API_KEY=sk-... SEEK_PROBE_ENGINE=bailian uv run uvicorn backend.app:app --port 8000
```

## 对外接口
- `POST /api/contracts`  `{text, template_id}` → `{contract_id, total_est_s, segments}`
- `GET /api/contracts/{id}` · `GET /api/contracts/{id}/segments/{n}`（audio/wav）· `POST /api/contracts/{id}/segments/{n}/preload`

v1 仅接受 `template_id=xcash`；音色 / 引擎 / 语言由服务端固定。详见 ADR-0001..0007。

## 测试
```
uv run pytest -q
```
