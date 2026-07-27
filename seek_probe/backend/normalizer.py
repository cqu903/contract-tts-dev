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
        int_cn = _int_to_cn(int_part) if int_part else "零"
        if dec_part.strip("0") == "":   # ".00" etc. -> whole number; drop the decimal
            return int_cn
        return int_cn + "點" + _digits_to_cn(dec_part)
    return _int_to_cn(num)


def _int_to_cn(int_part: str) -> str:
    """Cardinal reading via cn2an. Long reference/account numbers that exceed
    cn2an's range (>16 digits, e.g. loan-agreement number 1279857891713384448)
    fall back to digit-by-digit -- they are IDs, not cardinal quantities."""
    try:
        return an2cn(int_part)
    except ValueError:
        return _digits_to_cn(int_part)


# General HK address lexicon -- reusable across contracts, NOT per-contract
# data. Districts, common areas, and structural address words. Company and
# person names are deliberately excluded: they vary per contract and are left
# to the model's English pronunciation.
_ADDRESS_LEXICON = {
    # Kowloon
    "kowloon city": "九龍城", "kowloon tong": "九龍塘", "kowloon bay": "九龍灣",
    "kwun tong": "觀塘", "wong tai sin": "黃大仙", "sham shui po": "深水埗",
    "yau tsim mong": "油尖旺", "tsim sha tsui": "尖沙咀", "mong kok": "旺角",
    "hung hom": "紅磡", "kowloon": "九龍",
    # Hong Kong Island
    "central and western": "中西區", "wan chai": "灣仔", "causeway bay": "銅鑼灣",
    "admiralty": "金鐘", "central": "中環", "north point": "北角",
    # New Territories
    "tsuen wan": "荃灣", "tuen mun": "屯門", "yuen long": "元朗",
    "tai po": "大埔", "sha tin": "沙田", "sai kung": "西貢",
    "tseung kwan o": "將軍澳", "kwai chung": "葵涌", "kwai tsing": "葵青",
    "ma on shan": "馬鞍山",
    # structural address words (English reads poorly or gets letter-spelled)
    "building": "大廈", "estate": "屋邨", "block": "座", "blk": "座",
    "flat": "室", "flt": "室",
}

# Roman numerals -> Chinese. Length>=2 forms are used for parenthesized list
# markers (single (i)/(v)/(x) are ambiguous with letter markers a/b/c…); the
# full set (incl. singles) is used after 第, where it's unambiguously ordinal.
_ROMAN_TO_CN = {"i": "一", "ii": "二", "iii": "三", "iv": "四", "v": "五",
                "vi": "六", "vii": "七", "viii": "八", "ix": "九", "x": "十",
                "xi": "十一", "xii": "十二", "xiii": "十三", "xiv": "十四", "xv": "十五"}


def _apply_lexicon(text: str, lexicon: dict[str, str]) -> str:
    """Case-insensitive, whole-phrase replacement, longest phrases first (so
    'Kowloon City' wins over 'Kowloon'). Internal whitespace is flexible."""
    for phrase in sorted(lexicon, key=len, reverse=True):
        pat = r"\b" + r"\s+".join(re.escape(w) for w in phrase.split()) + r"\b"
        text = re.sub(pat, lexicon[phrase], text, flags=re.IGNORECASE)
    return text


def _roman_repl(m: re.Match) -> str:
    cn = _ROMAN_TO_CN.get(m.group(1).lower())
    return "（" + cn + "）" if cn else m.group(0)


def normalize_for_tts(text: str) -> str:
    # 0) strip PDF control chars (keep tab/newline); unify $ / HK$ -> 港幣 (HK context)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'(HK)?[$＄]', '港幣', text)
    text = re.sub(r'港幣港幣', '港幣', text)

    # 0.5) address lexicon (districts + structural words), floor indicator, and
    # roman list markers. Runs before the number rules so 39/F is handled cleanly.
    # Names / companies are untouched (model reads them with English pronunciation).
    text = _apply_lexicon(text, _ADDRESS_LEXICON)
    # 39/F -> 三十九樓 (convert the digit to Chinese here so later number rules
    # don't space-join it with an adjacent flat number like 08)
    text = re.sub(r'(\d+)\s*/?\s*[Ff](?![A-Za-z])',
                  lambda m: _num_to_cn(m.group(1)) + "樓", text)
    text = re.sub(r'[（(]([ivxlcdm]{2,})[）)]', _roman_repl, text, flags=re.IGNORECASE)
    text = re.sub(r'第([ivxlcdm]+)',                # 第III部 -> 第三部 (ordinal)
                  lambda m: "第" + _ROMAN_TO_CN.get(m.group(1).lower(), m.group(1)),
                  text, flags=re.IGNORECASE)

    # Reference numbers read DIGIT-BY-DIGIT, not as cardinals. In this HK contract
    # every amount is comma-grouped or currency-prefixed, so "no comma + no
    # currency prefix" reliably marks IDs / phones / accounts / licences.
    # 1) times HH:MM -> H時M分
    text = re.sub(r'(\d{1,2}):(\d{2})',
                  lambda m: an2cn(str(int(m.group(1)))) + "時" + an2cn(str(int(m.group(2)))) + "分", text)
    # 2) slash dates D/M/YYYY -> YYYY年M月D日 (before the generic code rule)
    text = re.sub(r'(\d{1,2})/(\d{1,2})/(\d{4})',
                  lambda m: _digits_to_cn(m.group(3)) + "年" + an2cn(str(int(m.group(2)))) + "月" + an2cn(str(int(m.group(1)))) + "日", text)
    # 3) separator-joined digit codes: 024-363-… / 0954/2024 / 2531 0300 -> digit-by-digit
    text = re.sub(r'\d+(?:[/ \-]\d+)+',
                  lambda m: _digits_to_cn(re.sub(r'\D', '', m.group(0))), text)
    # 4) bare runs >=6 digits (no comma, not currency-prefixed) -> digit-by-digit
    text = re.sub(r'(?<![$港幣元\d])\d{6,}(?![\d,])',
                  lambda m: _digits_to_cn(m.group(0)), text)

    # 5) percentages N% -> 百分之N   (before the cardinal pass)
    text = re.sub(r'(\d[\d,]*(?:\.\d+)?)\s*%',
                  lambda m: "百分之" + _num_to_cn(m.group(1)), text)
    # 6) full dates YYYY年M月D日, then standalone year, month, day
    def _date(m):
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return _digits_to_cn(y) + "年" + an2cn(str(int(mo))) + "月" + an2cn(str(int(d))) + "日"
    text = re.sub(r'(\d{4})年(\d{1,2})月(\d{1,2})日', _date, text)
    text = re.sub(r'(\d{4})年', lambda m: _digits_to_cn(m.group(1)) + "年", text)
    text = re.sub(r'(\d{1,2})月', lambda m: an2cn(str(int(m.group(1)))) + "月", text)
    text = re.sub(r'(\d{1,2})日', lambda m: an2cn(str(int(m.group(1)))) + "日", text)
    # 7) alphanumeric codes: XR-7200 -> XR-七二零零
    text = re.sub(r'([A-Za-z]+-?)(\d+)', lambda m: m.group(1) + _digits_to_cn(m.group(2)), text)
    # 8) remaining numbers (amounts/quantities) -> cardinal; (?:\.\d+)? so "9." -> 九 (period kept)
    text = re.sub(r'\d[\d,]*(?:\.\d+)?', lambda m: _num_to_cn(m.group(0)), text)
    # 9) ASCII punctuation -> fullwidth (engine reads these more naturally)
    text = text.replace('(', '（').replace(')', '）').replace(';', '；').replace(':', '：').replace('/', '、')
    return text
