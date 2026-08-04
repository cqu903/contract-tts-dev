const PRELOAD_AHEAD = 3;

const bar = document.getElementById("bar");
const statusEl = document.getElementById("status");
const audio = document.getElementById("audio");
const clauseEl = document.getElementById("clause");
const textInput = document.getElementById("text");
const uploadBtn = document.getElementById("upload");
const templateInput = document.getElementById("template");
const templateHint = document.getElementById("templateHint");

const TEMPLATE_HINTS = {
  xcash_yue: "中文合同，朗讀為粵語；使用粵語切分和文字處理。",
  xcash_zh: "中文合同，朗讀為普通話；使用普通話切分和文字處理。",
  xcash_en: "英文合同，朗讀為 English；使用英語切分和文字處理。",
};

let contractId = null;
let segs = [];        // [{seg_idx, est_dur_s, cumulative_start_s}]
let totalEst = 0;
let current = 0;

function updateTemplateHint() {
  templateHint.textContent = TEMPLATE_HINTS[templateInput.value];
}

templateInput.addEventListener("change", updateTemplateHint);
updateTemplateHint();

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
  const r = await fetch(`/api/contracts/${contractId}/segments/${segIdx}`);
  if (!r.ok) throw new Error(`segment ${segIdx} failed: ${r.status}`);
  return await r.blob();
}

async function playFrom(segIdx) {
  current = segIdx;
  statusEl.textContent = `生成/載入 第 ${segIdx + 1}/${segs.length} 段…`;
  try {
    const blob = await loadSegment(segIdx);
    audio.src = URL.createObjectURL(blob);
    clauseEl.textContent = `第 ${segIdx + 1}/${segs.length} 段`;
    bar.value = secondsToBar(segs[segIdx].cumulative_start_s);
    await audio.play();
    statusEl.textContent = `播放 第 ${segIdx + 1}/${segs.length} 段`;
    for (let k = 1; k <= PRELOAD_AHEAD; k++) {
      const n = segIdx + k;
      if (n < segs.length) fetch(`/api/contracts/${contractId}/segments/${n}/preload`, { method: "POST" });
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

uploadBtn.addEventListener("click", async () => {
  const text = textInput.value.trim();
  if (!text) { statusEl.textContent = "請貼上合同文字"; return; }
  const templateId = templateInput.value;
  uploadBtn.disabled = true;
  statusEl.textContent = templateId + " 上傳切片中…";
  try {
    const r = await fetch("/api/contracts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, template_id: templateId }),
    });
    if (!r.ok) {
      let detail = "HTTP " + r.status;
      try { detail = (await r.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    const data = await r.json();
    contractId = data.contract_id;
    segs = data.segments;
    totalEst = data.total_est_s;
    bar.disabled = false;
    current = 0;
    // preload seg 0 (also server-warmed) so the native play button works immediately
    try {
      const blob = await loadSegment(0);
      audio.src = URL.createObjectURL(blob);
      clauseEl.textContent = `第 1/${segs.length} 段`;
      bar.value = 0;
      statusEl.textContent = templateId + " · 就緒 · 共 " + segs.length
        + " 段 · 預估 " + totalEst.toFixed(0) + "s(已預載第 1 段,按播放即可)";
    } catch (e) {
      statusEl.textContent = `就緒 · 預載第 1 段失敗:${e.message}(可拖動進度條開始)`;
    }
  } catch (e) {
    statusEl.textContent = "上傳失敗:" + e.message;
    uploadBtn.disabled = false;
  }
});
