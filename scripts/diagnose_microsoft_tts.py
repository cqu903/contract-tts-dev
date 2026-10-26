"""Canonical Microsoft TTS diagnostic entrypoint.

The Edge-named module remains as a compatibility alias for existing operators.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.diagnose_microsoft_edge_tts import main, run_diagnostics


__all__ = ["main", "run_diagnostics"]


if __name__ == "__main__":
    raise SystemExit(main())
