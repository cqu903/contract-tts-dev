"""Thin async client over GPT-SoVITS api_v2.py /tts. Streams response bytes.

NOTE: streaming_mode=false returns one playable WAV per segment (robust for <audio>).
streaming_mode=true (lower cold-seek latency) is a documented follow-up: its
chunk format varies by version and is not bet-the-spike-on-able here."""
from __future__ import annotations
from typing import AsyncIterator
import httpx
from opencc import OpenCC


class GPTSoVITSClient:
    def __init__(self, base_url: str, ref_audio_path: str, prompt_text: str,
                 text_lang: str = "yue", prompt_lang: str = "yue",
                 fragment_interval: float = 0.3,
                 text_split_method: str = "cut5", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.ref_audio_path = ref_audio_path
        self.prompt_text = prompt_text
        self.text_lang = text_lang
        self.prompt_lang = prompt_lang
        self.fragment_interval = fragment_interval
        self.text_split_method = text_split_method
        self._text_converter = OpenCC("t2s") if text_lang == "zh" else None
        self._prompt_converter = OpenCC("t2s") if prompt_lang == "zh" else None
        self.timeout = timeout

    def prepare_text(self, text: str) -> str:
        """Apply target-language conversion at the engine seam."""
        return self._text_converter.convert(text) if self._text_converter else text

    def prepare_prompt(self, text: str) -> str:
        """Prepare the transcript using the reference audio's language."""
        return self._prompt_converter.convert(text) if self._prompt_converter else text

    async def synth(self, text: str, transport: httpx.AsyncBaseTransport | None = None) -> AsyncIterator[bytes]:
        payload = {
            "text": self.prepare_text(text),
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.prepare_prompt(self.prompt_text),
            "prompt_lang": self.prompt_lang,
            "media_type": "wav",
            "streaming_mode": False,
            "fragment_interval": self.fragment_interval,
            "text_split_method": self.text_split_method,
        }
        # trust_env=False: do NOT route localhost through HTTP_PROXY (e.g. clash on :7897) -> 502
        async with httpx.AsyncClient(timeout=self.timeout, transport=transport, trust_env=False) as client:
            async with client.stream("POST", f"{self.base_url}/tts", json=payload) as r:
                # Streaming responses are not buffered automatically. Read an error body
                # before raising so callers can report GPT-SoVITS' actual validation or
                # inference error instead of masking it with httpx.ResponseNotRead.
                if r.is_error:
                    await r.aread()
                r.raise_for_status()
                async for chunk in r.aiter_bytes():
                    yield chunk
