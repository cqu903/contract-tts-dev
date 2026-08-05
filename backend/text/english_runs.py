"""Internal cleanup for English phrases embedded in Chinese contract text."""
from __future__ import annotations

import re


# Conservative structural abbreviations commonly found in Hong Kong addresses.
# Expanding them gives an English frontend words instead of letter sequences.
_ADDRESS_ABBREVIATIONS = {
    "flt": "Flat",
    "blk": "Block",
    "bldg": "Building",
    "twr": "Tower",
    "rm": "Room",
    "rd": "Road",
    "ave": "Avenue",
    "ln": "Lane",
    "ctr": "Centre",
}
_ADDRESS_SIGNAL = re.compile(
    r"(?:\b(?:FLT|BLK|BLDG|TWR|RM|RD|AVE|LN|CTR)\b|"
    r"(?<![A-Za-z0-9])(?:LG|UG|G|M|\d+)\s*/\s*F(?![A-Za-z]))",
    re.IGNORECASE,
)
_LATIN_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_NON_PROSE_CODES = frozenset({"hkd", "usd", "rmb", "cny"})


def _numeric_ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def normalize_english_run(text: str) -> str:
    """Make an English phrase word-readable without changing its numbers."""
    for abbreviation, expansion in sorted(
        _ADDRESS_ABBREVIATIONS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        text = re.sub(
            rf"(?<![A-Za-z]){re.escape(abbreviation)}\.?(?![A-Za-z])",
            expansion,
            text,
            flags=re.IGNORECASE,
        )

    named_floors = {
        "g": "Ground Floor",
        "lg": "Lower Ground Floor",
        "ug": "Upper Ground Floor",
        "m": "Mezzanine Floor",
    }
    text = re.sub(
        r"(?<![A-Za-z0-9])(LG|UG|G|M)\s*/\s*F(?![A-Za-z])",
        lambda match: named_floors[match.group(1).lower()],
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?<![A-Za-z0-9])(\d+)\s*/?\s*[Ff](?![A-Za-z])",
        lambda match: f"{_numeric_ordinal(int(match.group(1)))} Floor",
        text,
    )
    # Apostrophes are part of a name: QUEEN'S -> Queen's, not Queen'S.
    return re.sub(
        r"\b[A-Z]{2,}(?:'[A-Z]+)?\b",
        lambda match: match.group(0).capitalize(),
        text,
    )


def is_spoken_english_run(text: str) -> bool:
    """Return whether an ASCII run is prose/address text worth protecting.

    Numeric identifiers and currency codes stay on the Mandarin path. Address
    signals, multi-word phrases, and a standalone non-numeric English word stay
    together so number conversion cannot turn their house numbers into Chinese.
    """
    words = _LATIN_WORD.findall(text)
    if not words:
        return False
    # ``39/F`` alone in Chinese context is a Mandarin floor, not an English
    # phrase. It becomes English only when the same run also carries a real
    # address word or structural abbreviation such as FLT/BLK.
    floor_tokens = {"f", "g", "lg", "ug", "m"}
    address_words = [word for word in words if word.lower() not in floor_tokens]
    if _ADDRESS_SIGNAL.search(text) and address_words:
        return True

    meaningful = [word for word in words if word.lower() not in _NON_PROSE_CODES]
    if len(words) >= 2:
        return any(len(word) >= 3 for word in meaningful)
    return (
        len(meaningful) == 1
        and len(meaningful[0]) >= 3
        and not re.search(r"\d", text)
    )
