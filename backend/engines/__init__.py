"""TTS engine adapters implementing the shared ``synth`` interface."""

from .bailian_cosyvoice_client import BailianCosyVoiceClient
from .gptsovits_client import GPTSoVITSClient

__all__ = ["BailianCosyVoiceClient", "GPTSoVITSClient"]
