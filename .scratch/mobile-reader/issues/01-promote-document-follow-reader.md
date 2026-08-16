# 01 — Promote document-follow reader to real mobile page

**What to build:** 把原型勝出變體 B「文稿跟讀」規範化折入正式前端：`frontend/mobile.html` + `frontend/mobile.mjs`（上傳折疊、連續文稿跟讀高亮 + 自動滾動、底部 mini-player：播放/暫停、可拖進度、語速循環、錯誤行 + 重試；點任意條款按比例跳讀），桌面 demo 首頁加移動版入口。

**Blocked by:** None

**Status:** done

- [x] `frontend/mobile.html` / `mobile.mjs`（複用生產 `playback.mjs`：SegmentAudioBuffer、preferredPlaybackRate）
- [x] 純映射函數導出並單測：`splitDocBlocks` / `blockCharOffsets` / `secondsToRatio` / `blockIndexAtRatio` / `segmentAtSeconds` / `nextSpeed`（`frontend/mobile.test.mjs`，node --test）
- [x] 上傳即起播（後端上傳時預熱 seg 0）；自動連播 + 預載後 3 段；語速初始取 preferredPlaybackRate
- [x] 瀏覽器實測（microsoft/edge 引擎真音頻）：上傳→起播→跟讀高亮→點「第九條」精確跳第 27/30 段·2:35/3:00
- [x] 「進度對齊為時間近似」限制在頁面如實標注（issue 02 落地後移除）

## Comments

來自 throwaway 原型（分支 `prototype/mobile-ui`，3 變體中 B 勝出；決策記錄見 `.scratch/mobile-reader/spec.md`）。按原型技能規範：勝者重寫折入（非直接搬運原型代碼），落選變體與切換器只留歸檔分支。
