// ⚠️ THROWAWAY PROTOTYPE — 變體 A「全屏播放器」：有聲書 / 播客形態（player-first）。
// 依賴 prototype-mobile-shell.mjs 注入的 ctx（模板元數據 + 播放控制器 p）；零 import、零自行 fetch。
// 視覺概念：夜間帳簿 —— 深墨綠底、象牙墨色、朱砂「印章」紅做唯一強調色（蓋章 = 按下播放）；
// 大數字用襯線體呼應合同數額；進度條是按段落打刻度的「標尺」。
export const key = "A";
export const label = "全屏播放器";

const CSS = `
.vA-app {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  background: linear-gradient(180deg, #12261F 0%, #0C1D17 55%, #0A1712 100%);
  color: #EDE7D8;
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "PingFang HK", "Noto Sans HK", "Microsoft JhengHei", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.vA-scr {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  animation: vA-in .28s ease both;
}
.vA-hide { display: none !important; }

/* ---------------- 畫面一：上傳 ---------------- */
.vA-head { flex: none; padding: 26px 22px 12px; }
.vA-brandrow { display: flex; align-items: center; gap: 13px; }
.vA-seal {
  width: 46px; height: 46px; flex: none; border-radius: 10px;
  background: #D0442E; color: #FFF6ED;
  display: flex; align-items: center; justify-content: center;
  font-family: Georgia, "Songti HK", serif; font-size: 25px; font-weight: 700;
  box-shadow: inset 0 0 0 2px rgba(255,246,237,.25), 0 3px 12px rgba(208,68,46,.32);
}
.vA-title { font-size: 26px; font-weight: 700; letter-spacing: 1px; line-height: 1.25; }
.vA-sub { margin-top: 3px; font-size: 12.5px; color: #93A79B; letter-spacing: 1.5px; }
.vA-body { flex: 1; min-height: 0; overflow-y: auto; padding: 4px 22px 14px; }
.vA-label { font-size: 12px; letter-spacing: 3px; color: #7E948A; margin: 20px 0 9px; }
.vA-cards { display: flex; flex-direction: column; gap: 10px; }
.vA-card {
  display: flex; align-items: center; gap: 12px;
  width: 100%; min-height: 74px; text-align: left;
  padding: 12px 14px; border-radius: 14px;
  border: 1px solid rgba(237,231,216,.12);
  background: rgba(21,44,36,.55);
  color: inherit; font: inherit; cursor: pointer;
  appearance: none; -webkit-appearance: none;
}
.vA-card.vA-on {
  border-color: rgba(237,231,216,.38);
  background: #1A342B;
  box-shadow: inset 3px 0 0 #D0442E;
}
.vA-cardmain { flex: 1; min-width: 0; }
.vA-cardname { font-size: 16.5px; font-weight: 600; color: #93A79B; }
.vA-card.vA-on .vA-cardname { color: #EDE7D8; }
.vA-cardhint { font-size: 12.5px; line-height: 1.5; margin-top: 2px; color: #5F756A; }
.vA-card.vA-on .vA-cardhint { color: #8AA394; }
.vA-radio {
  width: 20px; height: 20px; flex: none; border-radius: 50%;
  border: 2px solid rgba(237,231,216,.28);
}
.vA-card.vA-on .vA-radio {
  border-color: #D0442E;
  background: radial-gradient(circle, #D0442E 0 5px, transparent 5.5px);
}
.vA-ta {
  width: 100%; min-height: 138px; padding: 12px 14px;
  border-radius: 14px; border: 1px solid rgba(237,231,216,.14);
  background: rgba(9,23,18,.72); color: #EDE7D8;
  font-family: inherit; font-size: 14px; line-height: 1.7;
  resize: none; outline: none;
}
.vA-ta:focus { border-color: rgba(237,231,216,.42); }
.vA-tarow { display: flex; align-items: center; justify-content: space-between; }
.vA-count { font-size: 12px; color: #5F756A; }
.vA-sample {
  appearance: none; -webkit-appearance: none; background: none; border: none;
  min-height: 44px; padding: 10px 4px; cursor: pointer;
  color: #EDE7D8; font: inherit; font-size: 13.5px;
  text-decoration: underline; text-underline-offset: 4px; text-decoration-color: rgba(237,231,216,.5);
}
.vA-foot {
  flex: none; padding: 8px 22px calc(14px + env(safe-area-inset-bottom, 0px));
  border-top: 1px solid rgba(237,231,216,.08);
  background: rgba(9,20,16,.55);
}
.vA-err1 { display: none; margin-top: 6px; font-size: 13px; line-height: 1.55; color: #FF9A82; }
.vA-err1.vA-show { display: block; }
.vA-cta {
  width: 100%; height: 58px; margin-top: 10px;
  border: none; border-radius: 16px;
  background: #D0442E; color: #FFF6ED;
  font: inherit; font-size: 17px; font-weight: 700; letter-spacing: 5px;
  display: flex; align-items: center; justify-content: center; gap: 10px;
  cursor: pointer;
}
.vA-cta:active { background: #B03723; }
.vA-cta[disabled] { opacity: .8; cursor: default; }

/* ---------------- 畫面二：播放器 ---------------- */
.vA-top {
  flex: none; display: flex; align-items: center; gap: 8px;
  height: 56px; padding: 0 14px 0 6px;
  border-bottom: 1px solid rgba(237,231,216,.08);
}
.vA-back {
  width: 44px; height: 44px; flex: none;
  display: flex; align-items: center; justify-content: center;
  background: none; border: none; color: #EDE7D8; border-radius: 12px; cursor: pointer;
}
.vA-back:active { background: rgba(237,231,216,.08); }
.vA-badge {
  font-size: 12px; color: #AABBB0;
  border: 1px solid rgba(237,231,216,.22); border-radius: 999px;
  padding: 5px 12px; max-width: 190px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.vA-topseg { margin-left: auto; font-size: 13px; color: #93A79B; white-space: nowrap; }
.vA-stage { flex: 1; min-height: 0; display: flex; overflow-y: auto; padding: 0 26px; }
.vA-stagein { margin: auto 0; width: 100%; display: flex; flex-direction: column; }

.vA-eyebrow { font-size: 12px; letter-spacing: 6px; color: #5F756A; text-align: center; }
.vA-bigrow { display: flex; align-items: baseline; justify-content: center; gap: 8px; margin-top: 4px; }
.vA-bigpre { font-size: 18px; color: #93A79B; }
.vA-bign {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 86px; line-height: 1.05; color: #EDE7D8;
}
.vA-bigm { font-size: 20px; color: #93A79B; }
.vA-clockrow {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-top: 12px; font-size: 13.5px; color: #93A79B;
}
.vA-clocknum { font-family: Georgia, "Times New Roman", serif; font-size: 17px; color: #EDE7D8; }

.vA-barwrap { position: relative; margin-top: 40px; }
.vA-hint {
  position: absolute; top: -40px; transform: translateX(-50%);
  background: #EDE7D8; color: #12261F;
  font-size: 12.5px; font-weight: 600; line-height: 1;
  padding: 7px 12px; border-radius: 999px; white-space: nowrap;
  pointer-events: none;
}
.vA-hint::after {
  content: ""; position: absolute; left: 50%; bottom: -3px;
  width: 8px; height: 8px; background: #EDE7D8;
  transform: translateX(-50%) rotate(45deg);
}
.vA-bar {
  height: 44px; display: flex; align-items: center;
  touch-action: none; cursor: pointer; border-radius: 12px;
  outline: none; user-select: none; -webkit-user-select: none;
}
.vA-bar:focus-visible { outline: 2px solid rgba(237,231,216,.6); outline-offset: 3px; }
.vA-track { position: relative; width: 100%; height: 12px; border-radius: 999px; background: rgba(237,231,216,.13); }
.vA-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0%; border-radius: 999px; background: #EDE7D8; }
.vA-bar:not(.vA-drag) .vA-fill { transition: width .15s linear; }
.vA-tick {
  position: absolute; top: 1px; bottom: 1px; width: 2px; margin-left: -1px;
  border-radius: 1px;
  background: rgba(240,236,226,.92);
  box-shadow: 0 0 0 1.5px #0C1D17;   /* 深色描邊：在象牙填充與空軌道上都可見 */
}
.vA-knob {
  position: absolute; top: 50%; left: 0%; width: 22px; height: 22px;
  transform: translate(-50%, -50%); border-radius: 50%;
  background: #FBF7EF;
  box-shadow: 0 0 0 3px #0C1D17, 0 3px 9px rgba(0,0,0,.45);
  pointer-events: none;
}
.vA-bar:not(.vA-drag) .vA-knob { transition: left .15s linear; }

.vA-ctrl { display: flex; align-items: center; justify-content: center; gap: 36px; margin-top: 30px; }
.vA-skip {
  width: 56px; height: 56px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: none; border: none; color: #C9D4CB; cursor: pointer;
}
.vA-skip:active { background: rgba(237,231,216,.08); }
.vA-play {
  width: 80px; height: 80px; border-radius: 50%;
  border: none; background: #D0442E; color: #FFF6ED;
  display: flex; align-items: center; justify-content: center; cursor: pointer;
  box-shadow: 0 10px 30px rgba(208,68,46,.35), inset 0 0 0 2px rgba(255,246,237,.22);
}
.vA-play:active { transform: scale(.96); background: #B03723; }
.vA-rates { display: flex; justify-content: center; gap: 10px; margin-top: 28px; }
.vA-chip {
  min-width: 66px; height: 44px; padding: 0 16px;
  border-radius: 999px; border: 1px solid rgba(237,231,216,.22);
  background: none; color: #93A79B;
  font: inherit; font-size: 14px; cursor: pointer;
}
.vA-chip.vA-on { background: #EDE7D8; border-color: #EDE7D8; color: #12261F; font-weight: 700; }

.vA-status {
  flex: none; display: flex; align-items: center; justify-content: center; gap: 10px;
  min-height: 52px; padding: 4px 22px calc(10px + env(safe-area-inset-bottom, 0px));
  border-top: 1px solid rgba(237,231,216,.08);
  font-size: 13.5px; color: #93A79B;
}
.vA-dot { width: 8px; height: 8px; flex: none; border-radius: 50%; background: #5F756A; }
.vA-dot-play { background: #D0442E; animation: vA-pulse 1.6s ease-in-out infinite; }
.vA-dot-buf {
  width: 14px; height: 14px; background: none;
  border: 2px solid rgba(237,231,216,.25); border-top-color: #EDE7D8;
  animation: vA-rot .8s linear infinite;
}
.vA-dot-err { background: #FF6A4D; }
.vA-retry {
  min-height: 44px; padding: 8px 16px; margin-left: 4px;
  border-radius: 12px; border: 1px solid rgba(255,138,115,.55);
  background: none; color: #FF9A82;
  font: inherit; font-size: 13.5px; cursor: pointer;
}

.vA-spin {
  width: 18px; height: 18px; flex: none; border-radius: 50%;
  border: 2.5px solid rgba(255,246,237,.35); border-top-color: #FFF6ED;
  animation: vA-rot .8s linear infinite;
}
.vA-spinBig { width: 28px; height: 28px; }

@keyframes vA-rot { to { transform: rotate(360deg); } }
@keyframes vA-pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .45; transform: scale(.72); } }
@keyframes vA-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  .vA-dot-play, .vA-spin, .vA-dot-buf, .vA-scr { animation: none; }
}
.vA-card:focus-visible, .vA-sample:focus-visible, .vA-cta:focus-visible,
.vA-back:focus-visible, .vA-skip:focus-visible, .vA-play:focus-visible,
.vA-chip:focus-visible, .vA-retry:focus-visible {
  outline: 2px solid rgba(237,231,216,.65); outline-offset: 2px;
}
`;

const IC = {
  back:
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14.5 5.5 8 12l6.5 6.5"/></svg>',
  play:
    '<svg viewBox="0 0 24 24" width="34" height="34" fill="currentColor" aria-hidden="true" style="margin-left:4px"><path d="M8 5.2v13.6L19 12z"/></svg>',
  pause:
    '<svg viewBox="0 0 24 24" width="30" height="30" fill="currentColor" aria-hidden="true"><path d="M7.4 5h3.4v14H7.4zM13.2 5h3.4v14h-3.4z"/></svg>',
  prev:
    '<svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor" aria-hidden="true"><path d="M6 5h2.2v14H6z"/><path d="M20 6.1v11.8L11 12z"/></svg>',
  next:
    '<svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor" aria-hidden="true"><path d="M15.8 5H18v14h-2.2z"/><path d="M4 6.1v11.8L13 12z"/></svg>',
};

const RATES = [1.0, 1.1, 1.25];
const rateLabel = (r) => (r === 1.25 ? "1.25×" : r.toFixed(1) + "×");

export function mount(root, ctx) {
  const p = ctx.createPlayer();
  let selected = ctx.templates[0].id; // 選中的模板 id
  let endedFlag = false;              // 播完（p.current 停在最後一段，需另行標記）
  let dragging = false;               // 進度條拖動中（此時不回寫進度渲染）
  let loading = false;                // 上載中（防重複提交）

  const style = document.createElement("style");
  style.textContent = CSS;
  document.head.append(style);

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };

  const app = el("div", "vA-app");
  const scr1 = el("div", "vA-scr");
  const scr2 = el("div", "vA-scr vA-hide");
  app.append(scr1, scr2);
  root.append(app);

  /* ================= 畫面一：上傳 ================= */

  const head = el("div", "vA-head");
  const brandrow = el("div", "vA-brandrow");
  brandrow.append(el("div", "vA-seal", "讀"));
  const tcol = el("div");
  tcol.append(el("div", "vA-title", "合約朗讀"));
  tcol.append(el("div", "vA-sub", "對外服務 demo"));
  brandrow.append(tcol);
  head.append(brandrow);

  const body = el("div", "vA-body");
  body.append(el("div", "vA-label", "朗讀方式"));
  const cardsGroup = el("div", "vA-cards");
  cardsGroup.setAttribute("role", "radiogroup");
  cardsGroup.setAttribute("aria-label", "朗讀方式");
  const cards = ctx.templates.map((t) => {
    const btn = el("button", "vA-card");
    btn.type = "button";
    btn.setAttribute("role", "radio");
    const main = el("div", "vA-cardmain");
    main.append(el("div", "vA-cardname", t.name));
    main.append(el("div", "vA-cardhint", t.hint));
    btn.append(main, el("span", "vA-radio"));
    btn.addEventListener("click", () => {
      selected = t.id;
      renderCards();
    });
    cardsGroup.append(btn);
    return { btn, id: t.id };
  });
  body.append(cardsGroup);

  body.append(el("div", "vA-label", "合約文字"));
  const ta = el("textarea", "vA-ta");
  ta.rows = 6;
  ta.placeholder = "貼上需要朗讀的合約全文…";
  ta.spellcheck = false;
  const countEl = el("span", "vA-count", "已輸入 0 字");
  const sampleBtn = el("button", "vA-sample", "載入示例");
  sampleBtn.type = "button";
  const tarow = el("div", "vA-tarow");
  tarow.append(countEl, sampleBtn);
  body.append(ta, tarow);

  const foot = el("div", "vA-foot");
  const err1 = el("div", "vA-err1");
  const cta = el("button", "vA-cta");
  cta.type = "button";
  cta.innerHTML = "<span>開始朗讀</span>";
  foot.append(err1, cta);
  scr1.append(head, body, foot);

  /* ================= 畫面二：播放器 ================= */

  const top = el("div", "vA-top");
  const backBtn = el("button", "vA-back");
  backBtn.type = "button";
  backBtn.setAttribute("aria-label", "返回上傳頁");
  backBtn.innerHTML = IC.back;
  const badge = el("div", "vA-badge", ctx.templates[0].name);
  const topseg = el("div", "vA-topseg", "段 –");
  top.append(backBtn, badge, topseg);

  const stage = el("div", "vA-stage");
  const stagein = el("div", "vA-stagein");
  stagein.append(el("div", "vA-eyebrow", "合約段落"));
  const bigrow = el("div", "vA-bigrow");
  const bigpre = el("span", "vA-bigpre", "第");
  const bign = el("span", "vA-bign", "1");
  const bigm = el("span", "vA-bigm", "/ – 段");
  bigrow.append(bigpre, bign, bigm);
  const clockrow = el("div", "vA-clockrow");
  const clockL = el("span", null, "已播 ");
  const clockPlay = el("span", "vA-clocknum", "0:00");
  clockL.append(clockPlay);
  const clockR = el("span", null, "");
  const clockTotal = el("span", null, "–");
  clockR.append(clockTotal, " · 剩餘 ");
  const clockRem = el("span", "vA-clocknum", "0:00");
  clockR.append(clockRem);
  clockrow.append(clockL, clockR);

  const barwrap = el("div", "vA-barwrap");
  const hint = el("div", "vA-hint vA-hide", "跳至第 1 段");
  const bar = el("div", "vA-bar");
  bar.tabIndex = 0;
  bar.setAttribute("role", "slider");
  bar.setAttribute("aria-label", "朗讀進度（可拖動或左右鍵跳轉）");
  bar.setAttribute("aria-valuemin", "0");
  const track = el("div", "vA-track");
  const fill = el("div", "vA-fill");
  const knob = el("div", "vA-knob");
  track.append(fill, knob);
  bar.append(track);
  barwrap.append(hint, bar);
  stagein.append(bigrow, clockrow, barwrap);

  const ctrl = el("div", "vA-ctrl");
  const prevBtn = el("button", "vA-skip");
  prevBtn.type = "button";
  prevBtn.setAttribute("aria-label", "上一段");
  prevBtn.innerHTML = IC.prev;
  const playBtn = el("button", "vA-play");
  playBtn.type = "button";
  playBtn.setAttribute("aria-label", "播放");
  playBtn.innerHTML = IC.play;
  const nextBtn = el("button", "vA-skip");
  nextBtn.type = "button";
  nextBtn.setAttribute("aria-label", "下一段");
  nextBtn.innerHTML = IC.next;
  ctrl.append(prevBtn, playBtn, nextBtn);
  stagein.append(ctrl);

  const ratesRow = el("div", "vA-rates");
  const chips = RATES.map((r) => {
    const c = el("button", "vA-chip", rateLabel(r));
    c.type = "button";
    c.addEventListener("click", () => p.setRate(r));
    ratesRow.append(c);
    return { c, r };
  });
  stagein.append(ratesRow);
  stage.append(stagein);

  const status = el("div", "vA-status");
  const dot = el("span", "vA-dot");
  const stext = el("span", null, "就緒");
  const retryBtn = el("button", "vA-retry vA-hide", "重試");
  retryBtn.type = "button";
  status.append(dot, stext, retryBtn);
  scr2.append(top, stage, status);

  /* ================= 渲染 ================= */

  function renderCards() {
    for (const { btn, id } of cards) {
      const on = id === selected;
      btn.classList.toggle("vA-on", on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
    }
  }

  function renderTop() {
    const tpl = ctx.templates.find((t) => t.id === selected);
    badge.textContent = tpl ? tpl.name : selected;
    const n = p.segments.length;
    topseg.textContent = n ? `段 ${Math.max(p.current, 0) + 1}/${n}` : "段 –";
  }

  function renderBig() {
    const n = p.segments.length;
    bign.textContent = String(n ? Math.max(p.current, 0) + 1 : "–");
    bigm.textContent = n ? `/ ${n} 段` : "/ – 段";
  }

  function renderClock(t) {
    clockPlay.textContent = ctx.fmtClock(t);
    clockTotal.textContent = ctx.fmtDur(p.totalEst);
    clockRem.textContent = ctx.fmtClock(Math.max(p.totalEst - t, 0));
  }

  function renderBar(t) {
    const pct = p.totalEst > 0 ? Math.min(100, Math.max(0, (t / p.totalEst) * 100)) : 0;
    fill.style.width = pct + "%";
    knob.style.left = pct + "%";
    bar.setAttribute("aria-valuemax", String(Math.round(p.totalEst)));
    bar.setAttribute("aria-valuenow", String(Math.round(t)));
  }

  function renderTicks() {
    const ticks = p.segments.map((m) => {
      const tk = el("div", "vA-tick");
      tk.style.left = (m.cumulative_start_s / p.totalEst) * 100 + "%";
      return tk;
    });
    track.replaceChildren(fill, ...ticks, knob);
  }

  function renderChips() {
    for (const { c, r } of chips) c.classList.toggle("vA-on", Math.abs(p.rate - r) < 1e-9);
  }

  function renderStatus() {
    const err = p.error;
    retryBtn.classList.toggle("vA-hide", !err);
    stext.style.color = "";
    if (err) {
      dot.className = "vA-dot vA-dot-err";
      stext.textContent = `錯誤：${err}`;
      stext.style.color = "#FF9A82";
    } else if (p.buffering) {
      dot.className = "vA-dot vA-dot-buf";
      stext.textContent = "緩衝中…";
    } else if (endedFlag) {
      dot.className = "vA-dot";
      stext.textContent = "已結束 · 按播放鍵可重頭再聽";
    } else if (p.playing) {
      dot.className = "vA-dot vA-dot-play";
      stext.textContent = "播放中";
    } else if (p.current >= 0) {
      dot.className = "vA-dot";
      stext.textContent = `已暫停 · 第 ${p.current + 1} 段`;
    } else {
      dot.className = "vA-dot";
      stext.textContent = "就緒 · 按播放開始";
    }
  }

  function renderGlyph() {
    if (p.buffering && !p.playing) {
      playBtn.innerHTML = '<span class="vA-spin vA-spinBig"></span>';
      playBtn.setAttribute("aria-label", "緩衝中");
    } else if (p.playing) {
      playBtn.innerHTML = IC.pause;
      playBtn.setAttribute("aria-label", "暫停");
    } else {
      playBtn.innerHTML = IC.play;
      playBtn.setAttribute("aria-label", "播放");
    }
  }

  function renderAll(t) {
    renderTop();
    renderBig();
    renderClock(t);
    renderBar(t);
    renderChips();
    renderStatus();
    renderGlyph();
  }

  function renderCount() {
    countEl.textContent = `已輸入 ${ta.value.trim().length} 字`;
  }

  function setErr1(msg) {
    if (msg) {
      err1.textContent = msg;
      err1.classList.add("vA-show");
    } else {
      err1.classList.remove("vA-show");
    }
  }

  function show1() {
    scr1.classList.remove("vA-hide");
    scr2.classList.add("vA-hide");
  }
  function show2() {
    scr2.classList.remove("vA-hide");
    scr1.classList.add("vA-hide");
  }

  /* ================= 交互 ================= */

  ta.addEventListener("input", renderCount);
  sampleBtn.addEventListener("click", () => {
    ta.value = ctx.sampleText;
    renderCount();
    setErr1(null);
  });

  async function start() {
    if (loading) return;
    const text = ta.value.trim();
    if (!text) {
      setErr1("請先貼上合約文字，或點右下「載入示例」。");
      return;
    }
    loading = true;
    setErr1(null);
    cta.disabled = true;
    cta.innerHTML = '<span class="vA-spin"></span><span>切片中…</span>';
    try {
      await p.load(text, selected);
      endedFlag = false;
      show2();
      renderAll(0);
      p.playFrom(0);
    } catch (e) {
      setErr1(`上載失敗：${e && e.message ? e.message : e} · 可重試`);
    } finally {
      loading = false;
      cta.disabled = false;
      cta.innerHTML = "<span>開始朗讀</span>";
    }
  }
  cta.addEventListener("click", start);

  backBtn.addEventListener("click", () => {
    if (p.playing) p.toggle(); // 返回上傳頁即暫停（此形態無迷你播放條）
    show1();
  });

  playBtn.addEventListener("click", () => {
    if (endedFlag) {
      endedFlag = false;
      p.playFrom(0);
      return;
    }
    p.toggle();
  });
  prevBtn.addEventListener("click", () => {
    endedFlag = false;
    p.playFrom(Math.max(0, p.current - 1));
  });
  nextBtn.addEventListener("click", () => {
    endedFlag = false;
    const n = p.segments.length;
    if (n) p.playFrom(Math.min(p.current + 1, n - 1));
  });
  retryBtn.addEventListener("click", () => {
    endedFlag = false;
    p.playFrom(p.current >= 0 ? p.current : 0);
  });

  // —— 進度條：指針拖動（拖動中提示將跳至第幾段，松手才 seek）——
  function segAt(sec) {
    const segs = p.segments;
    for (const m of segs) {
      if (sec < m.cumulative_start_s + m.est_dur_s) return m.seg_idx;
    }
    return segs.length ? segs[segs.length - 1].seg_idx : 0;
  }
  function fracFromEvent(e) {
    const r = track.getBoundingClientRect();
    return r.width > 0 ? Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) : 0;
  }
  function applyDrag(f) {
    const pct = f * 100;
    fill.style.width = pct + "%";
    knob.style.left = pct + "%";
    const w = track.clientWidth;
    const x = Math.max(60, Math.min(w - 60, f * w));
    hint.style.left = x + "px";
    hint.textContent = `跳至第 ${segAt(f * p.totalEst) + 1} 段`;
    hint.classList.remove("vA-hide");
  }
  bar.addEventListener("pointerdown", (e) => {
    if (!p.segments.length) return;
    dragging = true;
    bar.classList.add("vA-drag");
    bar.setPointerCapture(e.pointerId);
    applyDrag(fracFromEvent(e));
  });
  bar.addEventListener("pointermove", (e) => {
    if (dragging) applyDrag(fracFromEvent(e));
  });
  bar.addEventListener("pointerup", (e) => {
    if (!dragging) return;
    const f = fracFromEvent(e);
    dragging = false;
    bar.classList.remove("vA-drag");
    hint.classList.add("vA-hide");
    endedFlag = false;
    p.seekToSeconds(f * p.totalEst);
    renderBar(f * p.totalEst);
  });
  bar.addEventListener("pointercancel", () => {
    dragging = false;
    bar.classList.remove("vA-drag");
    hint.classList.add("vA-hide");
    renderBar(p.currentTime());
  });
  bar.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    e.stopPropagation(); // 外殼把 ←→ 綁定為變體切換，焦點在進度條時不外傳
    const d = e.key === "ArrowLeft" ? -10 : 10;
    endedFlag = false;
    const t = Math.max(0, p.currentTime() + d);
    p.seekToSeconds(t);
    renderBar(t);
  });

  /* ================= 訂閱播放器事件 ================= */

  const offs = [
    p.on("ready", () => {
      endedFlag = false;
      renderTicks();
      renderAll(0);
    }),
    p.on("segment", () => {
      endedFlag = false;
      renderTop();
      renderBig();
      renderStatus();
      renderGlyph();
    }),
    p.on("timeupdate", (sec) => {
      if (dragging) return;
      renderClock(sec);
      renderBar(sec);
    }),
    p.on("state", () => {
      renderStatus();
      renderGlyph();
      renderChips();
      if (!dragging) {
        const t = p.currentTime();
        renderClock(t);
        renderBar(t);
      }
    }),
    p.on("ended", () => {
      endedFlag = true;
      renderStatus();
    }),
  ];

  renderCards();
  renderCount();
  renderAll(0);

  return function dispose() {
    for (const off of offs) off();
    p.dispose();
    style.remove();
    root.replaceChildren();
  };
}
