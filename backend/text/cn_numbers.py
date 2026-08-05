"""Shared Chinese number-to-speech helpers for Template normalizers."""
from __future__ import annotations

from cn2an import an2cn

_DIGIT_CN = {
    "0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
    "5": "五", "6": "六", "7": "七", "8": "八", "9": "九",
}


def digits_to_cn(value: str) -> str:
    """Return a digit-by-digit Chinese reading and ignore separators."""
    return "".join(_DIGIT_CN[char] for char in value if char in _DIGIT_CN)


def integer_to_cn(value: str) -> str:
    """Return a cardinal reading, falling back to digit-by-digit for long IDs."""
    try:
        return an2cn(value)
    except ValueError:
        return digits_to_cn(value)


def number_to_cn(value: str) -> str:
    """Return a Chinese cardinal/decimal reading for a formatted number."""
    value = value.replace(",", "")
    if "." in value:
        integer, decimal = value.split(".", 1)
        integer_cn = integer_to_cn(integer) if integer else "零"
        if decimal.strip("0") == "":
            return integer_cn
        return integer_cn + "點" + digits_to_cn(decimal)
    return integer_to_cn(value)
