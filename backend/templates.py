"""Template and Engine Profile definitions for contract processing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.normalizer import normalize_for_tts
from backend.segmenter import Segment, estimate_duration, split_contract
from backend.normalizers import normalize_for_tts_en, normalize_for_tts_zh
from backend.segmenters import estimate_duration_en, estimate_duration_zh, split_contract_en, split_contract_zh


@dataclass(frozen=True)
class EngineProfile:
    """A named TTS configuration and its cache namespace."""

    id: str
    cache_version: str = "v1"
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
                            engine_provider: Callable[[], object] | None = None,
                            engine_providers: dict[str, Callable[[], object]] | None = None,
                            cache_versions: dict[str, str] | None = None,
                            ) -> dict[str, TemplateProfile]:
    """Build the currently registered Template profiles.

    Each public Template is registered here; language-specific profiles share
    the application pipeline while keeping their rules and cache identities
    independent.
    """
    providers = engine_providers or {}
    versions = cache_versions or {}
    yue_provider = engine_provider or providers.get("yue") or (lambda: None)
    yue_profile = EngineProfile(
        id=f"{engine_name}_yue",
        cache_version=versions.get("yue", "v1"),
        available=engine_name != "bailian" or bool(api_key),
        engine_provider=yue_provider,
    )
    zh_profile = EngineProfile(
        id=f"{engine_name}_zh",
        cache_version=versions.get("zh", "v1"),
        available=engine_name == "bailian" and bool(api_key),
        engine_provider=providers.get("zh", yue_provider),
    )
    en_profile = EngineProfile(
        id=f"{engine_name}_en",
        cache_version=versions.get("en", "v1"),
        available=engine_name == "bailian" and bool(api_key),
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
