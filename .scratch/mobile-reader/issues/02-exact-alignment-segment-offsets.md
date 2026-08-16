# 02 — Exact follow alignment: expose segment char offsets in the index API

**What to build:** `/api/contracts` 的 index 響應為每段增加 `char_start` / `char_end`（原文 UTF-8 或碼點偏移，任選一種並在回應中注明單位）。只回偏移量、不回文本——調用方手裡已有原文（ADR-0001 不回傳段文本的理由依然成立），前端用偏移量把文稿塊與段精確對齊，替換 `frontend/mobile.mjs` 現有的時間/字符比例近似。

**Blocked by:** None（可獨立做；建議同時給 `_index_response` 加測試）

**Status:** todo

- [ ] `backend/storage/contract.py` `SegmentMeta` 攜帶切分時的原文偏移；`_index_response` 輸出 `char_start`/`char_end`
- [ ] 確認三種模板（yue/zh/en）的 splitter 都能回傳偏移（`backend/text/segmenter.py` / `mandarin_segmenter.py` / 英文路徑）
- [ ] `frontend/mobile.mjs`：偏移可用時走精確對齊；不可用（舊緩存的 index？N/A——index 不緩存）時保持近似兜底
- [ ] 頁面移除「進度對齊為時間近似」標注
- [ ] 更新 `docs/architecture.md` 歸一化表/響應形狀一節

## Comments

原型實測偏差 1-2 段（見 `prototype/mobile-ui` 分支截圖）。注意 char offsets 不構成 PII 增量（無文本內容），但要在 ADR-0001 的語境下補一句說明（或在 0001 加 amendment）。
