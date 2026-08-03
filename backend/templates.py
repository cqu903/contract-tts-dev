"""Template and Engine Profile definitions for contract processing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.normalizer import normalize_for_tts
from backend.segmenter import Segment, estimate_duration, split_contract


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
                            engine_provider: Callable[[], object] | None = None
                            ) -> dict[str, TemplateProfile]:
    """Build the currently registered Template profiles.

    Ticket 01 registers the Cantonese profile. Later tickets add Mandarin and
    English profiles without changing the application pipeline.
    """
    engine_profile = EngineProfile(
        id=f"{engine_name}_yue",
        available=engine_name != "bailian" or bool(api_key),
        engine_provider=engine_provider or (lambda: None),
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
            engine_profile=engine_profile,
        )
    }


def canonical_template_id(template_id: str, registry: dict[str, TemplateProfile]) -> str:
    """Return a canonical Template ID or raise ``KeyError`` when unknown."""
    if template_id in registry:
        return template_id
    for profile in registry.values():
        if template_id in profile.aliases:
            return profile.id
    raise KeyError(template_id)
