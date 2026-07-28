# 粵語合同朗讀 + 可拖動進度條(穿刺)

可行性穿刺:GPT-SoVITS(粵語)+ 分段 / 內容尋址緩存 / 文本歸一化 / seek 映射 + 網頁播放器。

- **架構說明(as-built,代碼為準):** `seek_probe/docs/architecture.md`
- 設計 spec:`docs/superpowers/specs/2026-07-25-cantonese-tts-seek-probe-design.md`
- 引擎安裝:`seek_probe/docs/engine-setup.md`

## 運行

### A. 本地 GPT-SoVITS 引擎(默認)

1. 引擎(獨立終端;見 `docs/engine-setup.md` 安裝步驟):
   ```
   cd /Users/roy/codes/GPT-SoVITS && uv run python api_v2.py   # 監聽 :9880
   ```
2. 參考音頻:`seek_probe/refs/cantonese_ref_trim.wav` + 轉寫 `cantonese_ref_trim.txt`(7s,gitignored)。
3. 後端 + 前端:
   ```
   uv run uvicorn seek_probe.backend.app:app --port 8000 --reload
   ```

### B. 雲端 Bailian CosyVoice 引擎(無需本地引擎 / 參考音)

用 `SEEK_PROBE_ENGINE=bailian` 切換;音色 `BAILIAN_VOICE`(默認 `longjiaxin_v3` 原生粵語女,亦可 `longjiayi_v3` / `longanyue_v3` 粵語男)。需先設 `DASHSCOPE_API_KEY`。
   ```
   SEEK_PROBE_ENGINE=bailian uv run uvicorn seek_probe.backend.app:app --port 8000
   ```
> 引擎可熱切:兩個 client 的 `synth(text)->AsyncIterator[bytes]` 同構,歸一化 / seek / 緩存全部共用。**注意緩存鍵不含引擎名**——本地↔雲端切換前先 `rm -f seek_probe/cache/*.wav`,否則會命中舊引擎的音頻。
> **TN 邊界**:雲端 cosyvoice 自動 TN 只覆蓋日期 / 基礎金額;逐位(電話 / 身份證 / 型號)、`HK$→港幣`、羅馬序號仍靠 `normalizer.py`——雲端路徑**不能省歸一化層**。

### 打開

http://127.0.0.1:8000 —— 默認合同 `zacl0603`(真實 Zero Finance 貸款協議,659 段 ≈85 min);`?contract=sample` 切樣例,`?contract=` 切其它已註冊合同。拖動進度條測試。

## 添加新合同 / 工具速查

換合同模板時:PDF→txt 轉換 + 閱讀順序審計 + 註冊。完整步驟見 **`docs/architecture.md` §8**,工具:
- `scripts/convert_contract_pdf.py` — PDF→txt(剝頁眉頁腳 + 行級排序)
- `scripts/audit_reading_order.py` — 標出閱讀順序不一致的頁,只復核這些

## 測試
```
uv run pytest -q
```

## 結果(zacl0603 實測)
- 分段數 / 預估時長:652 段 / ~85 min
- 冷 seek 首字節延遲:短段 ~1–4s(M3 Max CPU,RTF≈0.4;靠預載 + 緩存掩蓋)
- 跨段音色一致性:全部段共用同一參考音 → 一致
- 英文地址/公司名:`yue` + L2 清洗後讀成詞;金額/身份證/日期:粵語中文

## 已知後續(未做,見 spec §2/§10)
- `streaming_mode=true` 降冷 seek 延遲(段格式隨版本變,未押注)。
- 真實時長回填精修進度條。
- 段內精確子 seek(目前吸附段邊界)。
- 粵語母語者地道性 go/no-go(單獨關卡)。
