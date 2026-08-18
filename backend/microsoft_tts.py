"""Compatibility import for the Microsoft TTS Provider and Drivers."""

from backend.engines.microsoft_tts import (
    AzureSpeechDriver,
    EdgeTTSDriver,
    MicrosoftSynthesisError,
    MicrosoftTTSProvider,
    build_microsoft_provider,
    normalize_edge_rate,
)

__all__ = [
    "AzureSpeechDriver",
    "EdgeTTSDriver",
    "MicrosoftSynthesisError",
    "MicrosoftTTSProvider",
    "build_microsoft_provider",
    "normalize_edge_rate",
]
