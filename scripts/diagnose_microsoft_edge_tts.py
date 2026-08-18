"""Run an explicit three-language diagnostic against Microsoft TTS."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Callable, TextIO


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.audio import AudioFormat
from backend.engines.microsoft_tts import MicrosoftTTSProvider


DEFAULT_OUTPUT_DIR = ROOT / ".scratch" / "microsoft-edge-tts" / "diagnostics"
DIAGNOSTIC_TEXTS = {
    "yue": "本合約於今日生效，借款人須按時還款。",
    "zh": "本合同自今日起生效，借款人应按时还款。",
    "en": (
        "This contract takes effect today, and the borrower shall repay on time."
    ),
}
ProviderFactory = Callable[[str], MicrosoftTTSProvider]


def _configured_provider(reading_language: str) -> MicrosoftTTSProvider:
    from backend.app import make_engine

    provider = make_engine("microsoft", reading_language)
    if not isinstance(provider, MicrosoftTTSProvider):
        raise TypeError("configured Microsoft provider has an unexpected type")
    return provider


def _looks_like_mp3(audio: bytes) -> bool:
    if audio.startswith(b"ID3"):
        return True
    return len(audio) >= 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0


async def run_diagnostics(
    *,
    output_dir: Path,
    provider_factory: ProviderFactory = _configured_provider,
    stream: TextIO = sys.stdout,
) -> int:
    """Synthesize fixed, non-sensitive samples and return a process exit code."""
    print(
        "警告：以下固定测试文本将发送到外部 Microsoft TTS 服务；诊断不读取真实 "
        "Contract、缓存或用户数据。",
        file=stream,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    successes = 0
    failures = 0

    for language, text in DIAGNOSTIC_TEXTS.items():
        try:
            provider = provider_factory(language)
            driver = provider.driver
            driver_name = driver.driver_name
            voice = getattr(driver, "voice", "(unknown)")
            rate = getattr(driver, "rate", "(unknown)")
            print(
                f"[{language}] driver={driver_name} voice={voice} rate={rate}",
                file=stream,
            )

            audio = b"".join([chunk async for chunk in provider.synth(text)])
            if (
                provider.audio_format is not AudioFormat.MP3
                or not _looks_like_mp3(audio)
            ):
                raise RuntimeError("diagnostic result is not a non-empty MP3")

            output_path = output_dir / f"microsoft-{driver_name}-{language}.mp3"
            output_path.write_bytes(audio)
            print(
                f"[{language}] SUCCESS bytes={len(audio)} output={output_path}",
                file=stream,
            )
            successes += 1
        except Exception as exc:
            failures += 1
            print(f"[{language}] FAILED: {exc}", file=stream)

    print(f"结果：{successes} 成功，{failures} 失败", file=stream)
    return 1 if failures else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="验证 Microsoft TTS 的粤语、普通话和英语配置。"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="保存三份可试听 MP3 的目录。",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    return asyncio.run(run_diagnostics(output_dir=output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
