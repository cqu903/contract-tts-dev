// ⚠️ THROWAWAY UI PROTOTYPE — 移動端合同朗讀 demo 的外殼。
// 職責：手機框內掛載/卸載變體、?variant= 切換、提供共享 ctx（模板元數據 + 播放控制器）。
// 播放機制複用生產 playback.mjs（SegmentAudioBuffer），但每個變體的 UI 佈局完全獨立。
import { SegmentAudioBuffer, preferredPlaybackRate } from "./playback.mjs";

/* ------------------------------------------------------------------ */
/* 共享 ctx：變體唯一的後端入口。變體不得自行 fetch。                      */
/* ------------------------------------------------------------------ */

const TEMPLATES = [
  { id: "xcash_yue", name: "中文合同 → 粵語", hint: "中文合同，朗讀為粵語；使用粵語切分和文字處理。" },
  { id: "xcash_zh", name: "中文合同 → 普通話", hint: "中文合同，朗讀為普通話；使用普通話切分和文字處理。" },
  { id: "xcash_en", name: "英文合同 → English", hint: "英文合同，朗讀為 English；使用英語切分和文字處理。" },
];

// 取自倉庫內被跟蹤的脫敏樣本 contracts/sample_contract.txt（無 PII）
const SAMPLE_TEXT = `甲方：張氏有限公司。乙方：李氏貿易行。
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

function fmtClock(sec) {
  if (!Number.isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
function fmtDur(sec) {
  if (!Number.isFinite(sec) || sec <= 0) return "0秒";
  const m = Math.round(sec / 60);
  return m >= 1 ? `約${m}分鐘` : `${Math.round(sec)}秒`;
}

/**
 * 播放控制器：封裝「上傳→逐段取音→連播→seek」的機制（與桌面 demo app.js 同邏輯），
 * 只發事件、不渲染。每個變體用 ctx.createPlayer() 自建一個。
 *
 * 狀態字段（均可直接讀）：contractId, segments, totalEst, segCount,
 *   current(當前段 idx，未開始為 -1), playing, buffering, error, rate
 * 動作：load(text, templateId), playFrom(segIdx), toggle(), setRate(r),
 *   seekToSeconds(s), currentTime(), preloadAhead(fromIdx, n), dispose()
 * 事件（player.on(evt, cb) 返回解訂函數）：
 *   "ready" () · "segment"(segIdx) · "timeupdate"(全局秒) · "state"() · "ended"()
 */
function createPlayer() {
  const audio = new Audio();
  audio.preload = "auto";
  audio.preservesPitch = true;
  const buffer = new SegmentAudioBuffer();
  const listeners = new Map();
  let objectUrl = null;

  const S = {
    contractId: null,
    segments: [],        // [{seg_idx, est_dur_s, cumulative_start_s}]
    totalEst: 0,
    current: -1,
    playing: false,
    buffering: false,
    error: null,
    rate: 1,
  };

  function on(evt, cb) {
    if (!listeners.has(evt)) listeners.set(evt, []);
    listeners.get(evt).push(cb);
    return () => {
      const arr = listeners.get(evt) ?? [];
      const i = arr.indexOf(cb);
      if (i >= 0) arr.splice(i, 1);
    };
  }
  function emit(evt, ...args) {
    for (const cb of [...(listeners.get(evt) ?? [])]) cb(...args);
  }

  function setObjectUrl(blob) {
    const prev = objectUrl;
    objectUrl = URL.createObjectURL(blob);
    audio.src = objectUrl;
    audio.playbackRate = S.rate;
    audio.defaultPlaybackRate = S.rate;
    if (prev) URL.revokeObjectURL(prev);
  }

  async function load(text, templateId) {
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
    S.contractId = data.contract_id;
    S.segments = data.segments;
    S.totalEst = data.total_est_s;
    S.current = -1;
    S.playing = false;
    S.buffering = false;
    S.error = null;
    S.rate = preferredPlaybackRate(templateId);
    audio.playbackRate = S.rate;
    audio.defaultPlaybackRate = S.rate;
    buffer.clear();
    // 後端上傳時也會後台預熱 seg 0；前端雙保險
    buffer.preload(S.contractId, 0).catch(() => {});
    emit("ready");
    return data;
  }

  function preloadAhead(fromIdx, n = 3) {
    for (let k = 1; k <= n; k++) {
      const idx = fromIdx + k;
      if (idx >= 0 && idx < S.segments.length) {
        buffer.preload(S.contractId, idx).catch(() => {});
      }
    }
  }

  async function playFrom(segIdx) {
    if (segIdx < 0 || segIdx >= S.segments.length) return;
    S.current = segIdx;
    S.buffering = true;
    S.error = null;
    emit("segment", segIdx);
    emit("state");
    try {
      const blob = await buffer.load(S.contractId, segIdx);
      if (S.current !== segIdx) return; // 等待期間用戶已 seek 別處
      setObjectUrl(blob);
      await audio.play();
      S.playing = true;
      S.buffering = false;
      emit("state");
      preloadAhead(segIdx);
    } catch (e) {
      S.playing = false;
      S.buffering = false;
      S.error = String(e?.message || e);
      emit("state");
    }
  }

  function toggle() {
    if (S.playing) {
      audio.pause();
      return;
    }
    if (S.current >= 0 && audio.src && !audio.ended) {
      audio.play().catch((e) => { S.error = String(e?.message || e); emit("state"); });
    } else {
      playFrom(S.current >= 0 ? S.current : 0);
    }
  }

  function seekToSeconds(sec) {
    if (!S.segments.length) return;
    const clamped = Math.max(0, Math.min(sec, S.totalEst - 0.01));
    let seg = S.segments.length - 1;
    for (const m of S.segments) {
      if (clamped < m.cumulative_start_s + m.est_dur_s) { seg = m.seg_idx; break; }
    }
    playFrom(seg);
  }

  function currentTime() {
    if (S.current < 0 || !S.segments.length) return 0;
    const m = S.segments[S.current];
    return Math.min(m.cumulative_start_s + audio.currentTime, S.totalEst);
  }

  audio.addEventListener("ended", () => {
    if (S.current + 1 < S.segments.length) {
      playFrom(S.current + 1);   // 自動連播
    } else {
      S.playing = false;
      emit("state");
      emit("ended");
    }
  });
  audio.addEventListener("play", () => { S.playing = true; emit("state"); });
  audio.addEventListener("pause", () => { S.playing = false; emit("state"); });
  audio.addEventListener("timeupdate", () => emit("timeupdate", currentTime()));

  function setRate(r) {
    S.rate = r;
    audio.playbackRate = r;
    audio.defaultPlaybackRate = r;
    emit("state");
  }

  function dispose() {
    audio.pause();
    audio.src = "";
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null;
    listeners.clear();
  }

  return {
    ...S,                       // 注意：展開的是快照標量；可變狀態請訂閱 "state"/"segment" 事件後重讀
    get segments() { return S.segments; },
    get totalEst() { return S.totalEst; },
    get contractId() { return S.contractId; },
    get current() { return S.current; },
    get playing() { return S.playing; },
    get buffering() { return S.buffering; },
    get error() { return S.error; },
    get rate() { return S.rate; },
    on, load, playFrom, toggle, setRate, seekToSeconds, currentTime,
    preloadAhead, dispose,
  };
}

const ctx = {
  templates: TEMPLATES,
  sampleText: SAMPLE_TEXT,
  preferredRate: preferredPlaybackRate,
  createPlayer,
  fmtClock,
  fmtDur,
};

/* ------------------------------------------------------------------ */
/* 變體註冊表 + 切換器                                                  */
/* ------------------------------------------------------------------ */

const VARIANT_FILES = {
  A: "./prototype-mobile-a.mjs",
  B: "./prototype-mobile-b.mjs",
  C: "./prototype-mobile-c.mjs",
};

const screen = document.getElementById("screen");
const label = document.getElementById("switcherLabel");
let currentVariant = null;
let disposeCurrent = null;

function readVariantFromUrl() {
  const v = new URLSearchParams(location.search).get("variant")?.toUpperCase();
  return VARIANT_FILES[v] ? v : "A";
}

function writeVariantToUrl(v) {
  const url = new URL(location.href);
  url.searchParams.set("variant", v);
  history.replaceState(null, "", url);
}

async function show(v) {
  const target = VARIANT_FILES[v] ? v : "A";
  if (disposeCurrent) { try { disposeCurrent(); } catch {} disposeCurrent = null; }
  screen.replaceChildren();
  currentVariant = target;
  writeVariantToUrl(target);
  let mod;
  try {
    mod = await import(/* @vite-ignore */ VARIANT_FILES[target] + `?t=${Date.now()}`);
  } catch (e) {
    screen.replaceChildren(Object.assign(document.createElement("div"), {
      className: "proto-error",
      textContent: `變體 ${target} 載入失敗：${e}\n（檢查 frontend/prototype-mobile-${target.toLowerCase()}.mjs）`,
    }));
    label.textContent = `${target} · 載入失敗`;
    return;
  }
  label.innerHTML = "";
  label.append(`${target} · ${mod.label}`);
  const sub = document.createElement("small");
  sub.textContent = `變體 ${target}/${Object.keys(VARIANT_FILES).join("/")} · throwaway`;
  label.append(sub);
  if (currentVariant !== target) return; // 切換期間又切走了
  const root = document.createElement("div");
  root.style.cssText = "position:absolute;inset:0;overflow:hidden;";
  screen.append(root);
  disposeCurrent = mod.mount(root, ctx) ?? null;
}

function cycle(dir) {
  const keys = Object.keys(VARIANT_FILES);
  const i = keys.indexOf(currentVariant ?? "A");
  show(keys[(i + dir + keys.length) % keys.length]);
}

document.getElementById("prevVariant").addEventListener("click", () => cycle(-1));
document.getElementById("nextVariant").addEventListener("click", () => cycle(1));
document.addEventListener("keydown", (e) => {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  const t = e.target;
  if (t instanceof HTMLElement && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
  cycle(e.key === "ArrowLeft" ? -1 : 1);
});
window.addEventListener("pagehide", () => disposeCurrent?.());

show(readVariantFromUrl());
