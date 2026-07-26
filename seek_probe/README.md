# 粵語合同朗讀 + 可拖動進度條(穿刺)

可行性穿刺:GPT-SoVITS(粵語)+ 分段 / 內容尋址緩存 / 文本歸一化 / seek 映射 + 網頁播放器。

- **架構說明(as-built,代碼為準):** `seek_probe/docs/architecture.md`
- 設計 spec:`docs/superpowers/specs/2026-07-25-cantonese-tts-seek-probe-design.md`
- 引擎安裝:`seek_probe/docs/engine-setup.md`

## 運行

1. 引擎(獨立終端;見 `docs/engine-setup.md` 安裝步驟):
   ```
   cd /Users/roy/codes/GPT-SoVITS && uv run python api_v2.py   # 監聽 :9880
   ```
2. 參考音頻:放 `seek_probe/refs/cantonese_ref.wav`,其粵語轉寫放 `seek_probe/refs/cantonese_ref.txt`。
3. 後端 + 前端:
   ```
   uv run uvicorn seek_probe.backend.app:app --port 8000
   ```
4. 打開 http://127.0.0.1:8000/ ,拖動進度條測試。

## 測試
```
uv run pytest -q
```

## 結果(待引擎就緒後填入實測)
- 分段數 / 預估時長:22 段 / ~1.95 min
- 冷 seek 首字節延遲:_待測_
- 命中緩存耗時:_待測_
- 跨段音色一致性(耳聽):_待測_

## 已知後續(未做,見 spec §2/§10)
- `streaming_mode=true` 降冷 seek 延遲(段格式隨版本變,未押注)。
- 真實時長回填精修進度條。
- 段內精確子 seek(目前吸附段邊界)。
- 粵語母語者地道性 go/no-go(單獨關卡)。
