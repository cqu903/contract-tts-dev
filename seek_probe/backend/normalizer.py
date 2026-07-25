"""Text normalization for TTS.

GPT-SoVITS's number frontend mishandles comma-grouped Arabic numerals
(e.g. "2,864,000" is read as "28640"). We pre-convert amounts / dates /
percentages / quantities into Chinese before sending to the engine.

The text shown to the user stays original (Arabic digits); only the text
fed to the engine is normalized. Output numerals are simplified-form
(万) — Cantonese g2p reads 万 and 萬 identically, so this is fine for speech.
"""
from __future__ import annotations
import re
from cn2an import an2cn

_DIGIT_CN = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
             "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}


def _digits_to_cn(s: str) -> str:
    return "".join(_DIGIT_CN[c] for c in s if c in _DIGIT_CN)


def _num_to_cn(num: str) -> str:
    """'2864000' -> '二百八十六万四千'; '5.25' -> '五點二五'; '0.5' -> '零點五'."""
    num = num.replace(",", "")
    if "." in num:
        int_part, dec_part = num.split(".", 1)
        int_cn = an2cn(int_part) if int_part else "零"
        return int_cn + "點" + _digits_to_cn(dec_part)
    return an2cn(num)


def normalize_for_tts(text: str) -> str:
    # 1) percentages: N% -> 百分之N(cn)   (run before the plain-number pass)
    text = re.sub(r'(\d[\d,]*\.?\d*)\s*%',
                  lambda m: "百分之" + _num_to_cn(m.group(1)), text)
    # 2) full dates: YYYY年M月D日  (year digit-by-digit; month/day as cn)
    def _date(m):
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return _digits_to_cn(y) + "年" + an2cn(str(int(mo))) + "月" + an2cn(str(int(d))) + "日"
    text = re.sub(r'(\d{4})年(\d{1,2})月(\d{1,2})日', _date, text)
    # 3) standalone 4-digit year YYYY年 -> digit-by-digit (二零二六)
    text = re.sub(r'(\d{4})年', lambda m: _digits_to_cn(m.group(1)) + "年", text)
    # 4) month / day numbers
    text = re.sub(r'(\d{1,2})月', lambda m: an2cn(str(int(m.group(1)))) + "月", text)
    text = re.sub(r'(\d{1,2})日', lambda m: an2cn(str(int(m.group(1)))) + "日", text)
    # 5) remaining numbers (amounts, quantities, durations) -> cn
    text = re.sub(r'\d[\d,]*\.?\d*', lambda m: _num_to_cn(m.group(0)), text)
    return text
