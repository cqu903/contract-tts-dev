import asyncio
import json

import httpx
import pytest

from backend.bailian_cosyvoice_client import BailianCosyVoiceClient

OSS_URL = "https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/x.wav"


def test_synth_posts_to_cosyvoice_then_streams_downloaded_bytes():
    """synth: POST SpeechSynthesizer (model/voice/text/auth) -> parse audio url -> stream GET bytes."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["url"] = str(request.url)
            captured["payload"] = json.loads(request.content)
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"output": {"audio": {"url": OSS_URL}}})
        # GET the returned audio url
        return httpx.Response(200, content=b"AUDIOBYTES")

    client = BailianCosyVoiceClient(api_key="sk-test", voice="longjiaxin_v3")

    async def collect():
        return [c async for c in client.synth("你好", transport=httpx.MockTransport(handler))]

    chunks = asyncio.run(collect())

    assert b"".join(chunks) == b"AUDIOBYTES"
    assert captured["url"].endswith("/services/audio/tts/SpeechSynthesizer")
    assert captured["payload"]["model"] == "cosyvoice-v3-flash"
    assert captured["payload"]["input"]["text"] == "你好"
    assert captured["payload"]["input"]["voice"] == "longjiaxin_v3"
    assert captured["payload"]["input"]["format"] == "wav"
    assert captured["auth"] == "Bearer sk-test"


def test_synth_raises_http_status_error_on_engine_failure():
    """Non-2xx from cosyvoice -> httpx.HTTPStatusError (app.py maps this to 502)."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"code":"InvalidParameter","message":"bad voice"}')

    client = BailianCosyVoiceClient(api_key="sk-test")

    async def go():
        async for _ in client.synth("x", transport=httpx.MockTransport(handler)):
            pass

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(go())
