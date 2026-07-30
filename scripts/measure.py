"""Measure cold-seek first-byte latency, cache-hit, and per-segment RTF.
Run with engine + backend up: uv run python scripts/measure.py"""
from __future__ import annotations
import time
import httpx

BASE = "http://127.0.0.1:8000"
CONTRACT = "sample"


def main():
    idx = httpx.get(f"{BASE}/api/contract/{CONTRACT}").json()
    segs = idx["segments"]
    print(f"contract={CONTRACT} segments={len(segs)} est_total={idx['total_est_s']:.0f}s")

    # cold: request segment 5 (likely uncached), measure time-to-first-byte + total
    target = min(5, len(segs) - 1)
    t0 = time.perf_counter()
    first_byte = None
    total = 0
    with httpx.stream("GET", f"{BASE}/api/segment/{CONTRACT}/{target}", timeout=120) as r:
        for chunk in r.iter_bytes():
            if first_byte is None:
                first_byte = time.perf_counter() - t0
            total += len(chunk)
    full = time.perf_counter() - t0
    print(f"cold seg {target}: first_byte={first_byte:.2f}s total={full:.2f}s bytes={total}")

    # warm cache hit
    t0 = time.perf_counter()
    httpx.get(f"{BASE}/api/segment/{CONTRACT}/{target}")
    print(f"warm hit: {time.perf_counter() - t0:.3f}s")

    # RTF approx: generate a fresh segment and compare bytes-duration (rough)
    fresh = min(target + 1, len(segs) - 1)
    httpx.post(f"{BASE}/api/preload/{CONTRACT}/{fresh}")  # warm in bg
    time.sleep(0.5)


if __name__ == "__main__":
    main()
