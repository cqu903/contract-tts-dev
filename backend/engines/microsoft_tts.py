"""Stable Microsoft TTS Provider with replaceable synthesis Drivers."""
from __future__ import annotations

import json
import re
from importlib.metadata import PackageNotFoundError, version
from typing import AsyncIterator, Callable, Protocol

from backend.audio import AudioFormat


EDGE_ADAPTER_VERSION = "1"
_EDGE_RATE_PATTERN = re.compile(r"^(?P<sign>[+-]?)(?P<amount>\d+)%$")


class MicrosoftSynthesisError(RuntimeError):
    """A Microsoft Driver failed before producing a complete audio artifact."""


class MicrosoftTTSDriver(Protocol):
    """Internal Driver contract hidden behind the stable Microsoft Provider."""

    audio_format: AudioFormat
    synthesis_fingerprint: str

    def synth(self, text: str) -> AsyncIterator[bytes]: ...


def normalize_edge_rate(rate: str) -> str:
    """Return Edge rate as a signed integer percentage."""
    match = _EDGE_RATE_PATTERN.fullmatch((rate or "").strip())
    if match is None:
        raise ValueError("Microsoft Edge TTS rate must be an integer percentage")
    amount = int(match.group("amount"))
    if amount == 0:
        return "+0%"
    sign = "-" if match.group("sign") == "-" else "+"
    return f"{sign}{amount}%"


def _edge_tts_version() -> str:
    try:
        return version("edge-tts")
    except PackageNotFoundError:
        return "unknown"


def _default_communicate_factory(*args, **kwargs):
    from edge_tts import Communicate

    return Communicate(*args, **kwargs)


class EdgeTTSDriver:
    """Current Microsoft Driver implemented with the ``edge-tts`` client."""

    audio_format = AudioFormat.MP3

    def __init__(
        self,
        *,
        voice: str,
        rate: str,
        communicate_factory: Callable[..., object] | None = None,
    ):
        voice = (voice or "").strip()
        if not voice:
            raise ValueError("Microsoft Edge TTS voice must not be empty")
        self.voice = voice
        self.rate = normalize_edge_rate(rate)
        self._communicate_factory = (
            communicate_factory or _default_communicate_factory
        )
        self.synthesis_fingerprint = json.dumps(
            {
                "adapter": f"microsoft-edge-v{EDGE_ADAPTER_VERSION}",
                "driver": "edge",
                "edge_tts": _edge_tts_version(),
                "format": self.audio_format.format_id,
                "rate": self.rate,
                "voice": self.voice,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    async def synth(self, text: str) -> AsyncIterator[bytes]:
        produced_audio = False
        try:
            communication = self._communicate_factory(
                text,
                voice=self.voice,
                rate=self.rate,
            )
            async for event in communication.stream():
                if not isinstance(event, dict) or event.get("type") != "audio":
                    continue
                data = event.get("data")
                if not isinstance(data, bytes):
                    raise MicrosoftSynthesisError(
                        "Edge TTS returned an invalid audio event"
                    )
                if data:
                    produced_audio = True
                    yield data
        except MicrosoftSynthesisError:
            raise
        except Exception as exc:
            raise MicrosoftSynthesisError(
                f"Edge TTS synthesis failed: {exc}"
            ) from exc
        if not produced_audio:
            raise MicrosoftSynthesisError("Edge TTS returned no audio")


class MicrosoftTTSProvider:
    """Stable Engine Provider delegating synthesis to a configured Driver."""

    def __init__(self, driver: MicrosoftTTSDriver):
        self.driver = driver
        self.audio_format = driver.audio_format
        self.synthesis_fingerprint = driver.synthesis_fingerprint

    async def synth(self, text: str) -> AsyncIterator[bytes]:
        produced_audio = False
        try:
            async for chunk in self.driver.synth(text):
                if not isinstance(chunk, bytes):
                    raise MicrosoftSynthesisError(
                        "Microsoft TTS Driver returned an invalid audio chunk"
                    )
                if chunk:
                    produced_audio = True
                    yield chunk
        except MicrosoftSynthesisError:
            raise
        except Exception as exc:
            raise MicrosoftSynthesisError(
                f"Microsoft TTS synthesis failed: {exc}"
            ) from exc
        if not produced_audio:
            raise MicrosoftSynthesisError("Microsoft TTS Driver returned no audio")


def build_microsoft_provider(
    *,
    driver_name: str,
    voice: str,
    rate: str,
    communicate_factory: Callable[..., object] | None = None,
) -> MicrosoftTTSProvider:
    """Validate local Microsoft configuration and construct its Provider."""
    driver_name = (driver_name or "").strip().lower()
    if not driver_name:
        raise ValueError(
            "MICROSOFT_TTS_DRIVER must be explicitly configured when using microsoft"
        )
    if driver_name != "edge":
        raise ValueError(
            f"unsupported Microsoft TTS driver {driver_name!r}; expected: edge"
        )
    return MicrosoftTTSProvider(
        EdgeTTSDriver(
            voice=voice,
            rate=rate,
            communicate_factory=communicate_factory,
        )
    )
