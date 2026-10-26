"""Stable Microsoft TTS Provider with replaceable synthesis Drivers."""
from __future__ import annotations

import asyncio
import json
import re
from importlib.metadata import PackageNotFoundError, version
from typing import AsyncIterator, Callable, Protocol
from urllib.parse import urlparse
from xml.sax.saxutils import escape, quoteattr

from backend.audio import AudioFormat


EDGE_ADAPTER_VERSION = "1"
AZURE_ADAPTER_VERSION = "1"
_EDGE_RATE_PATTERN = re.compile(r"^(?P<sign>[+-]?)(?P<amount>\d+)%$")
_AZURE_RATE_PATTERN = re.compile(
    r"^(?P<sign>[+-]?)(?P<amount>\d+(?:\.\d+)?)%$"
)


class MicrosoftSynthesisError(RuntimeError):
    """A Microsoft Driver failed before producing a complete audio artifact."""


class MicrosoftTTSDriver(Protocol):
    """Internal Driver contract hidden behind the stable Microsoft Provider."""

    driver_name: str
    audio_format: AudioFormat
    synthesis_fingerprint: str

    def synth(self, text: str) -> AsyncIterator[bytes]: ...


def normalize_edge_rate(rate: str) -> str:
    """Return an Edge rate as a signed integer percentage."""
    match = _EDGE_RATE_PATTERN.fullmatch((rate or "").strip())
    if match is None:
        raise ValueError("Microsoft Edge TTS rate must be an integer percentage")
    amount = int(match.group("amount"))
    if amount == 0:
        return "+0%"
    sign = "-" if match.group("sign") == "-" else "+"
    return f"{sign}{amount}%"


def normalize_azure_rate(rate: str) -> str:
    """Return an Azure SSML rate as a signed percentage, including decimals."""
    match = _AZURE_RATE_PATTERN.fullmatch((rate or "").strip())
    if match is None:
        raise ValueError(
            "Microsoft Azure Speech rate must be a percentage"
        )
    amount = match.group("amount")
    if not amount.replace(".", "").strip("0"):
        return "+0%"
    sign = "-" if match.group("sign") == "-" else "+"
    return f"{sign}{amount}%"


def _edge_tts_version() -> str:
    try:
        return version("edge-tts")
    except PackageNotFoundError:
        return "unknown"


def _azure_speech_version() -> str:
    try:
        return version("azure-cognitiveservices-speech")
    except PackageNotFoundError:
        return "unknown"


def _default_communicate_factory(*args, **kwargs):
    from edge_tts import Communicate

    return Communicate(*args, **kwargs)


def _default_speechsdk_module():
    import azure.cognitiveservices.speech as speechsdk

    return speechsdk


class EdgeTTSDriver:
    """Current Microsoft Driver implemented with the ``edge-tts`` client."""

    driver_name = "edge"
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


class AzureSpeechDriver:
    """Official Azure Speech SDK Driver behind the Microsoft Provider."""

    driver_name = "azure"
    audio_format = AudioFormat.MP3

    def __init__(
        self,
        *,
        subscription_key: str,
        region: str,
        endpoint: str,
        voice: str,
        rate: str,
        speechsdk_module=None,
    ):
        self._subscription_key = (subscription_key or "").strip()
        self.region = (region or "").strip().lower()
        self.endpoint = (endpoint or "").strip()
        self.voice = (voice or "").strip()
        if not self._subscription_key:
            raise ValueError(
                "AZURE_SPEECH_KEY must be configured when using the azure driver"
            )
        if not self.region and not self.endpoint:
            raise ValueError(
                "AZURE_SPEECH_REGION or AZURE_SPEECH_ENDPOINT must be configured "
                "when using the azure driver"
            )
        if self.endpoint:
            parsed_endpoint = urlparse(self.endpoint)
            if (
                parsed_endpoint.scheme.lower() != "https"
                or not parsed_endpoint.netloc
                or parsed_endpoint.username
                or parsed_endpoint.password
            ):
                raise ValueError("AZURE_SPEECH_ENDPOINT must be an HTTPS URL")
        if not self.voice:
            raise ValueError("Microsoft Azure Speech voice must not be empty")
        self.rate = normalize_azure_rate(rate)
        self._speechsdk = speechsdk_module
        self.synthesis_fingerprint = json.dumps(
            {
                "adapter": f"microsoft-azure-v{AZURE_ADAPTER_VERSION}",
                "azure_speech": _azure_speech_version(),
                "driver": self.driver_name,
                "endpoint": self.endpoint,
                "format": self.audio_format.format_id,
                "rate": self.rate,
                "region": self.region,
                "voice": self.voice,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _ssml(self, text: str) -> str:
        xml_language = "-".join(self.voice.split("-")[:2])
        return (
            '<speak version="1.0" '
            'xmlns="http://www.w3.org/2001/10/synthesis" '
            f"xml:lang={quoteattr(xml_language)}>"
            f"<voice name={quoteattr(self.voice)}>"
            f"<prosody rate={quoteattr(self.rate)}>{escape(text)}</prosody>"
            "</voice></speak>"
        )

    def _redact(self, detail: object) -> str:
        return str(detail).replace(self._subscription_key, "***")

    def _synthesize(self, text: str) -> bytes:
        speechsdk = self._speechsdk or _default_speechsdk_module()
        if self.endpoint:
            speech_config = speechsdk.SpeechConfig(
                subscription=self._subscription_key,
                endpoint=self.endpoint,
            )
        else:
            speech_config = speechsdk.SpeechConfig(
                subscription=self._subscription_key,
                region=self.region,
            )
        speech_config.speech_synthesis_voice_name = self.voice
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
        )
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=None,
        )
        result = synthesizer.speak_ssml_async(self._ssml(text)).get()
        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            reason = getattr(cancellation, "reason", "unknown")
            details = self._redact(
                getattr(cancellation, "error_details", "")
            )
            suffix = f"; {details}" if details else ""
            raise MicrosoftSynthesisError(
                f"Azure Speech synthesis canceled: {reason}{suffix}"
            )
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise MicrosoftSynthesisError("Azure Speech synthesis did not complete")
        return result.audio_data

    async def synth(self, text: str) -> AsyncIterator[bytes]:
        try:
            audio = await asyncio.to_thread(self._synthesize, text)
        except MicrosoftSynthesisError:
            raise
        except Exception as exc:
            raise MicrosoftSynthesisError(
                f"Azure Speech synthesis failed: {self._redact(exc)}"
            ) from None
        if not isinstance(audio, bytes) or not audio:
            raise MicrosoftSynthesisError("Azure Speech returned no audio")
        yield audio


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
    azure_subscription_key: str = "",
    azure_region: str = "",
    azure_endpoint: str = "",
    speechsdk_module=None,
) -> MicrosoftTTSProvider:
    """Validate local Microsoft configuration and construct its Provider."""
    driver_name = (driver_name or "").strip().lower()
    if not driver_name:
        raise ValueError(
            "MICROSOFT_TTS_DRIVER must be explicitly configured when using microsoft"
        )
    if driver_name == "azure":
        return MicrosoftTTSProvider(
            AzureSpeechDriver(
                subscription_key=azure_subscription_key,
                region=azure_region,
                endpoint=azure_endpoint,
                voice=voice,
                rate=rate,
                speechsdk_module=speechsdk_module,
            )
        )
    if driver_name != "edge":
        raise ValueError(
            f"unsupported Microsoft TTS driver {driver_name!r}; expected: edge or azure"
        )
    return MicrosoftTTSProvider(
        EdgeTTSDriver(
            voice=voice,
            rate=rate,
            communicate_factory=communicate_factory,
        )
    )
