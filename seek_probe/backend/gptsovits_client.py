"""Thin async client over GPT-SoVITS api_v2.py /tts. Streams response bytes.

NOTE: streaming_mode=false returns one playable WAV per segment (robust for <audio>).
streaming_mode=true (lower cold-seek latency) is a documented follow-up: its
chunk format varies by version and is not bet-the-spike-on-able here."""
from __future__ import annotations
from typing import AsyncIterator
import httpx


class GPTSoVITSClient:
    def __init__(self, base_url: str, ref_audio_path: str, prompt_text: str,
                 text_lang: str = "yue", prompt_lang: str = "yue", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.ref_audio_path = ref_audio_path
        self.prompt_text = prompt_text
        self.text_lang = text_lang
        self.prompt_lang = prompt_lang
        self.timeout = timeout

    async def synth(self, text: str, transport: httpx.AsyncBaseTransport | None = None) -> AsyncIterator[bytes]:
        payload = {
            "text": text,
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "media_type": "wav",
            "streaming_mode": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout, transport=transport) as client:
            async with client.stream("POST", f"{self.base_url}/tts", json=payload) as r:
                r.raise_for_status()
                async for chunk in r.aiter_bytes():
                    yield chunk
