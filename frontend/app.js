import {
  SegmentAudioBuffer,
  preferredPlaybackRate,
} from "./playback.mjs";

const INITIAL_SEGMENT_REQUEST_COUNT = 3;
const PRELOAD_AHEAD = 3;

const bar = document.getElementById("bar");
const statusEl = document.getElementById("status");
const audio = document.getElementById("audio");
const clauseEl = document.getElementById("clause");
const textInput = document.getElementById("text");
const uploadBtn = document.getElementById("upload");
const templateInput = document.getElementById("template");
const templateHint = document.getElementById("templateHint");
const playbackRateInput = document.getElementById("playbackRate");
const segmentAudioBuffer = new SegmentAudioBuffer();

const TEMPLATE_HINTS = {
  xcash_yue: "中文合同，朗讀為粵語；使用粵語切分和文字處理。",
  xcash_zh: "中文合同，朗讀為普通話；使用普通話切分和文字處理。",
  xcash_en: "英文合同，朗讀為 English；使用英語切分和文字處理。",
};

let contractId = null;
let segs = [];        // [{seg_idx, est_dur_s, cumulative_start_s}]
let totalEst = 0;
let current = 0;
let currentObjectUrl = null;

function applyPlaybackRate() {
  const rate = Number(playbackRateInput.value);
  audio.defaultPlaybackRate = rate;
  audio.playbackRate = rate;
  audio.preservesPitch = true;
}

function useAudioBlob(blob) {
  const previousObjectUrl = currentObjectUrl;
  currentObjectUrl = URL.createObjectURL(blob);
  audio.src = currentObjectUrl;
  if (previousObjectUrl) URL.revokeObjectURL(previousObjectUrl);
  applyPlaybackRate();
}

function updateTemplateHint() {
  templateHint.textContent = TEMPLATE_HINTS[templateInput.value];
  playbackRateInput.value = String(
    preferredPlaybackRate(templateInput.value),
  );
  applyPlaybackRate();
}

templateInput.addEventListener("change", updateTemplateHint);
playbackRateInput.addEventListener("change", applyPlaybackRate);
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
  return segmentAudioBuffer.load(contractId, segIdx);
}

function preloadSegment(segIdx) {
  if (!contractId || segIdx < 0 || segIdx >= segs.length) return;

  const targetContractId = contractId;
  segmentAudioBuffer.preload(targetContractId, segIdx).catch((e) => {
    console.warn(e.message);
  });
}

function preloadAhead(segIdx, count = PRELOAD_AHEAD) {
  for (let k = 1; k <= count; k++) {
    preloadSegment(segIdx + k);
  }
}

async function playFrom(segIdx) {
  current = segIdx;
  statusEl.textContent = `生成/載入 第 ${segIdx + 1}/${segs.length} 段…`;
  try {
    const blob = await loadSegment(segIdx);
    useAudioBlob(blob);
    clauseEl.textContent = `第 ${segIdx + 1}/${segs.length} 段`;
    bar.value = secondsToBar(segs[segIdx].cumulative_start_s);
    await audio.play();
    statusEl.textContent = `播放 第 ${segIdx + 1}/${segs.length} 段`;
    preloadAhead(segIdx);
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
    if (data.template_id && data.template_id !== templateId) {
      throw new Error(
        `模板不一致：前端=${templateId}，後端=${data.template_id}`
      );
    }
    contractId = data.contract_id;
    segs = data.segments;
    totalEst = data.total_est_s;
    bar.disabled = false;
    current = 0;
    segmentAudioBuffer.clear();
    // Request segment 0 plus the next two segments immediately. Only segment 0
    // blocks readiness; the following requests warm the playback buffer in parallel.
    try {
      const firstSegment = loadSegment(0);
      preloadAhead(0, INITIAL_SEGMENT_REQUEST_COUNT - 1);
      const blob = await firstSegment;
      useAudioBlob(blob);
      clauseEl.textContent = `第 1/${segs.length} 段`;
      bar.value = 0;
      const initialRequestCount = Math.min(
        INITIAL_SEGMENT_REQUEST_COUNT,
        segs.length,
      );
      statusEl.textContent = templateId + " · 就緒 · 共 " + segs.length
        + " 段 · 預估 " + totalEst.toFixed(0) + "s(已開始預載前 "
        + initialRequestCount + " 段,按播放即可)";
    } catch (e) {
      statusEl.textContent = `就緒 · 預載第 1 段失敗:${e.message}(可拖動進度條開始)`;
    }
  } catch (e) {
    statusEl.textContent = "上傳失敗:" + e.message;
    uploadBtn.disabled = false;
  }
});
