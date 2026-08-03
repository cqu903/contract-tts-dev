"""Text processing modules selected by Template profiles."""

from .normalizer import normalize_for_tts
from .normalizers import normalize_for_tts_en, normalize_for_tts_zh
from .segmenter import Segment, estimate_duration, split_contract
from .segmenters import (
    estimate_duration_en,
    estimate_duration_zh,
    split_contract_en,
    split_contract_zh,
)

__all__ = [
    "Segment",
    "estimate_duration",
    "estimate_duration_en",
    "estimate_duration_zh",
    "normalize_for_tts",
    "normalize_for_tts_en",
    "normalize_for_tts_zh",
    "split_contract",
    "split_contract_en",
    "split_contract_zh",
]
