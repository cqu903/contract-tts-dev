// ⚠️ THROWAWAY UI PROTOTYPE — 變體 C「語音氣泡流」：三步向導（選模板 → 貼合約 → 生成）→
// 每段一條微信式語音氣泡（氣泡長度∝時長、點擊即播該段、連播自動跟隨滾動）。用完即棄。
export const key = "C";
export const label = "語音氣泡流";

const BADGE = { xcash_yue: "粵", xcash_zh: "普", xcash_en: "EN" };

export function mount(root, ctx) {
  /* ---------------- 樣式（唯一 <style>，選擇器全部 .vC- 前綴） ---------------- */
  const style = document.createElement("style");
  style.textContent = `
.vC-app{position:absolute;inset:0;display:flex;flex-direction:column;background:#ededed;color:#191919;font-size:15px;overflow:hidden;}
.vC-app *{box-sizing:border-box;}
.vC-hide{display:none !important;}

/* ---- 三步向導 ---- */
.vC-wizard{flex:1;display:flex;flex-direction:column;background:#fff;min-height:0;}
.vC-steps{display:flex;align-items:center;gap:4px;padding:10px 14px;border-bottom:1px solid #f0f0f0;flex:none;}
.vC-step{appearance:none;border:0;background:none;display:flex;align-items:center;gap:7px;padding:8px 6px;min-height:44px;font:inherit;font-size:13px;color:#9a9a9a;cursor:pointer;border-radius:8px;}
.vC-step b{width:26px;height:26px;border-radius:50%;background:#e8e8e8;color:#8a8a8a;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;flex:none;}
.vC-step.vC-on{color:#0e8f4c;font-weight:600;}
.vC-step.vC-on b,.vC-step.vC-done b{background:#07c160;color:#fff;}
.vC-step.vC-done{color:#0e8f4c;}
.vC-line{flex:1;height:2px;background:#e5e5e5;margin:0 3px;}
.vC-line.vC-done{background:#07c160;}
.vC-pane{flex:1;display:none;flex-direction:column;min-height:0;padding:16px;overflow:auto;}
.vC-pane.vC-show{display:flex;}
.vC-pane-title{font-size:17px;font-weight:700;margin-bottom:14px;flex:none;}

/* 步驟 ① 模板行 */
.vC-tpl{appearance:none;width:100%;text-align:left;background:#fff;border:1.5px solid #e8e8e8;border-radius:12px;padding:12px 14px;display:flex;align-items:center;gap:12px;min-height:68px;margin-bottom:12px;font:inherit;cursor:pointer;flex:none;}
.vC-tpl.vC-sel{border-color:#07c160;background:#f4fdf7;}
.vC-tpl-name{font-size:16px;font-weight:600;}
.vC-tpl-hint{font-size:12px;color:#8a8a8a;margin-top:3px;line-height:1.5;}
.vC-tpl-check{margin-left:auto;width:24px;height:24px;border-radius:50%;border:1.5px solid #d9d9d9;flex:none;display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;}
.vC-tpl.vC-sel .vC-tpl-check{background:#07c160;border-color:#07c160;}

/* 步驟 ② 合約文字 */
.vC-ta{flex:1;min-height:200px;width:100%;border:1.5px solid #e8e8e8;border-radius:12px;padding:12px;font:inherit;font-size:14px;line-height:1.7;resize:none;background:#fafafa;}
.vC-ta:focus{outline:none;border-color:#07c160;background:#fff;}
.vC-ta-meta{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:10px 0 14px;font-size:12px;color:#8a8a8a;flex:none;}
.vC-btn-ghost{appearance:none;min-height:44px;padding:0 16px;border:1.5px solid #07c160;background:#fff;color:#07c160;border-radius:10px;font:inherit;font-size:14px;font-weight:600;cursor:pointer;flex:none;}
.vC-btn-main{appearance:none;min-height:50px;border:0;background:#07c160;color:#fff;border-radius:12px;font:inherit;font-size:16px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;}
.vC-btn-main:disabled{opacity:.45;cursor:default;}
.vC-next{margin-top:auto;flex:none;}

/* 步驟 ③ 摘要 + 生成 */
.vC-sum{border:1px solid #eee;border-radius:12px;overflow:hidden;flex:none;}
.vC-sum-row{display:flex;justify-content:space-between;align-items:center;padding:13px 14px;font-size:14px;background:#fff;}
.vC-sum-row + .vC-sum-row{border-top:1px solid #f2f2f2;}
.vC-sum-row span{color:#8a8a8a;}
.vC-sum-row b{font-weight:600;text-align:right;}
.vC-gen{margin-top:16px;width:100%;flex:none;}
.vC-gen-err{margin-top:12px;}

/* ---- 過渡成功屏 ---- */
.vC-done{position:absolute;inset:0;display:none;flex-direction:column;align-items:center;justify-content:center;gap:12px;background:#fff;z-index:5;}
.vC-done.vC-show{display:flex;}
.vC-done b{width:66px;height:66px;border-radius:50%;background:#07c160;color:#fff;font-size:32px;display:flex;align-items:center;justify-content:center;}
.vC-done-t{font-size:18px;font-weight:700;}
.vC-done-s{font-size:13px;color:#8a8a8a;}

/* ---- 氣泡流主界面 ---- */
.vC-main{flex:1;display:none;flex-direction:column;min-height:0;}
.vC-main.vC-show{display:flex;}
.vC-head{flex:none;background:#fff;border-bottom:1px solid #ececec;padding:10px 14px 12px;}
.vC-head-row{display:flex;align-items:center;justify-content:space-between;gap:10px;}
.vC-stat{font-size:13px;color:#5a5a5a;line-height:1.5;}
.vC-stat b{color:#191919;}
.vC-btn-re{appearance:none;min-height:44px;padding:0 13px;background:#fff;border:1.5px solid #d9d9d9;border-radius:9px;font:inherit;font-size:13px;color:#5a5a5a;cursor:pointer;flex:none;}
.vC-go{margin-top:10px;width:100%;min-height:48px;}
.vC-err{display:none;margin-top:10px;background:#fdeceb;border:1px solid #f5c6c0;border-radius:10px;padding:6px 8px 6px 12px;font-size:12.5px;color:#c0392b;align-items:center;gap:10px;line-height:1.45;}
.vC-err.vC-show{display:flex;}
.vC-err button{appearance:none;min-height:44px;margin-left:auto;padding:0 14px;background:#fff;border:1px solid #eab3ac;border-radius:8px;color:#c0392b;font:inherit;font-size:13px;font-weight:600;cursor:pointer;flex:none;}

/* 氣泡列表 */
.vC-list{flex:1;overflow-y:auto;min-height:0;padding:12px 0 24px;}
.vC-day{text-align:center;font-size:11px;color:#9a9a9a;padding:2px 0 12px;}
.vC-row{display:flex;align-items:center;gap:9px;padding:7px 14px;}
.vC-badge{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,#12d474,#07c160);color:#fff;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex:none;box-shadow:0 1px 3px rgba(7,193,96,.35);}
.vC-bubble{position:relative;flex:none;min-height:52px;border:1.5px solid #ececec;background:#fff;border-radius:11px;display:flex;align-items:center;gap:11px;padding:0 15px;cursor:pointer;font:inherit;-webkit-tap-highlight-color:transparent;}
.vC-row.vC-cur .vC-bubble{border-color:#07c160;}
.vC-fill{position:absolute;left:0;top:0;bottom:0;width:0;background:rgba(7,193,96,.15);border-radius:9px 0 0 9px;transition:width .22s linear;}
.vC-ic{position:relative;z-index:1;width:15px;flex:none;display:flex;align-items:center;justify-content:center;}
.vC-tri{width:0;height:0;border-left:11px solid #07c160;border-top:7px solid transparent;border-bottom:7px solid transparent;display:block;}
.vC-pau{width:12px;height:15px;position:relative;display:none;}
.vC-pau::before,.vC-pau::after{content:"";position:absolute;top:0;width:4px;height:15px;background:#07c160;border-radius:1.5px;}
.vC-pau::before{left:0;}
.vC-pau::after{right:0;}
.vC-spin{display:none;width:17px;height:17px;border:2.5px solid rgba(7,193,96,.22);border-top-color:#07c160;border-radius:50%;animation:vCrot .8s linear infinite;}
.vC-row.vC-playing .vC-tri{display:none;}
.vC-row.vC-playing .vC-pau{display:block;}
.vC-row.vC-buf .vC-tri,.vC-row.vC-buf .vC-pau{display:none;}
.vC-row.vC-buf .vC-spin{display:block;}
@keyframes vCrot{to{transform:rotate(360deg);}}
.vC-wave{position:relative;z-index:1;display:flex;align-items:center;gap:3px;height:20px;}
.vC-wave i{width:3.5px;height:7px;border-radius:2px;background:#bfe9cf;transform-origin:center;}
.vC-wave i:nth-child(1){height:8px;}
.vC-wave i:nth-child(2){height:14px;}
.vC-wave i:nth-child(3){height:10px;}
.vC-wave i:nth-child(4){height:16px;}
.vC-row.vC-cur .vC-wave i{background:#07c160;}
.vC-row.vC-playing .vC-wave i{animation:vCbar .9s ease-in-out infinite;}
.vC-wave i:nth-child(2){animation-delay:.15s;}
.vC-wave i:nth-child(3){animation-delay:.3s;}
.vC-wave i:nth-child(4){animation-delay:.45s;}
@keyframes vCbar{0%,100%{transform:scaleY(.45);}50%{transform:scaleY(1.45);}}
.vC-check{display:none;position:absolute;top:-7px;right:-7px;width:18px;height:18px;border-radius:50%;background:#07c160;color:#fff;font-size:10px;line-height:15px;text-align:center;border:2px solid #ededed;z-index:2;}
.vC-row.vC-heard .vC-check{display:block;}
.vC-meta{display:flex;flex-direction:column;line-height:1.45;min-width:46px;}
.vC-meta b{font-size:13px;color:#191919;font-weight:600;}
.vC-meta small{font-size:11px;color:#a6a6a6;}
`;
  document.head.append(style);

  /* ---------------- 骨架 DOM ---------------- */
  const app = document.createElement("div");
  app.className = "vC-app";
  app.innerHTML = `
    <div class="vC-wizard">
      <div class="vC-steps"></div>
      <div class="vC-pane vC-pane1">
        <div class="vC-pane-title">選擇朗讀模板</div>
        <div class="vC-tpls"></div>
      </div>
      <div class="vC-pane vC-pane2">
        <div class="vC-pane-title">貼上合約全文</div>
        <textarea class="vC-ta" placeholder="貼上合同 TXT 全文…"></textarea>
        <div class="vC-ta-meta"><span class="vC-ta-count">尚未輸入</span><button type="button" class="vC-btn-ghost vC-sample">載入示例</button></div>
        <button type="button" class="vC-btn-main vC-next" disabled>下一步</button>
      </div>
      <div class="vC-pane vC-pane3">
        <div class="vC-pane-title">確認並生成</div>
        <div class="vC-sum">
          <div class="vC-sum-row"><span>朗讀模板</span><b class="vC-sum-tpl"></b></div>
          <div class="vC-sum-row"><span>合約字數</span><b class="vC-sum-n"></b></div>
          <div class="vC-sum-row"><span>建議語速</span><b class="vC-sum-rate"></b></div>
        </div>
        <button type="button" class="vC-btn-main vC-gen">生成語音</button>
        <div class="vC-err vC-gen-err"><span class="vC-err-t"></span><button type="button" class="vC-gen-retry">重試</button></div>
      </div>
    </div>
    <div class="vC-done">
      <b>✓</b>
      <div class="vC-done-t">已切片 · 共 <span class="vC-done-n"></span> 段</div>
      <div class="vC-done-s vC-done-dur"></div>
    </div>
    <div class="vC-main">
      <div class="vC-head">
        <div class="vC-head-row">
          <div class="vC-stat"></div>
          <button type="button" class="vC-btn-re vC-reup">重新上傳</button>
        </div>
        <button type="button" class="vC-btn-main vC-go">開始收聽</button>
        <div class="vC-err vC-play-err"><span class="vC-err-t"></span><button type="button" class="vC-play-retry">重試</button></div>
      </div>
      <div class="vC-list"></div>
    </div>
  `;
  root.append(app);
  const $ = (sel) => app.querySelector(sel);

  /* ---------------- 狀態 ---------------- */
  const p = ctx.createPlayer();
  const unsubs = [];
  const timers = [];
  let templateId = ctx.templates[0].id;
  let step = 1;
  const listened = new Set();   // 已聽（觸達）段 idx
  let refs = [];                // 每段 { row, fill }

  /* ---------------- 步驟指示器（①②③，可回退） ---------------- */
  const stepsEl = $(".vC-steps");
  const STEP_LABELS = ["選擇模板", "貼上合約", "生成"];
  const stepBtns = STEP_LABELS.map((lab, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "vC-step";
    b.innerHTML = `<b class="vC-step-n">${i + 1}</b><span></span>`;
    b.querySelector("span").textContent = lab;
    b.addEventListener("click", () => { if (i + 1 < step) setStep(i + 1); });
    stepsEl.append(b);
    if (i < STEP_LABELS.length - 1) {
      const line = document.createElement("i");
      line.className = "vC-line";
      stepsEl.append(line);
    }
    return b;
  });
  const lines = [...stepsEl.querySelectorAll(".vC-line")];

  function setStep(n) {
    step = n;
    stepBtns.forEach((b, i) => {
      b.classList.toggle("vC-on", i + 1 === n);
      b.classList.toggle("vC-done", i + 1 < n);
      b.querySelector(".vC-step-n").textContent = i + 1 < n ? "✓" : String(i + 1);
    });
    lines.forEach((l, i) => l.classList.toggle("vC-done", i + 1 < n));
    for (const pane of app.querySelectorAll(".vC-pane")) pane.classList.remove("vC-show");
    app.querySelector(`.vC-pane${n}`).classList.add("vC-show");
    if (n === 3) refreshSummary();
    if (n < 3) genErrEl.classList.remove("vC-show");
  }

  /* ---------------- 步驟 ① 模板行 ---------------- */
  const tplsEl = $(".vC-tpls");
  for (const t of ctx.templates) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "vC-tpl";
    row.innerHTML = `<div><div class="vC-tpl-name"></div><div class="vC-tpl-hint"></div></div><span class="vC-tpl-check">✓</span>`;
    row.querySelector(".vC-tpl-name").textContent = t.name;
    row.querySelector(".vC-tpl-hint").textContent = t.hint;
    row.addEventListener("click", () => { templateId = t.id; renderTplSel(); setStep(2); });
    tplsEl.append(row);
  }
  function renderTplSel() {
    [...tplsEl.children].forEach((el, i) => el.classList.toggle("vC-sel", ctx.templates[i].id === templateId));
  }
  renderTplSel();

  /* ---------------- 步驟 ② 貼上合約 ---------------- */
  const ta = $(".vC-ta");
  const taCount = $(".vC-ta-count");
  const nextBtn = $(".vC-next");
  function refreshTa() {
    const n = ta.value.trim().length;
    taCount.textContent = n ? `已輸入 ${n.toLocaleString()} 字` : "尚未輸入";
    nextBtn.disabled = n === 0;
  }
  ta.addEventListener("input", refreshTa);
  $(".vC-sample").addEventListener("click", () => { ta.value = ctx.sampleText; refreshTa(); ta.focus(); });
  nextBtn.addEventListener("click", () => setStep(3));

  /* ---------------- 步驟 ③ 摘要 + 生成 ---------------- */
  function refreshSummary() {
    const t = ctx.templates.find((x) => x.id === templateId);
    $(".vC-sum-tpl").textContent = t.name;
    $(".vC-sum-n").textContent = `${ta.value.trim().length.toLocaleString()} 字`;
    $(".vC-sum-rate").textContent = `×${ctx.preferredRate(templateId)}`;
  }

  const genBtn = $(".vC-gen");
  const genErrEl = $(".vC-gen-err");
  let generating = false;
  async function generate() {
    if (generating || ta.value.trim().length === 0) return;
    generating = true;
    genBtn.disabled = true;
    genBtn.textContent = "正在上傳並切片…";
    genErrEl.classList.remove("vC-show");
    try {
      await p.load(ta.value.trim(), templateId);
      listened.clear();
      renderList();
      $(".vC-done-n").textContent = String(p.segments.length);
      $(".vC-done-dur").textContent = `全長${ctx.fmtDur(p.totalEst)} · 點擊氣泡即可收聽`;
      show("done");
      timers.push(setTimeout(() => show("main"), 950));
    } catch (e) {
      genErrEl.querySelector(".vC-err-t").textContent = `上傳失敗：${e?.message || e}`;
      genErrEl.classList.add("vC-show");
    } finally {
      generating = false;
      genBtn.disabled = false;
      genBtn.textContent = "生成語音";
    }
  }
  genBtn.addEventListener("click", generate);
  $(".vC-gen-retry").addEventListener("click", generate);

  /* ---------------- 階段切換 ---------------- */
  let stageNow = "wizard";
  function show(stage) {
    stageNow = stage;
    $(".vC-wizard").classList.toggle("vC-hide", stage !== "wizard");
    $(".vC-done").classList.toggle("vC-show", stage === "done");
    $(".vC-main").classList.toggle("vC-show", stage === "main");
    if (stage === "main") refreshAll();
  }

  /* ---------------- 氣泡列表 ---------------- */
  const listEl = $(".vC-list");
  function renderList() {
    listEl.replaceChildren();
    const day = document.createElement("div");
    day.className = "vC-day";
    day.textContent = "— 合約語音消息 —";
    listEl.append(day);
    refs = [];
    const badge = BADGE[templateId] ?? "約";
    for (const s of p.segments) {
      const row = document.createElement("div");
      row.className = "vC-row";
      const badgeEl = document.createElement("span");
      badgeEl.className = "vC-badge";
      badgeEl.textContent = badge;
      const bubble = document.createElement("button");
      bubble.type = "button";
      bubble.className = "vC-bubble";
      bubble.style.width = `${Math.max(118, Math.min(252, 118 + Math.round(s.est_dur_s * 2.2)))}px`;
      bubble.innerHTML = `
        <span class="vC-fill"></span>
        <span class="vC-ic"><span class="vC-tri"></span><span class="vC-pau"></span><span class="vC-spin"></span></span>
        <span class="vC-wave"><i></i><i></i><i></i><i></i></span>
        <span class="vC-check">✓</span>`;
      bubble.addEventListener("click", () => {
        if (p.current === s.seg_idx && !p.buffering) p.toggle();   // 再點當前段 = 暫停/繼續；出錯時也由此重試
        else p.playFrom(s.seg_idx);
      });
      const meta = document.createElement("span");
      meta.className = "vC-meta";
      meta.innerHTML = `<b>${Math.max(1, Math.round(s.est_dur_s))}秒</b><small>第 ${s.seg_idx + 1} 段</small>`;
      row.append(badgeEl, bubble, meta);
      listEl.append(row);
      refs[s.seg_idx] = { row, fill: bubble.querySelector(".vC-fill") };
    }
  }

  function refreshBubbles() {
    const cur = p.current;
    for (const s of p.segments) {
      const r = refs[s.seg_idx];
      if (!r) continue;
      const isCur = s.seg_idx === cur;
      r.row.classList.toggle("vC-cur", isCur);
      r.row.classList.toggle("vC-playing", isCur && p.playing);
      r.row.classList.toggle("vC-buf", isCur && p.buffering && !p.playing);
      r.row.classList.toggle("vC-heard", listened.has(s.seg_idx));
      if (!isCur) r.fill.style.width = "0%";
    }
  }

  /* ---------------- 統計條 / 主按鈕 / 錯誤行 ---------------- */
  const statEl = $(".vC-stat");
  const goBtn = $(".vC-go");
  const playErrEl = $(".vC-play-err");

  function refreshStats() {
    const n = p.segments.length;
    const all = n > 0 && listened.size >= n;
    statEl.innerHTML = `共 <b>${n}</b> 段 · <b>${ctx.fmtDur(p.totalEst)}</b> · 已聽 <b>${listened.size}</b> 段${all ? " · ✓ 已全部聽完" : ""}`;
    goBtn.textContent = mainLabel();
  }
  function mainLabel() {
    if (p.error) return "重試";
    if (p.buffering) return "緩衝中…";
    if (p.playing) return "暫停";
    if (p.segments.length > 0 && listened.size >= p.segments.length) return "重新收聽";
    if (p.current >= 0) return "繼續";
    return listened.size === 0 ? "開始收聽" : "繼續收聽";
  }
  function refreshErr() {
    const e = p.error;
    playErrEl.classList.toggle("vC-show", !!e);
    if (e) playErrEl.querySelector(".vC-err-t").textContent = `播放失敗：${e} — 可點氣泡重試`;
  }
  function refreshAll() {
    refreshBubbles();
    refreshStats();
    refreshErr();
  }

  goBtn.addEventListener("click", () => {
    if (p.error) { if (p.current >= 0) p.playFrom(p.current); return; }
    if (p.playing) { p.toggle(); return; }
    if (p.segments.length > 0 && listened.size >= p.segments.length) {
      listened.clear();
      refreshBubbles();
      refreshStats();
      p.playFrom(0);
      return;
    }
    if (p.current >= 0) { p.toggle(); return; }   // 暫停中 → 繼續
    let first = 0;                                 // 否則 → 第一個未聽段
    for (const s of p.segments) {
      if (!listened.has(s.seg_idx)) { first = s.seg_idx; break; }
    }
    p.playFrom(first);
  });

  $(".vC-play-retry").addEventListener("click", () => { if (p.current >= 0) p.playFrom(p.current); });

  $(".vC-reup").addEventListener("click", () => {
    if (p.playing) p.toggle();
    show("wizard");
    setStep(2);   // 回到貼上合約，保留文字方便修改
  });

  /* ---------------- 連播跟隨滾動 ---------------- */
  function scrollToBubble(i) {
    const r = refs[i];
    if (!r) return;
    const lr = listEl.getBoundingClientRect();
    const br = r.row.getBoundingClientRect();
    const target = listEl.scrollTop + (br.top - lr.top) - (lr.height - br.height) / 2;
    listEl.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
  }

  /* ---------------- 訂閱播放器事件 ---------------- */
  unsubs.push(p.on("segment", (idx) => {
    listened.add(idx);
    refreshBubbles();
    refreshStats();
    scrollToBubble(idx);
  }));
  unsubs.push(p.on("timeupdate", (t) => {
    const cur = p.current;
    if (cur < 0) return;
    const seg = p.segments[cur];
    const r = refs[cur];
    if (!seg || !r) return;
    const local = t - seg.cumulative_start_s;   // 段內進度（近似）
    const pct = Math.max(0, Math.min(100, (local / Math.max(seg.est_dur_s, 0.001)) * 100));
    r.fill.style.width = `${pct.toFixed(1)}%`;
  }));
  unsubs.push(p.on("state", () => {
    if (stageNow === "wizard" && p.playing) p.toggle();   // 回向導後不讓殘餘連播出聲
    refreshAll();
  }));
  unsubs.push(p.on("ended", refreshAll));

  /* ---------------- 初始化 ---------------- */
  setStep(1);

  /* ---------------- dispose ---------------- */
  return () => {
    for (const u of unsubs) { try { u(); } catch {} }
    for (const t of timers) clearTimeout(t);
    p.dispose();
    style.remove();
  };
}
