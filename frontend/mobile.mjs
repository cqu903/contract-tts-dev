// 移動版「文稿跟讀」頁面（frontend/mobile.html 的模塊）。
// 設計決策來自 2026-08-16 的移動端 UI 原型（3 變體中 B 勝出），原型歸檔於分支 prototype/mobile-ui。
//
// 本文件上半部是可單測的純映射函數（node --test frontend/），底部 document 守衛內是頁面裝配。
import { SegmentAudioBuffer, preferredPlaybackRate } from "./playback.mjs";

/* ============ 純函數：文稿 ↔ 時間 ↔ 段 的映射 ============ */

/** 把原文按行拆成文稿塊：去首尾空白、丟棄空行。 */
export function splitDocBlocks(text) {
  return String(text ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

/**
 * 每塊首字符在全文（以塊拼接、每塊後補一個換行計）中的偏移。
 * 返回 { offsets: number[], total: number }；offsets[i] 是第 i 塊起點，total 是總字符數。
 */
export function blockCharOffsets(blocks) {
  const offsets = [];
  let cursor = 0;
  for (const block of blocks) {
    offsets.push(cursor);
    cursor += block.length + 1; // +1 視作行間隔
  }
  return { offsets, total: Math.max(cursor - 1, 0) };
}

/** 全局播放秒數 → 0..1 進度比例（越界鉗制；無時長時為 0）。 */
export function secondsToRatio(seconds, totalEst) {
  if (!Number.isFinite(totalEst) || totalEst <= 0) return 0;
  const r = seconds / totalEst;
  return Math.max(0, Math.min(1, r));
}

/** 進度比例 → 文稿塊下標（比例落在第 i 塊起點與下一塊起點之間則為 i；末尾鉗到最後一塊）。 */
export function blockIndexAtRatio(offsets, total, ratio) {
  if (offsets.length === 0) return -1;
  if (offsets.length === 1) return 0;
  const pos = Math.max(0, Math.min(1, ratio)) * total;
  for (let i = offsets.length - 1; i >= 0; i--) {
    if (pos >= offsets[i]) return i;
  }
  return 0;
}

/** 全局播放秒數 → 段下標（語義同桌面 demo：落在某段 [start, start+dur) 內即該段；越界為最後一段）。 */
export function segmentAtSeconds(segments, seconds) {
  if (!segments || segments.length === 0) return -1;
  for (const m of segments) {
    if (seconds < m.cumulative_start_s + m.est_dur_s) return m.seg_idx;
  }
  return segments[segments.length - 1].seg_idx;
}

export const SPEED_STEPS = [1.0, 1.1, 1.25];

/** 語速循環 1.0 → 1.1 → 1.25 → 1.0；未知值回到第一步。 */
export function nextSpeed(rate) {
  const i = SPEED_STEPS.indexOf(Number(rate));
  return SPEED_STEPS[(i + 1) % SPEED_STEPS.length] ?? SPEED_STEPS[0];
}

// 取自倉庫內被跟蹤的脫敏樣本 contracts/sample_contract.txt（無 PII）
export const SAMPLE_TEXT = `甲方：張氏有限公司。乙方：李氏貿易行。
第一條　合同標的。甲方同意向乙方採購一批電子元件，型號為XR-7200，數量共12,000件，具體規格詳見附件一。
第二條　價款與支付。合同總價款為港幣3,580,000元，大寫港幣叁佰伍拾捌萬元整。乙方應於簽署後3日內支付訂金港幣716,000元，即總價款的百分之二十；餘款港幣2,864,000元於交付驗收合格後7日內一次結清。逾期付款按年利率5.25%計收利息。
第三條　交付與驗收。甲方須於2026年8月1日前完成交付，最遲不得超過2026年8月15日。乙方應在收到貨物後5個工作日內完成驗收，數量誤差允許在正負3%以內，逾期未提出異議視為合格。
第四條　質量保證。甲方保證貨物符合約定標準，並提供自驗收之日起12個月的免費維修服務，維修響應時間不超過48小時。
第五條　違約責任。任何一方未按約履行義務，每逾期一日，應向守約方支付相當於總價款0.5%的違約金，累計不超過總價款的10%。
第六條　爭議解決。因本合同引起的爭議，雙方應協商解決；協商不成的，提交香港國際仲裁中心仲裁。
第七條　保密義務。雙方對在履行本合同過程中獲悉的對方商業資料負有保密義務，保密期限自合同生效之日起計5年。
第八條　不可抗力。因不可抗力導致無法履行合同義務的一方，應在事件發生後14日內書面通知對方，並提供證明，據此免除或減輕責任。
第九條　合同期限。本合同自2026年8月1日起生效，至2027年7月31日止。期滿前30日，雙方可協商續約。
本合同一式兩份，雙方各執一份，自雙方授權代表簽署之日起生效。簽署日期：2026年7月25日。`;

/* ============ 頁面裝配（僅瀏覽器執行） ============ */

function fmtClock(sec) {
  if (!Number.isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
function fmtDur(sec) {
  if (!Number.isFinite(sec) || sec <= 0) return "0秒";
  const m = Math.round(sec / 60);
  return m >= 1 ? `約${m}分鐘` : `${Math.round(sec)}秒`;
}

function main(doc) {
  const $ = (id) => doc.getElementById(id);
  const tplChipsEl = $("tplChips"), tplHintEl = $("tplHint");
  const textEl = $("text"), loadSampleEl = $("loadSample"), startBtn = $("startBtn");
  const uploadCard = $("uploadCard"), uploadErrEl = $("uploadErr");
  const summaryRow = $("summaryRow"), summaryMeta = $("summaryMeta"), reuploadBtn = $("reuploadBtn");
  const noteLine = $("noteLine"), docEl = $("doc"), tplBadge = $("tplBadge");
  const playBtn = $("playBtn"), trackEl = $("track"), fillEl = doc.querySelector("#track .fill");
  const thumbEl = doc.querySelector("#track .thumb");
  const segLabelEl = $("segLabel"), timeLabelEl = $("timeLabel"), speedBtn = $("speedBtn");
  const statusRow = $("statusRow"), statusText = $("statusText"), retryBtn = $("retryBtn");

  const TEMPLATES = [
    { id: "xcash_yue", name: "粵語", hint: "中文合同，朗讀為粵語；使用粵語切分和文字處理。" },
    { id: "xcash_zh", name: "普通話", hint: "中文合同，朗讀為普通話；使用普通話切分和文字處理。" },
    { id: "xcash_en", name: "English", hint: "英文合同，朗讀為 English；使用英語切分和文字處理。" },
  ];
  const PRELOAD_AHEAD = 3;

  const audio = new Audio();
  audio.preload = "auto";
  audio.preservesPitch = true;
  const buffer = new SegmentAudioBuffer();
  let objectUrl = null;

  let templateId = TEMPLATES[0].id;
  let contractId = null;
  let segs = [];               // [{seg_idx, est_dur_s, cumulative_start_s}]
  let totalEst = 0;
  let current = -1;
  let blocks = [];             // 文稿塊 DOM
  let blockOffsets = [], blockTotal = 1;
  let curBlock = -1;
  let engineError = null;

  /* ---- 模板選擇 ---- */
  for (const t of TEMPLATES) {
    const chip = doc.createElement("button");
    chip.type = "button";
    chip.className = "tpl-chip";
    chip.textContent = t.name;
    chip.setAttribute("aria-pressed", String(t.id === templateId));
    chip.addEventListener("click", () => {
      if (contractId) return; // 已上傳後鎖定模板，避免音/文錯配
      templateId = t.id;
      for (const c of tplChipsEl.children) {
        c.setAttribute("aria-pressed", String(c === chip));
      }
      refreshTemplateHint();
    });
    tplChipsEl.append(chip);
  }
  function refreshTemplateHint() {
    tplHintEl.textContent = TEMPLATES.find((t) => t.id === templateId).hint;
    if (!contractId) applyRate(preferredPlaybackRate(templateId));
  }
  refreshTemplateHint();

  loadSampleEl.addEventListener("click", () => { textEl.value = SAMPLE_TEXT; });

  /* ---- 狀態行 ---- */
  function setStatus(text, { err = false, retry = false } = {}) {
    statusText.textContent = text;
    statusRow.classList.toggle("err", err);
    retryBtn.style.display = retry ? "" : "none";
  }

  /* ---- 上傳 ---- */
  async function upload() {
    const text = textEl.value.trim();
    if (!text) { setStatus("請先貼上合同文字", { err: true }); return; }
    startBtn.disabled = true;
    startBtn.textContent = "切片中…";
    uploadErrEl.style.display = "none";
    setStatus("上傳切片中…");
    try {
      const r = await fetch("/api/contracts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, template_id: templateId }),
      });
      if (!r.ok) {
        let detail = `HTTP ${r.status}`;
        try { detail = (await r.json()).detail || detail; } catch {}
        throw new Error(detail);
      }
      const data = await r.json();
      if (data.template_id && data.template_id !== templateId) {
        throw new Error(`模板不一致：前端=${templateId}，後端=${data.template_id}`);
      }
      contractId = data.contract_id;
      segs = data.segments;
      totalEst = data.total_est_s;
      current = -1;
      engineError = null;
      buffer.clear();
      renderDoc(text);
      collapseUpload(text);
      playBtn.disabled = false;
      speedBtn.disabled = false;
      // 上傳即起播（後端已預熱 seg 0）；被瀏覽器自動播放策略攔截時降級為提示
      playFrom(0).catch(() => {});
    } catch (e) {
      uploadErrEl.textContent = `上傳失敗：${e?.message || e}`;
      uploadErrEl.style.display = "";
      setStatus("上傳失敗，可重試", { err: true });
      startBtn.disabled = false;
      startBtn.textContent = "開始朗讀";
    }
  }
  startBtn.addEventListener("click", upload);

  function collapseUpload(text) {
    uploadCard.style.display = "none";
    summaryRow.style.display = "flex";
    noteLine.style.display = "block";
    const tpl = TEMPLATES.find((t) => t.id === templateId);
    summaryMeta.innerHTML = "";
    summaryMeta.append(`${tpl.name} · 共 ${segs.length} 段 · ${fmtDur(totalEst)}（${text.length} 字）`);
    tplBadge.hidden = false;
    tplBadge.textContent = tpl.name;
  }
  reuploadBtn.addEventListener("click", () => {
    audio.pause();
    summaryRow.style.display = "none";
    noteLine.style.display = "none";
    tplBadge.hidden = true;
    uploadCard.style.display = "";
    startBtn.disabled = false;
    startBtn.textContent = "開始朗讀";
    playBtn.disabled = true;
    speedBtn.disabled = true;
    setStatus("請先上傳合同文稿");
  });

  /* ---- 文稿渲染與跟讀 ---- */
  function renderDoc(text) {
    docEl.replaceChildren();
    blocks = [];
    const lines = splitDocBlocks(text);
    const { offsets, total } = blockCharOffsets(lines);
    blockOffsets = offsets;
    blockTotal = Math.max(total, 1);
    curBlock = -1;
    lines.forEach((line, i) => {
      const p = doc.createElement("p");
      p.className = "block";
      p.textContent = line;
      // 點塊跳讀：塊首字符比例 × 總時長 → 段（近似對齊，同高亮）
      p.addEventListener("click", () => {
        const ratio = blockOffsets[i] / blockTotal;
        const seg = segmentAtSeconds(segs, ratio * totalEst);
        setBlockHighlight(i); // 立即反饋，不等音頻
        playFrom(seg).catch(() => {});
      });
      docEl.append(p);
      blocks.push(p);
    });
  }

  function setBlockHighlight(i) {
    if (i === curBlock) return;
    if (blocks[curBlock]) blocks[curBlock].classList.remove("cur");
    if (blocks[i]) {
      blocks[i].classList.add("cur");
      blocks[i].classList.remove("read");
      // 僅播放中自動跟隨滾動；暫停時不干擾手動滾動
      if (!audio.paused && i > curBlock) {
        blocks[i].scrollIntoView({ behavior: "smooth", block: "center" });
      }
      for (let k = 0; k < i; k++) blocks[k].classList.add("read");
    }
    curBlock = i;
  }

  function followPlayback(seconds) {
    const ratio = secondsToRatio(seconds, totalEst);
    setBlockHighlight(blockIndexAtRatio(blockOffsets, blockTotal, ratio));
    setProgressFill(ratio);
    timeLabelEl.textContent = `${fmtClock(seconds)} / ${fmtClock(totalEst)}`;
  }

  /* ---- 進度條 ---- */
  function setProgressFill(ratio) {
    const pct = `${Math.round(ratio * 1000) / 10}%`;
    fillEl.style.width = pct;
    thumbEl.style.left = pct;
  }
  let dragging = false;
  function trackRatioAt(ev) {
    const rect = trackEl.getBoundingClientRect();
    return Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
  }
  trackEl.addEventListener("pointerdown", (ev) => {
    if (!contractId) return;
    dragging = true;
    trackEl.setPointerCapture(ev.pointerId);
    setProgressFill(trackRatioAt(ev));
  });
  trackEl.addEventListener("pointermove", (ev) => {
    if (dragging) setProgressFill(trackRatioAt(ev));
  });
  trackEl.addEventListener("pointerup", (ev) => {
    if (!dragging) return;
    dragging = false;
    const ratio = trackRatioAt(ev);
    const seg = segmentAtSeconds(segs, ratio * totalEst);
    playFrom(seg).catch(() => {});
  });

  /* ---- 播放 ---- */
  function useAudioBlob(blob) {
    const prev = objectUrl;
    objectUrl = URL.createObjectURL(blob);
    audio.src = objectUrl;
    if (prev) URL.revokeObjectURL(prev);
  }

  function applyRate(rate) {
    audio.playbackRate = rate;
    audio.defaultPlaybackRate = rate;
    speedBtn.textContent = `${rate}×`;
  }
  speedBtn.addEventListener("click", () => applyRate(nextSpeed(audio.playbackRate)));

  function refreshSegLabel() {
    if (current < 0) { segLabelEl.textContent = "未上傳"; return; }
    segLabelEl.innerHTML = "";
    segLabelEl.append(`第 ${current + 1} `);
    const small = doc.createElement("small");
    small.textContent = `/ ${segs.length} 段`;
    segLabelEl.append(small);
  }

  async function playFrom(segIdx) {
    if (segIdx < 0 || segIdx >= segs.length) return;
    current = segIdx;
    engineError = null;
    refreshSegLabel();
    setStatus("緩衝中…");
    playBtn.textContent = "⏸";
    try {
      const blob = await buffer.load(contractId, segIdx);
      if (current !== segIdx) return; // 等待期間已跳別處
      useAudioBlob(blob);
      await audio.play();
      setStatus("播放中");
      for (let k = 1; k <= PRELOAD_AHEAD; k++) {
        if (segIdx + k < segs.length) buffer.preload(contractId, segIdx + k).catch(() => {});
      }
    } catch (e) {
      engineError = String(e?.message || e);
      playBtn.textContent = "▶";
      setStatus(`播放失敗：${engineError}`, { err: true, retry: true });
    }
  }

  playBtn.addEventListener("click", () => {
    if (engineError) {
      playFrom(current >= 0 ? current : 0).catch(() => {});
      return;
    }
    if (contractId && audio.src && !audio.paused) { audio.pause(); return; }
    playFrom(current >= 0 ? current : 0).catch(() => {});
  });
  retryBtn.addEventListener("click", () => {
    playFrom(current >= 0 ? current : 0).catch(() => {});
  });

  audio.addEventListener("ended", () => {
    if (current + 1 < segs.length) {
      playFrom(current + 1).catch(() => {});
    } else {
      playBtn.textContent = "▶";
      setStatus("已結束 · 可點任意段落重聽");
    }
  });
  audio.addEventListener("play", () => { playBtn.textContent = "⏸"; if (!engineError) setStatus("播放中"); });
  audio.addEventListener("pause", () => { playBtn.textContent = "▶"; if (!engineError && !audio.ended) setStatus("已暫停"); });
  audio.addEventListener("timeupdate", () => {
    if (current < 0 || !segs.length) return;
    const global = Math.min(segs[current].cumulative_start_s + audio.currentTime, totalEst);
    if (!dragging) followPlayback(global);
  });
}

if (typeof document !== "undefined") {
  main(document);
}
