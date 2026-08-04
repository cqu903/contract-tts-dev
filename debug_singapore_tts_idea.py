"""IDEA/PyCharm 里右键 Run 即可调试百炼新加坡 TTS。

使用前：
1. IDEA 的 Python Interpreter 选择项目的 .venv/Scripts/python.exe。
2. 项目根目录 .env 中填写 DASHSCOPE_API_KEY。
3. 修改下面的 DEBUG 配置，然后直接运行本文件。
"""

from __future__ import annotations

import os
from pathlib import Path

import dashscope
from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer
from dotenv import load_dotenv


# ==================== DEBUG 配置：通常只改这里 ====================
WS_URL = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
WORKSPACE_ID: str | None = None
MODEL = "cosyvoice-v3-flash"
VOICE = "longanyang"
TEXT = "Hello, this is a Singapore TTS endpoint test."
OUTPUT_FILE = "uploaded/diagnostics/bailian_singapore_idea_debug.wav"
# ================================================================


ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(".env 中缺少 DASHSCOPE_API_KEY")

    print("[Singapore TTS] 开始调试")
    print(f"endpoint : {WS_URL}")
    print(f"workspace: {WORKSPACE_ID or '(未设置)'}")
    print(f"model    : {MODEL}")
    print(f"voice    : {VOICE}")
    print(f"text     : {TEXT}")

    dashscope.api_key = api_key
    synthesizer = SpeechSynthesizer(
        model=MODEL,
        voice=VOICE,
        format=AudioFormat.WAV_24000HZ_MONO_16BIT,
        workspace=WORKSPACE_ID,
        url=WS_URL,
    )

    try:
        audio = synthesizer.call(TEXT, timeout_millis=60_000)
        if not audio:
            raise RuntimeError("服务端未返回音频数据")

        output = Path(OUTPUT_FILE)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(audio)

        print(f"request_id: {synthesizer.get_last_request_id()}")
        print(f"audio     : {len(audio)} bytes")
        print(f"output    : {output}")
        print("[Singapore TTS] 合成成功")
    except Exception:
        print(f"request_id   : {synthesizer.get_last_request_id()}")
        print(f"last_response: {synthesizer.last_response}")
        raise


if __name__ == "__main__":
    main()
