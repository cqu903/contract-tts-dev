"""Minimal Bailian CosyVoice WebSocket probe for the Singapore region.

This script is intentionally independent from ``backend.app`` so it can
distinguish regional endpoint, API key, model, and voice problems without
contract splitting, normalization, caching, or the HTTP TTS client involved.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import dashscope
from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WS_URL = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
DEFAULT_OUTPUT = ROOT / "uploaded" / "diagnostics" / "bailian_singapore_debug.wav"


def _masked(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}...{value[-4:]} (length={len(value)})"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Debug Bailian CosyVoice through the Singapore WebSocket endpoint."
    )
    parser.add_argument(
        "--url",
        default=os.getenv("BAILIAN_WS_URL", DEFAULT_WS_URL),
        help="Singapore WebSocket endpoint; use the API Host shown by Bailian when available.",
    )
    parser.add_argument(
        "--workspace",
        default=os.getenv("BAILIAN_WORKSPACE_ID") or None,
        help="Optional Bailian workspace ID.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("BAILIAN_MODEL", "cosyvoice-v3-flash"),
    )
    parser.add_argument(
        "--voice",
        default=os.getenv("BAILIAN_VOICE_EN", "longanyang"),
    )
    parser.add_argument(
        "--text",
        default="Hello, this is a Singapore TTS endpoint test.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate and print masked configuration without contacting Bailian.",
    )
    return parser


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    args = _parser().parse_args()
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()

    print("[debug-sg-tts] protocol=WebSocket")
    print(f"[debug-sg-tts] url={args.url}")
    print(f"[debug-sg-tts] workspace={args.workspace or '(not set)'}")
    print(f"[debug-sg-tts] model={args.model}")
    print(f"[debug-sg-tts] voice={args.voice}")
    print(f"[debug-sg-tts] api_key={_masked(api_key) if api_key else '(missing)'}")

    if not api_key:
        print("[debug-sg-tts] configuration error: DASHSCOPE_API_KEY is missing", file=sys.stderr)
        return 2
    if not args.url.startswith("wss://"):
        print(
            "[debug-sg-tts] configuration error: Singapore TTS requires a wss:// endpoint; "
            "the HTTP SpeechSynthesizer endpoint produced 'current user api does not support http call'",
            file=sys.stderr,
        )
        return 2
    if args.check_config:
        print("[debug-sg-tts] configuration check passed; no network request was sent")
        return 0

    dashscope.api_key = api_key
    synthesizer: SpeechSynthesizer | None = None
    try:
        synthesizer = SpeechSynthesizer(
            model=args.model,
            voice=args.voice,
            format=AudioFormat.WAV_24000HZ_MONO_16BIT,
            workspace=args.workspace,
            url=args.url,
        )
        audio = synthesizer.call(args.text, timeout_millis=60_000)
        if not audio:
            raise RuntimeError("the WebSocket call completed without audio bytes")

        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(audio)
        print(f"[debug-sg-tts] request_id={synthesizer.get_last_request_id()}")
        print(f"[debug-sg-tts] audio_bytes={len(audio)}")
        print(f"[debug-sg-tts] output={output}")
        print("[debug-sg-tts] SUCCESS")
        return 0
    except Exception as exc:
        print(f"[debug-sg-tts] FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        if synthesizer is not None:
            print(
                f"[debug-sg-tts] request_id={synthesizer.get_last_request_id()}",
                file=sys.stderr,
            )
            if synthesizer.last_response is not None:
                print(
                    f"[debug-sg-tts] last_response={_json(synthesizer.last_response)}",
                    file=sys.stderr,
                )
        print(
            "[debug-sg-tts] Check that API key, API Host/workspace, model, and voice all belong "
            "to the Singapore region.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
