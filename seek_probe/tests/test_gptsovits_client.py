import asyncio
import json
import httpx
from seek_probe.backend.gptsovits_client import GPTSoVITSClient


def test_synth_streams_engine_bytes_and_sends_yue_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, content=b"AUDIOBYTES")

    client = GPTSoVITSClient("http://127.0.0.1:9880",
                             ref_audio_path="/r.wav", prompt_text="參考")

    async def collect():
        return [c async for c in client.synth("你好", transport=httpx.MockTransport(handler))]

    chunks = asyncio.run(collect())
    assert b"".join(chunks) == b"AUDIOBYTES"
    assert captured["url"].endswith("/tts")
    assert captured["payload"]["text"] == "你好"
    assert captured["payload"]["text_lang"] == "yue"
    assert captured["payload"]["media_type"] == "wav"
