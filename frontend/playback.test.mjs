import assert from "node:assert/strict";
import test from "node:test";

import {
  SegmentAudioBuffer,
  preferredPlaybackRate,
} from "./playback.mjs";


test("a preloaded segment is reused without another network request", async () => {
  const expectedBlob = new Blob(["segment-audio"], { type: "audio/wav" });
  const requestedUrls = [];
  const fetchSegment = async (url) => {
    requestedUrls.push(url);
    return {
      ok: true,
      blob: async () => expectedBlob,
    };
  };
  const buffer = new SegmentAudioBuffer(fetchSegment);

  await buffer.preload("contract-1", 1);
  const loadedBlob = await buffer.load("contract-1", 1);

  assert.equal(loadedBlob, expectedBlob);
  assert.deepEqual(requestedUrls, ["/api/contracts/contract-1/segments/1"]);
});


test("Cantonese defaults to the intermediate playback speed", () => {
  assert.equal(preferredPlaybackRate("xcash_yue"), 1.1);
  assert.equal(preferredPlaybackRate("xcash_zh"), 1.0);
  assert.equal(preferredPlaybackRate("xcash_en"), 1.0);
});
