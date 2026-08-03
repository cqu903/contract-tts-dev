"""Thin async client over Bailian (DashScope) CosyVoice non-realtime TTS.

Two-step synth: POST SpeechSynthesizer -> JSON carrying an audio url -> stream
the GET of that url. Mirrors GPTSoVITSClient's ``synth(text) -> AsyncIterator[bytes]``
contract so the app layer can swap engines without changes; text normalization
stays at the app layer (shared ``normalizer.py``) — this client receives already
-normalized text, exactly like the local engine.

Endpoint/format: ``POST {base}/api/v1/services/audio/tts/SpeechSynthesizer``
(Beijing region only). Default voice ``longjiaxin_v3`` is a native Cantonese
system voice (粤语/英文).
"""
from __future__ import annotations
from typing import AsyncIterator

import httpx


class BailianCosyVoiceClient:
    def __init__(self, api_key: str, model: str = "cosyvoice-v3-flash",
                 voice: str = "longjiaxin_v3",
                 base_url: str = "https://dashscope.aliyuncs.com",
                 format: str = "wav", sample_rate: int = 24000,
                 timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.base_url = base_url.rstrip("/")
        self.format = format
        self.sample_rate = sample_rate
        self.timeout = timeout

    async def synth(self, text: str,
                    transport: httpx.AsyncBaseTransport | None = None) -> AsyncIterator[bytes]:
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
        # trust_env=False: do NOT route dashscope through HTTP_PROXY (e.g. clash on :7897) -> 502
        async with httpx.AsyncClient(timeout=self.timeout, transport=transport, trust_env=False) as client:
            r = await client.post(
                f"{self.base_url}/api/v1/services/audio/tts/SpeechSynthesizer",
                json=payload, headers=headers,
            )
            r.raise_for_status()
            audio_url = r.json()["output"]["audio"]["url"]
            async with client.stream("GET", audio_url) as ar:
                ar.raise_for_status()
                async for chunk in ar.aiter_bytes():
                    yield chunk
