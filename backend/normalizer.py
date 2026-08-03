"""Text normalization for TTS (engine text_lang=auto_yue).

The engine's auto_yue frontend switches per-token Cantonese<->English, so we no
longer translate English addresses/names to Chinese. Instead we:

  * L2-clean English runs (a maximal ASCII run containing a >=3-letter Latin word)
    so auto_yue reads them as WORDS, not letter-spells: expand structural
    abbreviations (FLT->Flat, BLK->Block, 39/F->39th Floor) and title-case
    ALL-CAPS words (ZERO->Zero). Digits inside an English run stay numeric
    (read in English).
  * Keep the Cantonese normalization for the CJK-context remainder -- amounts /
    dates / IDs / accounts / times / roman numerals -- because GPT-SoVITS
    mishandles comma-grouped Arabic numerals (e.g. "2,864,000" -> "28640").

English runs are stashed as Private-Use-Area chars so the CJK rules see the
remainder as one contiguous string (date rules like 2026年8月1日 need the CJK
delimiters adjacent to the digits, which a naive ASCII/CJK split would break).

Also fixes the 還 polyphone: the cosyvoice Cantonese frontend reads it haan4
("hái") even in waan4 (repay) words, so 償還/清還/退還/歸還/還款 are swapped to
homophones (償環/環款/...) in the engine-bound text.

The text shown to the user stays original (Arabic digits); only the engine-bound
text is normalized. Output numerals are simplified-form (万) -- Cantonese g2p
reads 万 and 萬 identically.
"""
from __future__ import annotations
import re
from cn2an import an2cn

from backend.cn_numbers import digits_to_cn as _digits_to_cn
from backend.cn_numbers import number_to_cn as _num_to_cn

_PUA_BASE = 0xE000  # Private Use Area start; placeholders for stashed English runs


# --- L2: English-run cleanup (for the engine's auto_yue English frontend) ---

# Structural abbreviations the English g2p would letter-spell -> expand to words.
# Keys are 3 letters so they never collide with the full words they map to.
_L2_ABBREV = {
    "flt": "Flat",
    "blk": "Block",
}

_ROMAN_TO_CN = {"i": "一", "ii": "二", "iii": "三", "iv": "四", "v": "五",
                "vi": "六", "vii": "七", "viii": "八", "ix": "九", "x": "十",
                "xi": "十一", "xii": "十二", "xiii": "十三", "xiv": "十四", "xv": "十五"}

# Polyphone fix (engine-bound text only): the cosyvoice Cantonese frontend
# misreads 還 as haan4 ("hái") even in waan4 (repay/return) words — verified
# 2026-07 by A/B synth: 償還 and 償環 produce byte-different audio. Swap the
# waan4 words for homophones. haan4 words (還是/還有) are deliberately absent.
_WAAN4_HOMOPHONES = {"償還": "償環", "清還": "清環", "退還": "退環",
                     "歸還": "歸環", "還款": "環款"}


def _ordinal(n: int) -> str:
    """1->1st, 2->2nd, 3->3rd, 4->4th, 11->11th, 12->12th, 39->39th."""
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _l2_english(text: str) -> str:
    """Clean an English run for auto_yue: expand structural abbreviations,
    39/F -> Nth Floor, and title-case ALL-CAPS words. Digits are left intact
    (read in English, not converted to Chinese)."""
    for ab, full in _L2_ABBREV.items():
        text = re.sub(r"\b" + ab + r"\b", full, text, flags=re.IGNORECASE)
    text = re.sub(r"(\d+)\s*/?\s*[Ff](?![A-Za-z])",
                  lambda m: _ordinal(int(m.group(1))) + " Floor", text)
    text = re.sub(r"\b[A-Z]{2,}\b", lambda m: m.group(0).capitalize(), text)
    return text


def _roman_repl(m: re.Match) -> str:
    cn = _ROMAN_TO_CN.get(m.group(1).lower())
    return "（" + cn + "）" if cn else m.group(0)


def _normalize_cjk_context(text: str) -> str:
    """Cantonese normalization for the CJK-context remainder (everything that is
    NOT a stashed English run): the number / currency / date / ID rules.
    Address lexicon is gone -- English runs handle addresses now. Roman markers
    are converted earlier (pre-pass) so a >=3-letter roman like III isn't stashed
    as an English run."""
    # 39/F -> 三十九樓 (only reaches here when not inside an English run)
    text = re.sub(r'(\d+)\s*/?\s*[Ff](?![A-Za-z])',
                  lambda m: _num_to_cn(m.group(1)) + "樓", text)

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


def normalize_for_tts(text: str) -> str:
    # 0) global pre-pass: strip control chars; unify $ / HK$ -> 港幣 (HK context)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'(HK)?[$＄]', '港幣', text)
    text = re.sub(r'港幣港幣', '港幣', text)

    # 0.3) polyphone fix: waan4 words -> homophones (engine misreads 還 as haan4)
    for word, homophone in _WAAN4_HOMOPHONES.items():
        text = text.replace(word, homophone)

    # 0.35) 注：/註： makes the engine misread the following word (verified:
    # 注：港幣 misreads 港幣, while 注，/注。/金額：港幣 all read correctly —
    # the trigger is the 注： token, not the colon). Use a comma instead.
    text = text.replace("注：", "注，").replace("註：", "註，")

    # 0.4) roman list markers (ii)/(iii)/... and 第III部 ordinals -> Chinese. Runs
    # BEFORE stashing so a >=3-letter roman (III, VII...) isn't swept into an
    # English run and title-cased. These markers only occur in CJK context (第 /
    # fullwidth parens), so converting them early is safe.
    text = re.sub(r'[（(]([ivxlcdm]{2,})[）)]', _roman_repl, text, flags=re.IGNORECASE)
    text = re.sub(r'第([ivxlcdm]+)',
                  lambda m: "第" + _ROMAN_TO_CN.get(m.group(1).lower(), m.group(1)),
                  text, flags=re.IGNORECASE)

    # 0.5) stash English runs (ASCII runs containing a >=3-letter Latin word) as
    # Private-Use-Area placeholders so the CJK rules see an intact remainder.
    # ASCII runs without an English word (digits/codes/punct, e.g. 126,000 or
    # XR-7200) stay in place for the Cantonese number rules.
    stash: list[str] = []

    def _maybe_stash(m: re.Match) -> str:
        chunk = m.group(0)
        if re.search(r'[A-Za-z]{3,}', chunk):
            stash.append(_l2_english(chunk))
            return chr(_PUA_BASE + len(stash) - 1)
        return chunk

    text = re.sub(r'[\x20-\x7e]+', _maybe_stash, text)

    # 1) Cantonese normalization on the CJK-context remainder
    text = _normalize_cjk_context(text)

    # 2) restore English runs
    for i, eng in enumerate(stash):
        text = text.replace(chr(_PUA_BASE + i), eng)
    return text
