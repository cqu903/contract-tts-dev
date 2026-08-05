"""Compatibility export for the Bailian CosyVoice engine adapter."""

from backend.engines.bailian_cosyvoice_client import (
    BailianCosyVoiceClient,
    BailianSynthesisError,
)

__all__ = ["BailianCosyVoiceClient", "BailianSynthesisError"]
