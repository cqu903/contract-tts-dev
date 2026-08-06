"""Template and Engine Profile definitions for contract processing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.text.normalizer import normalize_for_tts
from backend.text.segmenter import Segment, estimate_duration, split_contract
from backend.text.normalizers import normalize_for_tts_en, normalize_for_tts_zh
from backend.text.mandarin_segmenter import estimate_duration_zh, split_contract_zh
from backend.text.segmenters import estimate_duration_en, split_contract_en


_ENGINE_ALIASES = {
    "bailian": "bailian",
    "cosyvoice": "bailian",
    "gptsovits": "gptsovits",
    "microsoft": "microsoft",
}
_READING_LANGUAGES = ("yue", "zh", "en")


def canonical_engine_name(engine_name: str) -> str:
    """Resolve a configured engine name to its adapter identity."""
    normalized = (engine_name or "").strip().lower()
    try:
        return _ENGINE_ALIASES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(_ENGINE_ALIASES))
        raise ValueError(
            f"unsupported TTS engine {engine_name!r}; expected one of: {supported}"
        ) from exc


@dataclass(frozen=True)
class EngineProfile:
    """A named TTS configuration and its cache namespace."""

    id: str
    cache_version: str = "v1"
    synthesis_fingerprint: str = "audio-artifact-v1"
    available: bool = True
    engine_provider: Callable[[], object] = lambda: None


@dataclass(frozen=True)
class TemplateProfile:
    """Complete language-isolated processing rules for one Template."""

    id: str
    aliases: tuple[str, ...]
    contract_language: str
    reading_language: str
    splitter: Callable[[str], list[Segment]]
    duration_estimator: Callable[[str], float]
    normalizer: Callable[[str], str]
    engine_profile: EngineProfile


def build_template_registry(*, engine_name: str, api_key: str = "",
                            engine_names: dict[str, str] | None = None,
                            engine_provider: Callable[[], object] | None = None,
                            engine_providers: dict[str, Callable[[], object]] | None = None,
                            cache_versions: dict[str, str] | None = None,
                            synthesis_fingerprints: dict[str, str] | None = None,
                            ) -> dict[str, TemplateProfile]:
    """Build the currently registered Template profiles.

    Each public Template is registered here; language-specific profiles share
    the application pipeline while keeping their rules and cache identities
    independent.
    """
    providers = engine_providers or {}
    versions = cache_versions or {}
    fingerprints = synthesis_fingerprints or {}
    default_engine = canonical_engine_name(engine_name)
    configured_engines = engine_names or {}
    selected_engines = {
        language: canonical_engine_name(
            configured_engines.get(language, default_engine)
        )
        for language in _READING_LANGUAGES
    }

    def is_available(language: str) -> bool:
        selected = selected_engines[language]
        return (
            selected == "gptsovits"
            or (selected == "bailian" and bool(api_key))
            or (selected == "microsoft" and language == "yue")
        )

    yue_provider = engine_provider or providers.get("yue") or (lambda: None)
    yue_profile = EngineProfile(
        id=f"{selected_engines['yue']}_yue",
        cache_version=versions.get("yue", "v1"),
        synthesis_fingerprint=fingerprints.get("yue", "audio-artifact-v1"),
        available=is_available("yue"),
        engine_provider=yue_provider,
    )
    zh_profile = EngineProfile(
        id=f"{selected_engines['zh']}_zh",
        cache_version=versions.get("zh", "v1"),
        synthesis_fingerprint=fingerprints.get("zh", "audio-artifact-v1"),
        available=is_available("zh"),
        engine_provider=providers.get("zh", yue_provider),
    )
    en_profile = EngineProfile(
        id=f"{selected_engines['en']}_en",
        cache_version=versions.get("en", "v1"),
        synthesis_fingerprint=fingerprints.get("en", "audio-artifact-v1"),
        available=is_available("en"),
        engine_provider=providers.get("en", yue_provider),
    )
    return {
        "xcash_yue": TemplateProfile(
            id="xcash_yue",
            aliases=("xcash",),
            contract_language="zh",
            reading_language="yue",
            splitter=split_contract,
            duration_estimator=estimate_duration,
            normalizer=normalize_for_tts,
            engine_profile=yue_profile,
        ),
        "xcash_zh": TemplateProfile(
            id="xcash_zh",
            aliases=(),
            contract_language="zh",
            reading_language="zh",
            splitter=split_contract_zh,
            duration_estimator=estimate_duration_zh,
            normalizer=normalize_for_tts_zh,
            engine_profile=zh_profile,
        ),
        "xcash_en": TemplateProfile(
            id="xcash_en",
            aliases=(),
            contract_language="en",
            reading_language="en",
            splitter=split_contract_en,
            duration_estimator=estimate_duration_en,
            normalizer=normalize_for_tts_en,
            engine_profile=en_profile,
        ),
    }


def canonical_template_id(template_id: str, registry: dict[str, TemplateProfile]) -> str:
    """Return a canonical Template ID or raise ``KeyError`` when unknown."""
    if template_id in registry:
        return template_id
    for profile in registry.values():
        if template_id in profile.aliases:
            return profile.id
    raise KeyError(template_id)
