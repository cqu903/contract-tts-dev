"""Run one Bailian TTS request with editable text and language settings.

Usage in VS Code/PyCharm:
1. Edit the values in "EDIT HERE" below.
2. Right-click this file and choose "Run Python File in Terminal".
3. The generated WAV is written to verify/ and opened on Windows when
   AUTO_PLAY is enabled.

The script reads the same project .env variables as backend/app.py and prints
the effective model, voice, transport, and output path. It never prints the
API key.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Match backend/app.py: variables already present in the launching environment
# take precedence over values declared in .env.
load_dotenv(ROOT / ".env", override=False)

from backend.engines.bailian_cosyvoice_client import BailianCosyVoiceClient
from backend.text.normalizer import normalize_for_tts
from backend.text.normalizers import normalize_for_tts_en, normalize_for_tts_zh


# ============================ EDIT HERE ============================

# Available values: "zh" (Mandarin), "yue" (Cantonese), "en" (English)
LANGUAGE_PROFILE = "zh"

# Replace this with any text you want to compare.
TEXT = "本協議的洽商地點及完成地點：本貸款協議透過X Wallet應用程式及/或貸款人之網頁洽商。貸款人所有從X Wallet應用程式及/或貸款人之網頁發出或接收的電子紀錄均被視為於貸款人的業務地址（見以上第3段）發出或接收。本貸款協議於貸款人在其業務地址接收到借款人接納貸款條款的確認時完成"

OUTPUT_FILENAME = "bailian_debug_zh.wav"

# Keep enabled to use the production language-specific contract normalization.
# Mandarin Traditional -> Simplified conversion is applied separately inside
# the Bailian TTS engine client, immediately before the remote request.
APPLY_PROJECT_NORMALIZER = True

# On Windows, open the WAV in the default audio player after synthesis.
AUTO_PLAY = True

# ==================================================================


VOICE_ENV_BY_LANGUAGE = {
    "yue": ("BAILIAN_VOICE", "longjiaxin_v3"),
    "zh": ("BAILIAN_VOICE_ZH", "longxiaochun"),
    "en": ("BAILIAN_VOICE_EN", "longanyang"),
}

NORMALIZER_BY_LANGUAGE = {
    "yue": normalize_for_tts,
    "zh": normalize_for_tts_zh,
    "en": normalize_for_tts_en,
}


def build_client(language: str) -> BailianCosyVoiceClient:
    if language not in VOICE_ENV_BY_LANGUAGE:
        choices = ", ".join(VOICE_ENV_BY_LANGUAGE)
        raise ValueError(f"LANGUAGE_PROFILE must be one of: {choices}")

    voice_env, default_voice = VOICE_ENV_BY_LANGUAGE[language]
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key or api_key == "replace-with-your-api-key":
        raise RuntimeError("DASHSCOPE_API_KEY is missing from .env")

    return BailianCosyVoiceClient(
        api_key=api_key,
        model=os.getenv("BAILIAN_MODEL", "cosyvoice-v3-flash"),
        voice=os.getenv(voice_env, default_voice),
        text_lang=language,
        transport_mode=os.getenv("BAILIAN_TRANSPORT", "http").lower(),
        http_base_url=os.getenv(
            "BAILIAN_HTTP_BASE_URL", "https://dashscope.aliyuncs.com"
        ),
        ws_url=os.getenv(
            "BAILIAN_WS_URL",
            "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
        ),
        workspace=os.getenv("BAILIAN_WORKSPACE_ID") or None,
    )


async def synthesize() -> Path:
    source_text = TEXT.strip()
    if not source_text:
        raise ValueError("TEXT cannot be empty")
    normalized_text = (
        NORMALIZER_BY_LANGUAGE[LANGUAGE_PROFILE](source_text)
        if APPLY_PROJECT_NORMALIZER
        else source_text
    )

    client = build_client(LANGUAGE_PROFILE)
    tts_text = client.prepare_text(normalized_text)
    print("Bailian debug request")
    print(f"  language profile : {LANGUAGE_PROFILE}")
    print(f"  model            : {client.model}")
    print(f"  voice            : {client.voice}")
    print(f"  transport        : {client.transport_mode}")
    print(f"  source text      : {source_text}")
    print(f"  normalized text  : {normalized_text}")
    print(f"  TTS text         : {tts_text}")
    print(f"  normalized       : {APPLY_PROJECT_NORMALIZER}")

    chunks = [chunk async for chunk in client.synth(normalized_text)]
    audio = b"".join(chunks)
    if not audio:
        raise RuntimeError("Bailian returned empty audio")

    output_dir = ROOT / "verify"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME
    output_path.write_bytes(audio)

    print(f"  audio bytes      : {len(audio)}")
    print(f"  output           : {output_path}")
    return output_path


def main() -> None:
    output_path = asyncio.run(synthesize())
    if AUTO_PLAY and sys.platform == "win32":
        os.startfile(output_path)  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
