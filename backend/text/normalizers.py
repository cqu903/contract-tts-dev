"""Template-specific text normalization for Mandarin and English TTS."""
from __future__ import annotations

import re
from datetime import date

from cn2an import an2cn

from .cn_numbers import digits_to_cn, number_to_cn
from .english_runs import is_spoken_english_run, normalize_english_run


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ENGLISH_RUN_PUA_BASE = 0xE000
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(raw: str) -> int | None:
    """Parse a conventional Roman numeral, returning ``None`` when malformed."""
    value = raw.upper()
    if not value or any(char not in _ROMAN_VALUES for char in value):
        return None
    total = 0
    previous = 0
    for char in reversed(value):
        current = _ROMAN_VALUES[char]
        total += -current if current < previous else current
        previous = max(previous, current)
    return total if 0 < total <= 3999 else None


def _valid_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _mandarin_date(year: int, month: int, day: int) -> str | None:
    parsed = _valid_date(year, month, day)
    if parsed is None:
        return None
    return (
        f"{digits_to_cn(str(parsed.year))}年"
        f"{an2cn(str(parsed.month))}月{an2cn(str(parsed.day))}日"
    )


def _spoken_marker_token(raw: str) -> str:
    """Read a structural marker literally, without guessing Roman-vs-letter intent."""
    if raw.isdigit():
        return _int_to_words(int(raw))
    return " ".join(raw.upper())


def normalize_for_tts_zh(text: str) -> str:
    """Render common Hong Kong contract formats for Mandarin TTS.

    Rules identify semantic values (dates, time, currency, identifiers) rather
    than specific contract data. Embedded English names and addresses are made
    word-readable; the Mandarin engine adapter performs final script conversion.
    """
    text = _CONTROL_CHARS.sub("", text or "")

    # Currency identity is resolved before the generic number pass. In the
    # Xcash Hong Kong Template a bare dollar sign denotes Hong Kong dollars.
    text = re.sub(r"(?:US\$|USD)\s*", "美元", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:RMB|CNY|CN¥|￥|¥)\s*", "人民币", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?:港[幣币]\s*)?(?:HK\$|HKD|\$)\s*",
        "港币",
        text,
        flags=re.IGNORECASE,
    )

    def chinese_date(match: re.Match[str]) -> str:
        year, month, day = map(int, match.groups())
        return _mandarin_date(year, month, day) or match.group(0)

    def iso_date(match: re.Match[str]) -> str:
        year, month, day = map(int, match.groups())
        return _mandarin_date(year, month, day) or match.group(0)

    def day_month_year_date(match: re.Match[str]) -> str:
        day, month, year = map(int, match.groups())
        return _mandarin_date(year, month, day) or match.group(0)

    text = re.sub(r"(?<!\d)(\d{4})年(\d{1,2})月(\d{1,2})日(?!\d)", chinese_date, text)
    text = re.sub(r"(?<!\d)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)", iso_date, text)
    text = re.sub(
        r"(?<!\d)(\d{1,2})[-/](\d{1,2})[-/](\d{4})(?!\d)",
        day_month_year_date,
        text,
    )

    # Explicit Roman context is unambiguous. Parenthesized structural markers
    # are read literally so (i) remains correct whether it is Roman or alphabetic.
    def roman_part(match: re.Match[str]) -> str:
        value = _roman_to_int(match.group(1))
        return f"第{an2cn(str(value))}{match.group(2)}" if value else match.group(0)

    text = re.sub(
        r"第([IVXLCDM]+)(部|章|條|条|節|节|項|项)",
        roman_part,
        text,
        flags=re.IGNORECASE,
    )

    def mandarin_marker(match: re.Match[str]) -> str:
        token = match.group(1)
        spoken = number_to_cn(token) if token.isdigit() else " ".join(token.upper())
        return f"第{spoken}项，"

    text = re.sub(
        r"^\s*[（(]([A-Za-z]+|\d+)[）)]\s*",
        mandarin_marker,
        text,
    )

    def embedded_mandarin_marker(match: re.Match[str]) -> str:
        prefix, token = match.groups()
        if token == "s":  # English plural suffix, for example account(s)
            return match.group(0)
        spoken = number_to_cn(token) if token.isdigit() else " ".join(token.upper())
        return f"{prefix}第{spoken}项，"

    text = re.sub(
        r"([：:；;，,]\s*)[（(]([a-z]+|\d+)[）)]\s*",
        embedded_mandarin_marker,
        text,
    )

    # Protect word-like English runs before the Mandarin floor and number
    # passes. This keeps an English address intact while Chinese-context dates,
    # amounts, identifiers, and isolated numeric floors continue below.
    english_runs: list[str] = []

    def stash_english_run(match: re.Match[str]) -> str:
        chunk = match.group(0)
        if not is_spoken_english_run(chunk):
            return chunk
        english_runs.append(normalize_english_run(chunk))
        return chr(_ENGLISH_RUN_PUA_BASE + len(english_runs) - 1)

    text = re.sub(r"[\x20-\x7e]+", stash_english_run, text)

    # Address floors are quantities, not alphanumeric identifiers.
    text = re.sub(
        r"(?<![A-Za-z0-9])(\d{1,3})\s*/?\s*[Ff](?![A-Za-z])",
        lambda m: f"{number_to_cn(m.group(1))}楼",
        text,
    )
    # Hong Kong identity-card check digits are part of the identifier, not a
    # parenthesized list item. Read the entire value one character at a time.
    def mandarin_identity_card(match: re.Match[str]) -> str:
        check = match.group(3)
        spoken_check = digits_to_cn(check) if check.isdigit() else check.upper()
        return f"{match.group(1).upper()}{digits_to_cn(match.group(2))}{spoken_check}"

    text = re.sub(
        r"\b([A-Za-z]{1,2})(\d{6})\s*[（(]([A-Za-z0-9])[）)]",
        mandarin_identity_card,
        text,
    )
    # Percentages must be handled before the generic number pass.
    text = re.sub(r"(\d[\d,]*(?:\.\d+)?)\s*%", lambda m: f"百分之{number_to_cn(m.group(1))}", text)
    # Times and separator-delimited identifiers (telephone/account/contract
    # numbers) are read digit-by-digit rather than as cardinal quantities.
    def mandarin_time(match: re.Match[str]) -> str:
        hour, minute = map(int, match.groups())
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return match.group(0)
        return f"{an2cn(str(hour))}点{an2cn(str(minute))}分"

    text = re.sub(
        r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)",
        mandarin_time,
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
    for index, english_run in enumerate(english_runs):
        text = text.replace(chr(_ENGLISH_RUN_PUA_BASE + index), english_run)
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
_EN_MONTH_LOOKUP = {
    name.lower(): index for index, name in enumerate(_EN_MONTHS) if name
}
_EN_MONTH_LOOKUP.update(
    {name[:3].lower(): index for index, name in enumerate(_EN_MONTHS) if name}
)
_EN_MONTH_PATTERN = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?"
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
    if value < 100:
        tens, ones = divmod(value, 10)
        return f"{_EN_TENS[tens]} {_EN_ORDINALS[ones]}"
    if value < 1000:
        hundreds, remainder = divmod(value, 100)
        if remainder == 0:
            return f"{_EN_ONES[hundreds]} hundredth"
        return f"{_EN_ONES[hundreds]} hundred {_ordinal_to_words(remainder)}"
    return f"{_int_to_words(value)}th"


def _english_date(year: int, month: int, day: int) -> str | None:
    parsed = _valid_date(year, month, day)
    if parsed is None:
        return None
    return (
        f"{_EN_MONTHS[parsed.month]} {_ordinal_to_words(parsed.day)}, "
        f"{_int_to_words(parsed.year)}"
    )


def _currency_to_words(raw: str, currency: str) -> str:
    """Render a decimal currency amount as major units and optional cents."""
    cleaned = raw.replace(",", "")
    integer, dot, decimal = cleaned.partition(".")
    major = int(integer)
    if dot and decimal.strip("0") and len(decimal) > 2:
        return f"{_number_to_words(raw)} {currency}s"
    if dot and len(decimal) <= 2:
        cents = int(decimal.ljust(2, "0"))
    else:
        cents = 0
    major_name = currency if major == 1 else f"{currency}s"
    spoken = f"{_int_to_words(major)} {major_name}"
    if cents:
        cent_name = "cent" if cents == 1 else "cents"
        spoken += f" and {_int_to_words(cents)} {cent_name}"
    return spoken


def _english_time(match: re.Match[str]) -> str:
    hour, minute = map(int, match.group(1, 2))
    meridiem = (match.group(3) or "").lower()
    if meridiem:
        if not (1 <= hour <= 12 and 0 <= minute <= 59):
            return match.group(0)
    elif not (0 <= hour <= 23 and 0 <= minute <= 59):
        return match.group(0)

    if hour == 0 and minute == 0 and not meridiem:
        return "midnight"
    spoken = _int_to_words(hour)
    if minute == 0:
        spoken += " o'clock"
    elif minute < 10:
        spoken += f" oh {_int_to_words(minute)}"
    else:
        spoken += f" {_int_to_words(minute)}"
    if meridiem:
        spoken += f" {meridiem} m"
    return spoken


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
    """Render common contract semantics for English TTS.

    The implementation validates values before converting them so date-shaped
    identifiers remain identifiers, while names and ordinary prose are kept.
    """
    text = _CONTROL_CHARS.sub("", text or "")

    def iso_date(match: re.Match[str]) -> str:
        year, month, day = map(int, match.groups())
        return _english_date(year, month, day) or match.group(0)

    def day_month_year_date(match: re.Match[str]) -> str:
        day, month, year = map(int, match.groups())
        return _english_date(year, month, day) or match.group(0)

    def textual_day_month_year(match: re.Match[str]) -> str:
        day = int(match.group(1))
        month = _EN_MONTH_LOOKUP[match.group(2)[:3].lower()]
        year = int(match.group(3))
        return _english_date(year, month, day) or match.group(0)

    def textual_month_day_year(match: re.Match[str]) -> str:
        month = _EN_MONTH_LOOKUP[match.group(1)[:3].lower()]
        day = int(match.group(2))
        year = int(match.group(3))
        return _english_date(year, month, day) or match.group(0)

    # Parse all supported dates before slash/hyphen identifiers and generic
    # numbers. Hong Kong numeric dates use day-month-year order.
    text = re.sub(
        r"(?<!\d)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)",
        iso_date,
        text,
    )
    text = re.sub(
        r"(?<!\d)(\d{1,2})[-/](\d{1,2})[-/](\d{4})(?!\d)",
        day_month_year_date,
        text,
    )
    text = re.sub(
        rf"(?<!\w)(\d{{1,2}})(?:st|nd|rd|th)?\s+({_EN_MONTH_PATTERN})\s+(\d{{4}})(?!\d)",
        textual_day_month_year,
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"\b({_EN_MONTH_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(\d{{4}})(?!\d)",
        textual_month_day_year,
        text,
        flags=re.IGNORECASE,
    )

    # A leading parenthesized token is a structural identifier. Spell it
    # literally instead of guessing whether (i) is Roman or alphabetic.
    text = re.sub(
        r"^\s*[（(]([A-Za-z]+|\d+)[）)]\s*",
        lambda m: f"item {_spoken_marker_token(m.group(1))}, ",
        text,
    )

    def embedded_english_marker(match: re.Match[str]) -> str:
        prefix, token = match.groups()
        if token == "s":  # Preserve productive plural forms such as account(s).
            return match.group(0)
        return f"{prefix}item {_spoken_marker_token(token)}, "

    text = re.sub(
        r"([：:；;，,]\s*)[（(]([a-z]+|\d+)[）)]\s*",
        embedded_english_marker,
        text,
    )

    def contextual_roman(match: re.Match[str]) -> str:
        value = _roman_to_int(match.group(2))
        return f"{match.group(1)} {_int_to_words(value)}" if value else match.group(0)

    text = re.sub(
        r"\b(Part|Schedule|Section)\s+([IVXLCDM]+)\b",
        contextual_roman,
        text,
        flags=re.IGNORECASE,
    )

    # Make address abbreviations and all-caps names word-readable before the
    # English number passes expand floors and other numeric semantics.
    text = normalize_english_run(text)

    text = re.sub(
        r"(?<![A-Za-z0-9])(\d{1,3})(?:st|nd|rd|th)?\s*/?\s*[Ff](?![A-Za-z])",
        lambda m: f"{_ordinal_to_words(int(m.group(1)))} floor",
        text,
    )
    text = re.sub(
        r"(?<!\d)(\d{1,3})(?:st|nd|rd|th)\s+[Ff]loor\b",
        lambda m: f"{_ordinal_to_words(int(m.group(1)))} floor",
        text,
    )

    text = re.sub(
        r"(?<!\d)(\d{1,2}):(\d{2})(?:\s*([ap])\.?m\.?)?(?!\d)",
        _english_time,
        text,
        flags=re.IGNORECASE,
    )

    amount_pattern = r"(\d[\d,]*(?:\.\d+)?)"
    text = re.sub(
        rf"(?:HK\$|HKD)\s*{amount_pattern}",
        lambda m: _currency_to_words(m.group(1), "Hong Kong dollar"),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"\$\s*{amount_pattern}",
        lambda m: _currency_to_words(m.group(1), "dollar"),
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
        r"\b[A-Za-z]{1,2}\d{6}\s*[（(][A-Za-z0-9][）)]",
        _identifier_repl,
        text,
    )
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
