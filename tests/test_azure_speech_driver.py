import asyncio

import pytest

import backend.app as appmod
from backend.audio import AudioFormat
from backend.engines.microsoft_tts import (
    AzureSpeechDriver,
    MicrosoftSynthesisError,
    build_microsoft_provider,
)


async def _collect(stream):
    return b"".join([chunk async for chunk in stream])


class FakeFuture:
    def __init__(self, result):
        self.result = result

    def get(self):
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class FakeSpeechConfig:
    def __init__(self, owner, kwargs):
        self.owner = owner
        self.kwargs = kwargs
        self.speech_synthesis_voice_name = None
        self.output_format = None

    def set_speech_synthesis_output_format(self, output_format):
        self.output_format = output_format


class FakeSpeechSynthesizer:
    def __init__(self, owner, speech_config, audio_config):
        self.owner = owner
        self.speech_config = speech_config
        self.audio_config = audio_config

    def speak_ssml_async(self, ssml):
        self.owner.ssml.append(ssml)
        return FakeFuture(self.owner.result)


class FakeAzureSpeechSDK:
    class ResultReason:
        SynthesizingAudioCompleted = "completed"
        Canceled = "canceled"

    class SpeechSynthesisOutputFormat:
        Audio24Khz48KBitRateMonoMp3 = "24khz-48kbps-mono-mp3"

    def __init__(self, *, result):
        self.result = result
        self.configurations = []
        self.synthesizers = []
        self.ssml = []

    def SpeechConfig(self, **kwargs):
        config = FakeSpeechConfig(self, kwargs)
        self.configurations.append(config)
        return config

    def SpeechSynthesizer(self, *, speech_config, audio_config):
        synthesizer = FakeSpeechSynthesizer(
            self, speech_config, audio_config
        )
        self.synthesizers.append(synthesizer)
        return synthesizer


class FakeSynthesisResult:
    def __init__(self, reason, audio_data=b"", cancellation_details=None):
        self.reason = reason
        self.audio_data = audio_data
        self.cancellation_details = cancellation_details


def test_azure_driver_synthesizes_native_mp3_with_region_voice_and_rate():
    sdk = FakeAzureSpeechSDK(
        result=FakeSynthesisResult("completed", b"ID3azure-mp3")
    )
    provider = build_microsoft_provider(
        driver_name="azure",
        voice="zh-HK-WanLungNeural",
        rate="33.33%",
        azure_subscription_key="secret-key",
        azure_region="eastasia",
        speechsdk_module=sdk,
    )
    audio = asyncio.run(_collect(provider.synth("合約 <A&B>")))

    assert (
        audio,
        provider.audio_format,
        provider.driver.driver_name,
        provider.driver.voice,
        provider.driver.rate,
        sdk.configurations[0].kwargs,
        sdk.configurations[0].speech_synthesis_voice_name,
        sdk.configurations[0].output_format,
        sdk.synthesizers[0].audio_config,
        sdk.ssml,
        "secret-key" in provider.synthesis_fingerprint,
    ) == (
        b"ID3azure-mp3",
        AudioFormat.MP3,
        "azure",
        "zh-HK-WanLungNeural",
        "+33.33%",
        {"subscription": "secret-key", "region": "eastasia"},
        "zh-HK-WanLungNeural",
        "24khz-48kbps-mono-mp3",
        None,
        [
            '<speak version="1.0" '
            'xmlns="http://www.w3.org/2001/10/synthesis" '
            'xml:lang="zh-HK"><voice name="zh-HK-WanLungNeural">'
            '<prosody rate="+33.33%">合約 &lt;A&amp;B&gt;</prosody>'
            "</voice></speak>"
        ],
        False,
    )


def test_azure_driver_supports_https_endpoint_without_key_in_cache_identity():
    sdk = FakeAzureSpeechSDK(
        result=FakeSynthesisResult("completed", b"ID3azure-endpoint")
    )
    configuration = {
        "driver_name": "azure",
        "voice": "en-HK-SamNeural",
        "rate": "+0%",
        "azure_region": "",
        "azure_endpoint": "https://speech.example.test/",
        "speechsdk_module": sdk,
    }
    first = build_microsoft_provider(
        azure_subscription_key="first-secret",
        **configuration,
    )
    rotated = build_microsoft_provider(
        azure_subscription_key="rotated-secret",
        **configuration,
    )

    audio = asyncio.run(_collect(first.synth("Contract text")))

    assert audio == b"ID3azure-endpoint"
    assert sdk.configurations[0].kwargs == {
        "subscription": "first-secret",
        "endpoint": "https://speech.example.test/",
    }
    assert first.synthesis_fingerprint == rotated.synthesis_fingerprint
    assert "first-secret" not in first.synthesis_fingerprint
    assert "rotated-secret" not in rotated.synthesis_fingerprint
    assert "https://speech.example.test/" in first.synthesis_fingerprint


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"azure_subscription_key": ""}, "AZURE_SPEECH_KEY"),
        ({"azure_region": ""}, "AZURE_SPEECH_REGION or AZURE_SPEECH_ENDPOINT"),
        (
            {"azure_region": "", "azure_endpoint": "http://speech.example"},
            "HTTPS URL",
        ),
        ({"voice": " "}, "voice must not be empty"),
        ({"rate": "fast"}, "must be a percentage"),
    ],
)
def test_azure_driver_rejects_invalid_local_configuration(overrides, error):
    configuration = {
        "driver_name": "azure",
        "voice": "zh-HK-WanLungNeural",
        "rate": "+0%",
        "azure_subscription_key": "secret-key",
        "azure_region": "eastasia",
        "azure_endpoint": "",
        "speechsdk_module": object(),
    }
    configuration.update(overrides)

    with pytest.raises(ValueError, match=error):
        build_microsoft_provider(**configuration)


def test_azure_driver_exposes_safe_cancellation_details_as_microsoft_error():
    cancellation = type(
        "CancellationDetails",
        (),
        {
            "reason": "Error",
            "error_details": (
                "AuthenticationFailure: invalid subscription key=secret-key"
            ),
        },
    )()
    sdk = FakeAzureSpeechSDK(
        result=FakeSynthesisResult(
            "canceled", cancellation_details=cancellation
        )
    )
    provider = build_microsoft_provider(
        driver_name="azure",
        voice="en-HK-SamNeural",
        rate="+0%",
        azure_subscription_key="secret-key",
        azure_region="eastasia",
        speechsdk_module=sdk,
    )

    with pytest.raises(
        MicrosoftSynthesisError,
        match=(
            "Azure Speech synthesis canceled: Error; "
            r"AuthenticationFailure: invalid subscription key=\*\*\*"
        ),
    ):
        asyncio.run(_collect(provider.synth("Contract text")))


def test_azure_driver_redacts_subscription_key_from_sdk_exceptions():
    sdk = FakeAzureSpeechSDK(
        result=RuntimeError("request rejected for secret-key")
    )
    provider = build_microsoft_provider(
        driver_name="azure",
        voice="en-HK-SamNeural",
        rate="+0%",
        azure_subscription_key="secret-key",
        azure_region="eastasia",
        speechsdk_module=sdk,
    )

    with pytest.raises(MicrosoftSynthesisError) as raised:
        asyncio.run(_collect(provider.synth("Contract text")))

    assert str(raised.value) == "Azure Speech synthesis failed: request rejected for ***"
    assert "secret-key" not in str(raised.value)


def test_make_engine_builds_azure_driver_from_deployment_configuration(
    monkeypatch,
):
    monkeypatch.setattr(appmod, "MICROSOFT_TTS_DRIVER", "azure")
    monkeypatch.setattr(
        appmod, "AZURE_SPEECH_KEY", "secret-key", raising=False
    )
    monkeypatch.setattr(
        appmod, "AZURE_SPEECH_REGION", "EastAsia", raising=False
    )
    monkeypatch.setattr(appmod, "AZURE_SPEECH_ENDPOINT", "", raising=False)
    monkeypatch.setitem(
        appmod.MICROSOFT_TTS_LANGUAGE_CONFIGS,
        "yue",
        appmod.MicrosoftReadingLanguageConfig(
            "zh-HK-WanLungNeural", "+0%"
        ),
    )

    provider = appmod.make_engine("microsoft", "yue")

    assert (
        isinstance(provider.driver, AzureSpeechDriver),
        provider.driver.driver_name,
        provider.driver.region,
        provider.driver.endpoint,
        provider.driver.voice,
        provider.driver.rate,
        provider.audio_format,
    ) == (
        True,
        "azure",
        "eastasia",
        "",
        "zh-HK-WanLungNeural",
        "+0%",
        AudioFormat.MP3,
    )
