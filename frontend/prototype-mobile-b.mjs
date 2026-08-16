// ⚠️ THROWAWAY UI PROTOTYPE — 變體 B「文稿跟讀」：邊看邊聽的連續文稿閱讀器。
// 驗證的產品問題：API 刻意不回傳分段文本（PII），文稿高亮只能按時間比例近似，
// 真實段號須單獨外顯 —— 原型如實暴露「近似對齊」這個體驗缺口。
export const key = "B";
export const label = "文稿跟讀";

const LANG_SHORT = { xcash_yue: "粵語", xcash_zh: "普通話", xcash_en: "English" };
const RATES = [1.0, 1.1, 1.25];
// 瀏覽器攔截非手勢 autoplay 時的錯誤不算真故障，只需引導用戶點播放鍵
const GESTURE_ERR = /notallowed|gesture|interrupted|denied/i;

const ICON_PLAY =
  '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M8.4 5.2v13.6L19 12z" fill="currentColor"/></svg>';
const ICON_PAUSE =
  '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M7.4 5.4h3.2v13.2H7.4zM13.4 5.4h3.2v13.2h-3.2z" fill="currentColor"/></svg>';
const ICON_DOC =
  '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M7 3.5h6.5L18 8v12.5H7z"/><path d="M13.5 3.5V8H18"/><path d="M9.8 12.5h6M9.8 16h6"/></svg>';

const CSS = `
.vB-app{position:absolute;inset:0;display:flex;flex-direction:column;background:#f8f5ee;color:#2a2822;font-family:-apple-system,BlinkMacSystemFont,"PingFang HK","PingFang SC","Noto Sans HK",sans-serif;overflow:hidden;-webkit-tap-highlight-color:transparent}
.vB-app button{font-family:inherit;cursor:pointer;-webkit-appearance:none;appearance:none;touch-action:manipulation;padding:0}
/* ---- 頂部上傳區（可折疊）---- */
.vB-head{flex:none;background:#fff;border-bottom:1px solid #e9e3d4;padding:14px 16px}
.vB-title{font-size:18px;font-weight:700;color:#22201a;display:flex;align-items:baseline;justify-content:space-between}
.vB-title small{font-size:11px;font-weight:500;color:#a29a85;letter-spacing:.06em}
.vB-lab{font-size:12px;color:#8d8776;margin:13px 0 7px}
.vB-chips{display:flex;gap:8px}
.vB-chip{flex:1;min-height:44px;border-radius:12px;border:1.5px solid #ded8c8;background:#fffdf8;font-size:13.5px;color:#5c5748}
.vB-chip.on{border-color:#0e7f6f;background:#e4f3f0;color:#0a5f53;font-weight:700}
.vB-hint{font-size:11.5px;color:#a29a85;margin-top:7px;line-height:1.5;min-height:1.6em}
.vB-ta{display:block;width:100%;min-height:104px;margin-top:10px;padding:10px 12px;border:1.5px solid #ded8c8;border-radius:12px;background:#fffdf8;font-family:inherit;font-size:13.5px;line-height:1.6;color:#2a2822;resize:vertical}
.vB-ta:focus{outline:none;border-color:#0e7f6f}
.vB-row{display:flex;gap:10px;margin-top:10px}
.vB-btn2{min-width:96px;min-height:48px;border-radius:12px;border:1.5px solid #ded8c8;background:#fff;font-size:14.5px;color:#5c5748;font-weight:600}
.vB-go{flex:1;min-height:48px;border:none;border-radius:12px;background:#0e7f6f;color:#fff;font-size:16px;font-weight:700;letter-spacing:.05em;box-shadow:0 2px 10px rgba(14,127,111,.3)}
.vB-go:disabled{background:#b9b4a4;box-shadow:none}
.vB-err{margin-top:9px;font-size:12.5px;color:#b3261e;line-height:1.5}
/* ---- 折疊後的一行摘要 ---- */
.vB-sum{flex:none;display:flex;align-items:center;gap:10px;background:#fff;border-bottom:1px solid #e9e3d4;padding:9px 16px;cursor:pointer}
.vB-sumIco{flex:none;width:34px;height:34px;border-radius:9px;background:#e4f3f0;color:#0a5f53;display:flex;align-items:center;justify-content:center}
.vB-sumTxt{flex:1;min-width:0}
.vB-sumMain{font-size:14.5px;font-weight:700;color:#22201a}
.vB-sumSub{font-size:11.5px;color:#a29a85;margin-top:2px}
.vB-reup{flex:none;min-height:44px;padding:0 14px;border-radius:10px;border:1.5px solid #ded8c8;background:#fff;font-size:13px;color:#5c5748;font-weight:600}
/* ---- 近似說明條（文稿區頂部）---- */
.vB-note{flex:none;display:flex;align-items:center;gap:6px;padding:7px 16px;font-size:11px;color:#8d8168;background:#f1ecdd;border-bottom:1px solid #e6dfc9}
/* ---- 連續文稿正文 ---- */
.vB-doc{flex:1;min-height:0;display:flex;flex-direction:column;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:18px 18px calc(160px + env(safe-area-inset-bottom));scrollbar-width:thin}
.vB-block{position:relative;margin:0 0 22px;padding:5px 10px 5px 20px;border-radius:9px;font-family:"Songti TC","Noto Serif TC","Source Han Serif TC",Georgia,serif;font-size:17px;line-height:1.8;text-align:justify;color:#38352d;cursor:pointer;touch-action:manipulation;transition:background-color .4s}
.vB-block:last-child{margin-bottom:0}
.vB-block::before{content:"";position:absolute;left:5px;top:2px;bottom:2px;width:3.5px;border-radius:2px;background:transparent;transition:background-color .4s}
.vB-block.done::before{background:rgba(14,127,111,.28)}
.vB-block.on{background:rgba(230,180,44,.22)}
.vB-block.on::before{background:#0e7f6f}
.vB-empty{margin:auto;text-align:center;color:#b0a78f;padding:0 34px}
.vB-eicon{display:flex;justify-content:center;color:#cdc5ab;margin-bottom:12px}
.vB-eicon svg{width:42px;height:42px}
.vB-eT{font-size:15.5px;font-weight:700;color:#8b8470}
.vB-eS{font-size:12.5px;line-height:1.8;color:#b0a78f;margin-top:8px}
/* ---- 底部 sticky mini-player（absolute，不逃出手机外框）---- */
.vB-player{position:absolute;left:0;right:0;bottom:0;z-index:6;background:rgba(255,255,255,.97);backdrop-filter:blur(8px);border-top:1px solid #e2dbc8;box-shadow:0 -10px 26px rgba(76,64,28,.10);padding:0 14px calc(8px + env(safe-area-inset-bottom))}
.vB-player.off .vB-trackWrap{pointer-events:none}
.vB-player.off .vB-track{background:#eee9da}
.vB-player.off .vB-fill,.vB-player.off .vB-dot{display:none}
.vB-player.off .vB-play,.vB-player.off .vB-rate{opacity:.45}
.vB-trackWrap{height:44px;display:flex;align-items:center;touch-action:none;cursor:pointer}
.vB-track{position:relative;width:100%;height:4px;border-radius:2px;background:#e4dec9}
.vB-fill{position:absolute;left:0;top:0;bottom:0;width:0%;border-radius:2px;background:linear-gradient(90deg,#0e7f6f,#14a08d)}
.vB-dot{position:absolute;top:50%;left:0%;width:15px;height:15px;border-radius:50%;background:#0e7f6f;border:2.5px solid #fff;box-shadow:0 1px 5px rgba(30,60,50,.35);transform:translate(-50%,-50%)}
.vB-prow{display:flex;align-items:center;gap:12px}
.vB-play{flex:none;width:48px;height:48px;border:none;border-radius:50%;background:#0e7f6f;color:#fff;display:flex;align-items:center;justify-content:center;box-shadow:0 3px 10px rgba(14,127,111,.35)}
.vB-play:active{transform:scale(.96)}
.vB-info{flex:1;min-width:0}
.vB-seg{font-size:13.5px;font-weight:700;color:#0a5f53;white-space:nowrap}
.vB-approx{font-size:10.5px;font-weight:500;color:#a29a85;margin-left:5px}
.vB-sub{display:flex;align-items:center;gap:8px;font-size:12px;color:#78725f;margin-top:3px}
.vB-sub.err{color:#b3261e}
.vB-eline{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vB-retry{flex:none;min-height:44px;padding:0 14px;border-radius:10px;border:1px solid #d8574a;background:#fdf1f0;color:#b3261e;font-size:12.5px;font-weight:700}
.vB-rate{flex:none;min-width:56px;height:44px;border-radius:10px;border:1.5px solid #ded8c8;background:#fff;font-size:13.5px;font-weight:700;color:#0a5f53}
`;

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}
const tnode = (s) => document.createTextNode(s);
const fmtRate = (r) => `${parseFloat(Number(r).toFixed(2))}×`;

export function mount(root, ctx) {
  const styleEl = document.createElement("style");
  styleEl.textContent = CSS;
  document.head.append(styleEl);

  const p = ctx.createPlayer();
  const offs = [];
  let templateId = ctx.templates[0].id;
  let blockMeta = [];   // [{text, start}] —— start 為塊首字符在全文的字符偏移
  let blockEls = [];
  let totalChars = 1;
  let activeIdx = -1;
  let ended = false;
  let everPlayed = false;
  let dragging = false;
  let dragFrac = 0;

  /* ---------------- DOM 骨架 ---------------- */

  const app = el("div", "vB-app");

  // 上傳區（展開態）
  const headOpen = el("div", "vB-head");
  const title = el("div", "vB-title");
  title.append(el("span", null, "合同朗讀"), el("small", null, "文稿跟讀 · 邊看邊聽"));
  headOpen.append(title);

  headOpen.append(el("div", "vB-lab", "朗讀語音"));
  const chips = el("div", "vB-chips");
  const chipEls = new Map();
  for (const t of ctx.templates) {
    const c = el("button", "vB-chip", LANG_SHORT[t.id] ?? t.name);
    c.type = "button";
    c.title = t.name;
    c.addEventListener("click", () => {
      templateId = t.id;
      for (const [id, node] of chipEls) node.classList.toggle("on", id === t.id);
      hintEl.textContent = t.hint;
    });
    chipEls.set(t.id, c);
    chips.append(c);
  }
  chipEls.get(templateId).classList.add("on");
  const hintEl = el("div", "vB-hint", ctx.templates[0].hint);
  headOpen.append(chips, hintEl);

  const ta = el("textarea", "vB-ta");
  ta.placeholder = "貼上合同全文（建議每條條款一行）…";
  ta.spellcheck = false;
  const row = el("div", "vB-row");
  const sampleBtn = el("button", "vB-btn2", "載入示例");
  sampleBtn.type = "button";
  const goBtn = el("button", "vB-go", "開始朗讀");
  goBtn.type = "button";
  row.append(sampleBtn, goBtn);
  const upErr = el("div", "vB-err");
  upErr.style.display = "none";
  headOpen.append(ta, row, upErr);

  // 上傳區（折疊態）：一行摘要 + 重新上傳
  const headSum = el("div", "vB-sum");
  headSum.style.display = "none";
  const sumIco = el("div", "vB-sumIco");
  sumIco.innerHTML = ICON_DOC;
  const sumMain = el("div", "vB-sumMain");
  const sumSub = el("div", "vB-sumSub");
  const reupBtn = el("button", "vB-reup", "重新上傳");
  reupBtn.type = "button";
  const sumWrap = el("div", "vB-sumTxt");
  sumWrap.append(sumMain, sumSub);
  headSum.append(sumIco, sumWrap, reupBtn);

  // 近似說明條（文稿區頂部，常駐可見）
  const note = el("div", "vB-note");
  note.append(tnode("※ 進度對齊為時間近似（API 不回傳分段文本）；底部段號為實際值。"));
  note.style.display = "none";

  // 連續文稿正文（頁面主體，可滾動）
  const doc = el("div", "vB-doc");
  const emptyEl = el("div", "vB-empty");
  const emptyIco = el("div", "vB-eicon");
  emptyIco.innerHTML = ICON_DOC;
  emptyEl.append(emptyIco, el("div", "vB-eT", "貼上合同，一邊讀一邊聽"));
  emptyEl.append(el("div", "vB-eS", "於上方貼上合同全文（或點「載入示例」），開始朗讀後文稿會隨進度高亮跟讀；點任意段落可直接跳讀。"));
  doc.append(emptyEl);

  // 底部 mini-player
  const player = el("div", "vB-player off");
  const trackWrap = el("div", "vB-trackWrap");
  const track = el("div", "vB-track");
  const fill = el("div", "vB-fill");
  const dot = el("div", "vB-dot");
  track.append(fill, dot);
  trackWrap.append(track);
  const prow = el("div", "vB-prow");
  const playBtn = el("button", "vB-play");
  playBtn.type = "button";
  playBtn.innerHTML = ICON_PLAY;
  playBtn.disabled = true;
  playBtn.setAttribute("aria-label", "播放 / 暫停");
  const info = el("div", "vB-info");
  const segLine = el("div", "vB-seg");
  const segTxt = el("span", null, "未上傳");
  const segTag = el("span", "vB-approx", "實際段");
  segLine.append(segTxt, segTag);
  const subLine = el("div", "vB-sub");
  info.append(segLine, subLine);
  const rateBtn = el("button", "vB-rate", "1×");
  rateBtn.type = "button";
  rateBtn.disabled = true;
  rateBtn.setAttribute("aria-label", "語速");
  prow.append(playBtn, info, rateBtn);
  player.append(trackWrap, prow);

  app.append(headOpen, headSum, note, doc, player);
  root.append(app);

  /* ---------------- 狀態渲染 ---------------- */

  function setSub(nodes, isErr) {
    subLine.classList.toggle("err", !!isErr);
    subLine.replaceChildren(...nodes);
  }

  function makeRetry() {
    const b = el("button", "vB-retry", "重試");
    b.type = "button";
    b.addEventListener("click", () => p.playFrom(p.current >= 0 ? p.current : 0));
    return b;
  }

  function refresh() {
    // 每次事件後重讀 p 的 getter，不解構快照
    const segCount = p.segments.length;
    const loaded = segCount > 0;
    player.classList.toggle("off", !loaded);
    playBtn.disabled = !loaded;
    rateBtn.disabled = !loaded;
    playBtn.innerHTML = p.playing ? ICON_PAUSE : ICON_PLAY;
    segTxt.textContent = !loaded
      ? "未上傳"
      : p.current >= 0 ? `第 ${p.current + 1} / ${segCount} 段` : "尚未開始";
    segTag.style.display = loaded ? "" : "none";
    rateBtn.textContent = fmtRate(p.rate);

    const t = dragging ? dragFrac * p.totalEst : p.currentTime();
    const frac = loaded && p.totalEst > 0 ? Math.min(1, Math.max(0, t / p.totalEst)) : 0;
    const barFrac = dragging ? dragFrac : frac;
    fill.style.width = `${barFrac * 100}%`;
    dot.style.left = `${barFrac * 100}%`;
    const clock = `${ctx.fmtClock(t)} / ${ctx.fmtClock(p.totalEst)}`;

    if (!loaded) { setSub([tnode("請先上傳合同文稿")]); return; }
    if (p.error) {
      if (!everPlayed && GESTURE_ERR.test(p.error)) {
        setSub([tnode(`${clock} · 點 ▶ 開始`)]);
        return;
      }
      setSub([el("span", "vB-eline", `⚠ ${p.error}`), makeRetry()], true);
      return;
    }
    if (p.buffering) { setSub([tnode(`${clock} · 緩衝中…`)]); return; }
    if (ended) { setSub([tnode(`朗讀完畢 · 全長${ctx.fmtDur(p.totalEst)} · 點 ▶ 重聽`)]); return; }
    if (p.playing) { setSub([tnode(clock)]); return; }
    if (p.current >= 0) { setSub([tnode(`${clock} · 已暫停`)]); return; }
    setSub([tnode(`${clock} · 已就緒，點 ▶ 開始`)]);
  }

  /* ---------------- 跟讀對齊：時間比例 → 字符比例 → 塊 ---------------- */

  function idxAtFrac(frac) {
    const pos = Math.max(0, Math.min(0.999, frac)) * totalChars;
    let i = blockMeta.length - 1;
    for (let k = 0; k < blockMeta.length; k++) {
      if (pos < blockMeta[k].start + blockMeta[k].text.length) { i = k; break; }
    }
    return i;
  }

  function setActive(i, follow) {
    if (i < 0 || i === activeIdx) return;
    activeIdx = i;
    for (let k = 0; k < blockEls.length; k++) {
      blockEls[k].classList.toggle("on", k === i);
      blockEls[k].classList.toggle("done", k < i);
    }
    // 節流：僅在活躍塊變化時滾動；播放/緩衝中才跟隨，暫停時不打擾手動滾動
    if (follow) blockEls[i].scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function renderDoc(text) {
    blockMeta = [];
    blockEls = [];
    totalChars = 0;
    const frag = document.createDocumentFragment();
    const lines = text ? text.split(/\n+/).map((s) => s.trim()).filter(Boolean) : [];
    for (const ln of lines) {
      blockMeta.push({ text: ln, start: totalChars });
      totalChars += ln.length;
      frag.append(el("p", "vB-block", ln));
    }
    blockEls = [...frag.children];
    activeIdx = -1;
    if (blockEls.length) {
      doc.replaceChildren(frag);
      note.style.display = "flex";
    } else {
      doc.replaceChildren(emptyEl);
      note.style.display = "none";
    }
    doc.scrollTop = 0;
  }

  /* ---------------- 折疊 / 展開 ---------------- */

  function collapseHeader() {
    const tpl = ctx.templates.find((t) => t.id === templateId);
    sumMain.textContent =
      `${LANG_SHORT[templateId] ?? templateId} · 共 ${p.segments.length} 段 · ${ctx.fmtDur(p.totalEst)}`;
    sumSub.textContent = tpl ? tpl.name : "";
    headOpen.style.display = "none";
    headSum.style.display = "flex";
  }
  function expandHeader() {
    headSum.style.display = "none";
    headOpen.style.display = "";
  }

  /* ---------------- 交互 ---------------- */

  function showUpErr(msg) { upErr.textContent = msg; upErr.style.display = ""; }
  function hideUpErr() { upErr.textContent = ""; upErr.style.display = "none"; }

  sampleBtn.addEventListener("click", () => {
    ta.value = ctx.sampleText;
    ta.focus();
  });

  goBtn.addEventListener("click", async () => {
    const text = ta.value.trim();
    if (!text) { showUpErr("請先貼上合同文字，或點「載入示例」。"); return; }
    hideUpErr();
    goBtn.disabled = true;
    goBtn.textContent = "上傳切片中…";
    if (p.playing) p.toggle(); // 換約前先停舊音，避免疊音
    try {
      await p.load(text, templateId);
      ended = false;
      everPlayed = false;
      renderDoc(text);
      collapseHeader();
      refresh();
      p.playFrom(0); // 嘗試自動起播；被瀏覽器攔截時僅顯示「點 ▶ 開始」
    } catch (e) {
      showUpErr(`上傳失敗：${e?.message || e}（可重試）`);
      expandHeader();
    } finally {
      goBtn.disabled = false;
      goBtn.textContent = "開始朗讀";
    }
  });

  headSum.addEventListener("click", expandHeader);
  reupBtn.addEventListener("click", expandHeader);

  playBtn.addEventListener("click", () => {
    if (!p.segments.length) return;
    if (ended) {
      ended = false;
      setActive(0, false);
      p.playFrom(0);
    } else {
      p.toggle();
    }
    refresh();
  });

  rateBtn.addEventListener("click", () => {
    if (!p.segments.length) return;
    const cur = RATES.indexOf(Math.round(p.rate * 100) / 100);
    p.setRate(RATES[(cur + 1) % RATES.length] ?? 1.0);
    refresh();
  });

  function fracFromEvent(e) {
    const r = track.getBoundingClientRect();
    if (!r.width) return 0;
    return Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
  }
  trackWrap.addEventListener("pointerdown", (e) => {
    if (!p.segments.length) return;
    dragging = true;
    dragFrac = fracFromEvent(e);
    trackWrap.setPointerCapture(e.pointerId);
    refresh();
  });
  trackWrap.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    dragFrac = fracFromEvent(e);
    refresh();
  });
  trackWrap.addEventListener("pointerup", (e) => {
    if (!dragging) return;
    dragging = false;
    dragFrac = fracFromEvent(e);
    setActive(idxAtFrac(dragFrac), false);
    p.seekToSeconds(dragFrac * p.totalEst); // 松手才 seek
    refresh();
  });
  trackWrap.addEventListener("pointercancel", () => {
    if (!dragging) return;
    dragging = false;
    refresh();
  });

  // 點任意塊：塊首字符比例 × totalEst → seek
  doc.addEventListener("click", (e) => {
    const t = e.target instanceof Element ? e.target.closest(".vB-block") : null;
    if (!t || !p.segments.length || totalChars <= 0) return;
    const i = blockEls.indexOf(t);
    if (i < 0) return;
    setActive(i, false);
    p.seekToSeconds((blockMeta[i].start / totalChars) * p.totalEst);
  });

  /* ---------------- 訂閱播放事件 ---------------- */

  offs.push(
    p.on("ready", refresh),
    p.on("segment", refresh),
    p.on("state", () => {
      if (p.playing) { everPlayed = true; ended = false; }
      refresh();
    }),
    p.on("timeupdate", () => {
      if (blockMeta.length && p.totalEst > 0) {
        setActive(idxAtFrac(p.currentTime() / p.totalEst), p.playing || p.buffering);
      }
      refresh();
    }),
    p.on("ended", () => { ended = true; refresh(); }),
  );

  refresh();

  return function dispose() {
    for (const off of offs) { try { off(); } catch {} }
    offs.length = 0;
    p.dispose();
    styleEl.remove();
  };
}
