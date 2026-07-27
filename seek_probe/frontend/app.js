const CONTRACT_ID = new URLSearchParams(location.search).get("contract") || "sample";
const PRELOAD_AHEAD = 3;

const bar = document.getElementById("bar");
const statusEl = document.getElementById("status");
const audio = document.getElementById("audio");
const clauseEl = document.getElementById("clause");

let segs = [];        // [{seg_idx, est_dur_s, cumulative_start_s}]
let totalEst = 0;
let current = 0;
let segTexts = [];

function barToSeconds(v) {
  return (Number(v) / 1000) * totalEst;
}
function secondsToBar(s) {
  return Math.round((s / totalEst) * 1000);
}
function segmentAtSeconds(s) {
  for (const m of segs) {
    if (s < m.cumulative_start_s + m.est_dur_s) return m.seg_idx;
  }
  return segs.length - 1;
}

async function loadSegment(segIdx) {
  const r = await fetch(`/api/segment/${CONTRACT_ID}/${segIdx}`);
  if (!r.ok) throw new Error(`segment ${segIdx} failed: ${r.status}`);
  return await r.blob();
}

async function playFrom(segIdx) {
  current = segIdx;
  statusEl.textContent = `生成/載入 第 ${segIdx + 1}/${segs.length} 段…`;
  try {
    const blob = await loadSegment(segIdx);
    audio.src = URL.createObjectURL(blob);
    clauseEl.textContent = segTexts[segIdx] || "";
    bar.value = secondsToBar(segs[segIdx].cumulative_start_s);
    await audio.play();
    statusEl.textContent = `播放 第 ${segIdx + 1}/${segs.length} 段`;
    for (let k = 1; k <= PRELOAD_AHEAD; k++) {
      const n = segIdx + k;
      if (n < segs.length) fetch(`/api/preload/${CONTRACT_ID}/${n}`, { method: "POST" });
    }
  } catch (e) {
    statusEl.textContent = "錯誤:" + e.message;
  }
}

audio.addEventListener("ended", () => {
  if (current + 1 < segs.length) playFrom(current + 1);
  else statusEl.textContent = "完畢";
});

bar.addEventListener("change", () => {
  const seg = segmentAtSeconds(barToSeconds(bar.value));
  playFrom(seg);
});

(async function init() {
  const r = await fetch(`/api/contract/${CONTRACT_ID}`);
  const data = await r.json();
  segs = data.segments;
  totalEst = data.total_est_s;
  segTexts = data.texts;
  bar.disabled = false;
  statusEl.textContent = `就緒 · 共 ${segs.length} 段 · 預載第 1 段中…`;
  // 預載第 1 段並設為 audio.src,這樣首次按「播放」就能直接出聲。
  // 否則原生播放鍵因 audio.src 為空而無反應,須先拖動進度條才會 playFrom。
  current = 0;
  try {
    const blob = await loadSegment(0);
    audio.src = URL.createObjectURL(blob);
    clauseEl.textContent = segTexts[0] || "";
    bar.value = 0;
    statusEl.textContent = `就緒 · 共 ${segs.length} 段 · 預估 ${totalEst.toFixed(0)}s(已預載第 1 段,按播放即可)`;
  } catch (e) {
    statusEl.textContent = `就緒 · 預載第 1 段失敗:${e.message}(可拖動進度條開始)`;
  }
})();
