import asyncio
import json

import httpx
import pytest

from backend.bailian_cosyvoice_client import (
    BailianCosyVoiceClient,
    BailianSynthesisError,
)

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


def test_synth_uses_wss_sdk_when_configured(monkeypatch):
    captured = {}

    class FakeSynthesizer:
        last_response = None

        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def call(self, text, timeout_millis):
            captured["text"] = text
            captured["timeout_millis"] = timeout_millis
            return b"WSS-AUDIO"

    monkeypatch.setattr(
        "backend.engines.bailian_cosyvoice_client.SpeechSynthesizer",
        FakeSynthesizer,
    )
    client = BailianCosyVoiceClient(
        api_key="sk-test",
        model="cosyvoice-v3-flash",
        voice="longanyang",
        transport_mode="wss",
        ws_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
        workspace="ws-test",
    )

    async def collect():
        return [chunk async for chunk in client.synth("hello")]

    assert asyncio.run(collect()) == [b"WSS-AUDIO"]
    assert captured["text"] == "hello"
    assert captured["timeout_millis"] == 60_000
    assert captured["kwargs"]["model"] == "cosyvoice-v3-flash"
    assert captured["kwargs"]["voice"] == "longanyang"
    assert captured["kwargs"]["workspace"] == "ws-test"
    assert captured["kwargs"]["url"].startswith("wss://")


def test_synth_reports_wss_service_failure(monkeypatch):
    class FailedSynthesizer:
        last_response = {
            "header": {
                "event": "task-failed",
                "error_code": "Model.AccessDenied",
            }
        }

        def __init__(self, **kwargs):
            pass

        def call(self, text, timeout_millis):
            return None

    monkeypatch.setattr(
        "backend.engines.bailian_cosyvoice_client.SpeechSynthesizer",
        FailedSynthesizer,
    )
    client = BailianCosyVoiceClient(
        api_key="sk-test", transport_mode="wss"
    )

    async def collect():
        return [chunk async for chunk in client.synth("hello")]

    with pytest.raises(BailianSynthesisError, match="Model.AccessDenied"):
        asyncio.run(collect())


@pytest.mark.parametrize("mode", ["websocket", "https", ""])
def test_rejects_unknown_transport_mode(mode):
    with pytest.raises(ValueError, match="BAILIAN_TRANSPORT"):
        BailianCosyVoiceClient(api_key="sk-test", transport_mode=mode)
