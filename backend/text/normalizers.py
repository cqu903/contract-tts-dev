"""Template-specific text normalization for Mandarin and English TTS."""
from __future__ import annotations

import re
from datetime import date

from cn2an import an2cn

from .cn_numbers import digits_to_cn, number_to_cn


def normalize_for_tts_zh(text: str) -> str:
    """Normalize Mandarin reading cues while preserving the original script."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "")
    text = re.sub(r"(?:HK\$|HKD)\s*", "港币", text, flags=re.IGNORECASE)

    def date_repl(match: re.Match[str]) -> str:
        year, month, day = match.groups()
        return f"{digits_to_cn(year)}年{an2cn(str(int(month)))}月{an2cn(str(int(day)))}日"

    text = re.sub(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_repl, text)
    text = re.sub(
        r"(\d{1,2})/(\d{1,2})/(\d{4})",
        lambda m: f"{digits_to_cn(m.group(3))}年{an2cn(str(int(m.group(2))))}月{an2cn(str(int(m.group(1))))}日",
        text,
    )
    # Percentages must be handled before the generic number pass.
    text = re.sub(r"(\d[\d,]*(?:\.\d+)?)\s*%", lambda m: f"百分之{number_to_cn(m.group(1))}", text)
    # Times and separator-delimited identifiers (telephone/account/contract
    # numbers) are read digit-by-digit rather than as cardinal quantities.
    text = re.sub(
        r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)",
        lambda m: f"{an2cn(str(int(m.group(1))))}点{an2cn(str(int(m.group(2))))}分",
        text,
    )
    text = re.sub(
        r"(?<!\d)\d+(?:[-/ ]\d+)+(?!\d)",
        lambda m: digits_to_cn(re.sub(r"\D", "", m.group(0))),
        text,
    )
    # Alphanumeric contract references retain their Latin prefix while the
    # numeric suffix is spoken one digit at a time.
    text = re.sub(
        r"\b([A-Za-z]+[-/]?)(\d{2,})\b",
        lambda m: m.group(1) + digits_to_cn(m.group(2)),
        text,
    )
    text = re.sub(r"(?<![\d,])\d{6,}(?![\d,])", lambda m: digits_to_cn(m.group(0)), text)
    text = re.sub(r"\d[\d,]*(?:\.\d+)?", lambda m: number_to_cn(m.group(0)), text)
    return text


_EN_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
)
_EN_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_EN_DIGITS = tuple(_EN_ONES[i] for i in range(10))
_EN_MONTHS = (
    "", "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)
_EN_UNITS = {
    "kg": ("kilogram", "kilograms"), "g": ("gram", "grams"),
    "km": ("kilometer", "kilometers"), "m": ("meter", "meters"),
    "cm": ("centimeter", "centimeters"), "mm": ("millimeter", "millimeters"),
    "sq m": ("square meter", "square meters"), "lb": ("pound", "pounds"),
    "lbs": ("pound", "pounds"), "ft": ("foot", "feet"), "in": ("inch", "inches"),
    "hour": ("hour", "hours"), "hours": ("hour", "hours"),
    "minute": ("minute", "minutes"), "minutes": ("minute", "minutes"),
}
_EN_ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
    11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
    15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth",
    19: "nineteenth", 20: "twentieth", 30: "thirtieth",
}


def _int_to_words(value: int) -> str:
    if value < 20:
        return _EN_ONES[value]
    if value < 100:
        return _EN_TENS[value // 10] + (f" {_EN_ONES[value % 10]}" if value % 10 else "")
    if value < 1000:
        remainder = value % 100
        return f"{_EN_ONES[value // 100]} hundred" + (f" {_int_to_words(remainder)}" if remainder else "")
    for scale, name in ((1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand")):
        if value >= scale:
            remainder = value % scale
            return f"{_int_to_words(value // scale)} {name}" + (f" {_int_to_words(remainder)}" if remainder else "")
    return str(value)


def _number_to_words(raw: str) -> str:
    cleaned = raw.replace(",", "")
    if "." not in cleaned:
        return _int_to_words(int(cleaned))
    integer, decimal = cleaned.split(".", 1)
    return f"{_int_to_words(int(integer))} point {' '.join(_EN_DIGITS[int(d)] for d in decimal)}"


def _ordinal_to_words(value: int) -> str:
    if value in _EN_ORDINALS:
        return _EN_ORDINALS[value]
    tens, ones = divmod(value, 10)
    return f"{_EN_TENS[tens]} {_EN_ORDINALS[ones]}"


def _is_singular(raw: str) -> bool:
    return float(raw.replace(",", "")) == 1.0


def _identifier_repl(match: re.Match[str]) -> str:
    tokens: list[str] = []
    for char in match.group(0):
        if char.isascii() and char.isalpha():
            tokens.append(char.upper())
        elif char.isdigit():
            tokens.append(_EN_DIGITS[int(char)])
    return " ".join(tokens)


def normalize_for_tts_en(text: str) -> str:
    """Normalize English numbers and identifiers while preserving words and names."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "")

    def iso_date(match: re.Match[str]) -> str:
        year, month, day = map(int, match.groups())
        try:
            parsed = date(year, month, day)
        except ValueError:
            # A malformed date is contract text, not an API validation error;
            # leave it untouched so the caller-declared Template can proceed.
            return match.group(0)
        return f"{_EN_MONTHS[parsed.month]} {_ordinal_to_words(parsed.day)}, {parsed.year}"

    text = re.sub(r"(\d{4})-(\d{2})-(\d{2})", iso_date, text)
    text = re.sub(
        r"(HK\$|HKD\s*)(\d[\d,]*(?:\.\d+)?)",
        lambda m: (
            f"{_number_to_words(m.group(2))} Hong Kong "
            f"{'dollar' if _is_singular(m.group(2)) else 'dollars'}"
        ),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\$(\d[\d,]*(?:\.\d+)?)",
        lambda m: f"{_number_to_words(m.group(1))} {'dollar' if _is_singular(m.group(1)) else 'dollars'}",
        text,
    )
    text = re.sub(
        r"(\d[\d,]*(?:\.\d+)?)\s*%",
        lambda m: f"{_number_to_words(m.group(1))} percent",
        text,
    )
    # Convert common measurement/time units before the identifier pass so a
    # compact value such as ``5kg`` is not mistaken for an alphanumeric ID.
    unit_pattern = "|".join(re.escape(unit) for unit in sorted(_EN_UNITS, key=len, reverse=True))
    text = re.sub(
        rf"\b(\d[\d,]*(?:\.\d+)?)\s*({unit_pattern})\b",
        lambda m: (
            f"{_number_to_words(m.group(1))} "
            f"{_EN_UNITS[m.group(2).lower()][0 if _is_singular(m.group(1)) else 1]}"
        ),
        text,
        flags=re.IGNORECASE,
    )
    # Contract references with a letter prefix and phone/account numbers with
    # separators are identifiers, not cardinal quantities.
    text = re.sub(
        r"\b(?=[A-Za-z0-9/-]*[A-Za-z])(?=[A-Za-z0-9/-]*\d)"
        r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*\b",
        _identifier_repl,
        text,
    )
    text = re.sub(
        r"\b\d+(?:[-/ ]\d+)+\b",
        lambda m: " ".join(_EN_DIGITS[int(d)] for d in re.sub(r"\D", "", m.group(0))),
        text,
    )
    text = re.sub(r"\b\d{6,}\b", lambda m: " ".join(_EN_DIGITS[int(d)] for d in m.group(0)), text)
    text = re.sub(r"\b\d[\d,]*(?:\.\d+)?\b", lambda m: _number_to_words(m.group(0)), text)
    return text
