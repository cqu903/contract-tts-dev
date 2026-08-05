"""Bailian CosyVoice adapter with configurable HTTP and WebSocket transports.

Both transports implement the same ``synth(text) -> AsyncIterator[bytes]``
interface. HTTP uses the legacy SpeechSynthesizer endpoint and downloads the
returned audio URL. WSS uses DashScope's CosyVoice SDK, which is required by
the Singapore region. General contract normalization remains in the
application layer; engine-specific Mandarin script conversion happens here at
the final TTS boundary.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Literal

import dashscope
import httpx
from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer
from opencc import OpenCC


BailianTransport = Literal["http", "wss"]


class BailianSynthesisError(RuntimeError):
    """Bailian accepted the connection but failed to synthesize audio."""


class BailianCosyVoiceClient:
    def __init__(
        self,
        api_key: str,
        model: str = "cosyvoice-v3-flash",
        voice: str = "longjiaxin_v3",
        text_lang: str | None = None,
        transport_mode: BailianTransport = "http",
        http_base_url: str = "https://dashscope.aliyuncs.com",
        ws_url: str = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
        workspace: str | None = None,
        format: str = "wav",
        sample_rate: int = 24000,
        timeout: float = 60.0,
    ):
        if transport_mode not in {"http", "wss"}:
            raise ValueError("BAILIAN_TRANSPORT must be 'http' or 'wss'")
        if transport_mode == "wss" and not ws_url.startswith("wss://"):
            raise ValueError("BAILIAN_WS_URL must start with wss://")
        if text_lang not in {None, "zh", "yue", "en"}:
            raise ValueError("text_lang must be one of: zh, yue, en")

        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.text_lang = text_lang
        self._traditional_to_simplified = OpenCC("t2s") if text_lang == "zh" else None
        self.transport_mode = transport_mode
        self.http_base_url = http_base_url.rstrip("/")
        self.ws_url = ws_url
        self.workspace = workspace or None
        self.format = format
        self.sample_rate = sample_rate
        self.timeout = timeout

    def prepare_text(self, text: str) -> str:
        """Apply language-specific conversion immediately before TTS."""
        if self._traditional_to_simplified is None:
            return text
        return self._traditional_to_simplified.convert(text)

    async def synth(
        self, text: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> AsyncIterator[bytes]:
        text = self.prepare_text(text)
        if self.transport_mode == "wss":
            audio = await asyncio.to_thread(self._synth_wss, text)
            yield audio
            return

        async for chunk in self._synth_http(text, transport):
            yield chunk

    async def _synth_http(
        self, text: str, transport: httpx.AsyncBaseTransport | None
    ) -> AsyncIterator[bytes]:
        payload = {
            "model": self.model,
            "input": {
                "text": text,
                "voice": self.voice,
                "format": self.format,
                "sample_rate": self.sample_rate,
            },
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        # Do not route DashScope through HTTP_PROXY (for example Clash on :7897).
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=transport, trust_env=False
        ) as client:
            response = await client.post(
                f"{self.http_base_url}/api/v1/services/audio/tts/SpeechSynthesizer",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            audio_url = response.json()["output"]["audio"]["url"]
            async with client.stream("GET", audio_url) as audio_response:
                audio_response.raise_for_status()
                async for chunk in audio_response.aiter_bytes():
                    yield chunk

    def _synth_wss(self, text: str) -> bytes:
        if self.format != "wav" or self.sample_rate != 24000:
            raise ValueError(
                "WSS transport currently requires format=wav and sample_rate=24000"
            )

        # The DashScope SDK reads the key from this process-global setting. All
        # language profiles in one app instance intentionally share one key.
        dashscope.api_key = self.api_key
        synthesizer = SpeechSynthesizer(
            model=self.model,
            voice=self.voice,
            format=AudioFormat.WAV_24000HZ_MONO_16BIT,
            workspace=self.workspace,
            url=self.ws_url,
        )
        try:
            audio = synthesizer.call(text, timeout_millis=int(self.timeout * 1000))
        except Exception as exc:
            response = synthesizer.last_response
            detail = f"; response={response}" if response is not None else ""
            raise BailianSynthesisError(
                f"Bailian WSS synthesis failed: {exc}{detail}"
            ) from exc
        if not audio:
            raise BailianSynthesisError(
                f"Bailian WSS returned no audio; response={synthesizer.last_response}"
            )
        return audio
