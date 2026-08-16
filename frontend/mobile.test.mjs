import assert from "node:assert/strict";
import test from "node:test";

import {
  splitDocBlocks,
  blockCharOffsets,
  secondsToRatio,
  blockIndexAtRatio,
  segmentAtSeconds,
  nextSpeed,
  SPEED_STEPS,
} from "./mobile.mjs";


test("splitDocBlocks trims lines and drops empties", () => {
  assert.deepEqual(
    splitDocBlocks("  第一條　標的。\n\n\t第二條　價款。 \r\n\r\n"),
    ["第一條　標的。", "第二條　價款。"],
  );
  assert.deepEqual(splitDocBlocks(null), []);
});

test("blockCharOffsets gives cumulative starts counting one separator per block", () => {
  const { offsets, total } = blockCharOffsets(["ab", "cdef", "g"]);
  assert.deepEqual(offsets, [0, 3, 8]);
  assert.equal(total, 9); // "ab|cdef|g"：每塊後補一個分隔、只去最後一個 → 2+1+4+1+1
});

test("blockIndexAtRatio maps ratio to the containing block and clamps at both ends", () => {
  const { offsets, total } = blockCharOffsets(["ab", "cdef", "g"]);
  assert.equal(blockIndexAtRatio(offsets, total, 0), 0);
  assert.equal(blockIndexAtRatio(offsets, total, 0.99), 2);
  assert.equal(blockIndexAtRatio(offsets, total, 1.5), 2); // 越界鉗制
  assert.equal(blockIndexAtRatio(offsets, total, -1), 0);
  // ratio=0.5 → pos=4 → 落在第二塊 [3, 8)
  assert.equal(blockIndexAtRatio(offsets, total, 0.5), 1);
  assert.equal(blockIndexAtRatio([], 0, 0.5), -1);
});

test("secondsToRatio clamps and guards zero duration", () => {
  assert.equal(secondsToRatio(30, 100), 0.3);
  assert.equal(secondsToRatio(-5, 100), 0);
  assert.equal(secondsToRatio(500, 100), 1);
  assert.equal(secondsToRatio(10, 0), 0);
});

test("segmentAtSeconds follows the desktop seek semantics", () => {
  const segs = [
    { seg_idx: 0, est_dur_s: 2.5, cumulative_start_s: 0 },
    { seg_idx: 1, est_dur_s: 2.5, cumulative_start_s: 2.5 },
    { seg_idx: 2, est_dur_s: 5, cumulative_start_s: 5 },
  ];
  assert.equal(segmentAtSeconds(segs, 0), 0);
  assert.equal(segmentAtSeconds(segs, 2.4), 0);
  assert.equal(segmentAtSeconds(segs, 2.5), 1);
  assert.equal(segmentAtSeconds(segs, 7.9), 2);
  assert.equal(segmentAtSeconds(segs, 999), 2); // 越界為最後一段
  assert.equal(segmentAtSeconds([], 1), -1);
});

test("nextSpeed cycles through the steps and recovers unknown values", () => {
  assert.equal(nextSpeed(1.0), 1.1);
  assert.equal(nextSpeed(1.1), 1.25);
  assert.equal(nextSpeed(1.25), 1.0);
  assert.equal(nextSpeed(3), SPEED_STEPS[0]); // 未知值回到第一步
});
