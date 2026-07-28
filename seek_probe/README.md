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
2. 參考音頻:`seek_probe/refs/cantonese_ref_trim.wav` + 轉寫 `cantonese_ref_trim.txt`(7s,gitignored)。
3. 後端 + 前端:
   ```
   uv run uvicorn seek_probe.backend.app:app --port 8000 --reload
   ```
4. 打開 http://127.0.0.1:8000/?contract=zacl0603 ,拖動進度條測試(`?contract=` 切換合同)。

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
