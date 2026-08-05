import asyncio
import json
import httpx
import pytest
from backend.gptsovits_client import GPTSoVITSClient


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


def test_synth_buffers_engine_error_body_before_raising():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "reference audio not found"})

    client = GPTSoVITSClient(
        "http://127.0.0.1:9880",
        ref_audio_path="/missing.wav",
        prompt_text="reference",
    )

    async def collect():
        return [
            chunk
            async for chunk in client.synth(
                "hello", transport=httpx.MockTransport(handler)
            )
        ]

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        asyncio.run(collect())

    assert exc_info.value.response.json() == {
        "message": "reference audio not found"
    }


def test_mandarin_synth_converts_script_and_keeps_reference_language_separate():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, content=b"MANDARIN")

    client = GPTSoVITSClient(
        "http://127.0.0.1:9880",
        ref_audio_path="/cantonese.wav",
        prompt_text="尋日我同阿媽去咗街市。",
        text_lang="zh",
        prompt_lang="yue",
    )

    async def collect():
        return [
            chunk
            async for chunk in client.synth(
                "貸款人應於三十日內還款。",
                transport=httpx.MockTransport(handler),
            )
        ]

    assert b"".join(asyncio.run(collect())) == b"MANDARIN"
    assert captured["payload"]["text"] == "贷款人应于三十日内还款。"
    assert captured["payload"]["text_lang"] == "zh"
    assert captured["payload"]["prompt_lang"] == "yue"
