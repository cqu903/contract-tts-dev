"""Compatibility exports for language-specific segmenters."""

from backend.text.segmenters import (
    estimate_duration_en,
    estimate_duration_zh,
    split_contract_en,
    split_contract_zh,
)

__all__ = [
    "estimate_duration_en",
    "estimate_duration_zh",
    "split_contract_en",
    "split_contract_zh",
]
