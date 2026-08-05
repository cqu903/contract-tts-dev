"""Compatibility exports for language-specific segmenters."""

from backend.text.mandarin_segmenter import estimate_duration_zh, split_contract_zh
from backend.text.segmenters import estimate_duration_en, split_contract_en

__all__ = [
    "estimate_duration_en",
    "estimate_duration_zh",
    "split_contract_en",
    "split_contract_zh",
]
