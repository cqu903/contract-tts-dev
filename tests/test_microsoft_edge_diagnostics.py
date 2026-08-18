import asyncio
import io
import subprocess
import sys
from pathlib import Path

from backend.audio import AudioFormat
from backend.engines.microsoft_tts import MicrosoftTTSProvider
from scripts.diagnose_microsoft_edge_tts import run_diagnostics


ROOT = Path(__file__).resolve().parent.parent


class FakeDiagnosticDriver:
    audio_format = AudioFormat.MP3
    driver_name = "edge"

    def __init__(self, language, voice, rate, error=None):
        self.language = language
        self.voice = voice
        self.rate = rate
        self.error = error
        self.synthesis_fingerprint = f"fake-edge-{language}"
        self.texts = []

    async def synth(self, text):
        self.texts.append(text)
        if self.error is not None:
            raise self.error
        yield b"ID3" + f":{self.language}:{text}".encode("utf-8")


def _diagnostic_providers(*, failing_language=None):
    voices = {
        "yue": "zh-HK-WanLungNeural",
        "zh": "zh-CN-YunyangNeural",
        "en": "en-HK-SamNeural",
    }
    drivers = {
        language: FakeDiagnosticDriver(
            language,
            voice,
            "+0%",
            error=(
                TimeoutError("Edge timed out")
                if language == failing_language
                else None
            ),
        )
        for language, voice in voices.items()
    }
    return drivers, lambda language: MicrosoftTTSProvider(drivers[language])


def test_operator_can_diagnose_all_microsoft_edge_language_profiles(tmp_path):
    drivers, provider_factory = _diagnostic_providers()
    output = io.StringIO()

    exit_code = asyncio.run(
        run_diagnostics(
            provider_factory=provider_factory,
            output_dir=tmp_path,
            stream=output,
        )
    )

    assert (
        exit_code,
        sorted(path.name for path in tmp_path.glob("*.mp3")),
        {language: driver.texts for language, driver in drivers.items()},
        "测试文本将发送到外部 Microsoft TTS 服务" in output.getvalue(),
        "不读取真实 Contract、缓存或用户数据" in output.getvalue(),
        all(
            f"[{language}] driver=edge voice={driver.voice} rate=+0%"
            in output.getvalue()
            for language, driver in drivers.items()
        ),
    ) == (
        0,
        [
            "microsoft-edge-en.mp3",
            "microsoft-edge-yue.mp3",
            "microsoft-edge-zh.mp3",
        ],
        {
            "yue": ["本合約於今日生效，借款人須按時還款。"],
            "zh": ["本合同自今日起生效，借款人应按时还款。"],
            "en": [
                "This contract takes effect today, and the borrower shall repay on time."
            ],
        },
        True,
        True,
        True,
    )


def test_diagnostic_continues_after_one_language_fails_and_returns_nonzero(
    tmp_path,
):
    drivers, provider_factory = _diagnostic_providers(failing_language="zh")
    output = io.StringIO()

    exit_code = asyncio.run(
        run_diagnostics(
            provider_factory=provider_factory,
            output_dir=tmp_path,
            stream=output,
        )
    )

    assert (
        exit_code,
        sorted(path.name for path in tmp_path.glob("*.mp3")),
        {language: len(driver.texts) for language, driver in drivers.items()},
        "[yue] SUCCESS" in output.getvalue(),
        "[zh] FAILED: Microsoft TTS synthesis failed: Edge timed out"
        in output.getvalue(),
        "[en] SUCCESS" in output.getvalue(),
        "结果：2 成功，1 失败" in output.getvalue(),
    ) == (
        1,
        ["microsoft-edge-en.mp3", "microsoft-edge-yue.mp3"],
        {"yue": 1, "zh": 1, "en": 1},
        True,
        True,
        True,
        True,
    )


def test_generic_microsoft_diagnostic_supports_configured_azure_driver(tmp_path):
    from scripts.diagnose_microsoft_tts import run_diagnostics as run_generic

    drivers, provider_factory = _diagnostic_providers()
    for driver in drivers.values():
        driver.driver_name = "azure"
    output = io.StringIO()

    exit_code = asyncio.run(
        run_generic(
            provider_factory=provider_factory,
            output_dir=tmp_path,
            stream=output,
        )
    )

    assert (
        exit_code,
        sorted(path.name for path in tmp_path.glob("*.mp3")),
        "测试文本将发送到外部 Microsoft TTS 服务" in output.getvalue(),
        all(
            f"[{language}] driver=azure" in output.getvalue()
            for language in drivers
        ),
    ) == (
        0,
        [
            "microsoft-azure-en.mp3",
            "microsoft-azure-yue.mp3",
            "microsoft-azure-zh.mp3",
        ],
        True,
        True,
    )


def test_generic_microsoft_diagnostic_can_run_as_a_script():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "diagnose_microsoft_tts.py"),
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Microsoft TTS" in result.stdout
