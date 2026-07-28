import re
import fitz  # pymupdf
from seek_probe.scripts.convert_contract_pdf import (
    convert_pdf_to_text, DEFAULT_HEADER_PATTERNS, DEFAULT_FOOTER_PATTERNS,
)


def _make_pdf(path, body_lines, header="PAGE_HEADER_LINE", footer="P.1 / 1"):
    doc = fitz.open()
    page = doc.new_page()
    h = page.rect.height
    page.insert_text((50, 25), header, fontsize=9)
    y = h / 2
    for ln in body_lines:
        page.insert_text((50, y), ln, fontsize=11)
        y += 20
    page.insert_text((50, h - 15), footer, fontsize=9)
    doc.save(str(path))
    doc.close()


def test_strips_header_and_footer_keeps_body(tmp_path):
    pdf = tmp_path / "c.pdf"
    _make_pdf(pdf, ["Body line one", "Body line two"])
    out = convert_pdf_to_text(pdf, header_patterns=[r"^PAGE_HEADER"])
    assert "PAGE_HEADER" not in out                          # header stripped
    assert not re.search(r"P\.\d+\s*/\s*\d+", out)           # footer stripped
    assert "Body line one" in out and "Body line two" in out  # body preserved


def test_default_header_pattern_matches_warning():
    # the real per-page HK Money Lenders Ordinance warning header is matched
    assert re.search(DEFAULT_HEADER_PATTERNS[0], "忠告: 借錢梗要還, 咪俾錢中介")
    assert not re.search(DEFAULT_HEADER_PATTERNS[0], "本協議正文內容")


def test_default_footer_pattern_matches_page_number():
    assert re.search(DEFAULT_FOOTER_PATTERNS[0], "P.3 / 20")
    assert not re.search(DEFAULT_FOOTER_PATTERNS[0], "電話25310333")


def test_collapse_spaces_between_cjk_chars():
    from seek_probe.scripts.convert_contract_pdf import _collapse_cjk_spaces
    # CJK<space>CJK collapsed (incl. chains); CJK-Latin and Latin-Latin kept
    assert _collapse_cjk_spaces("地 點") == "地點"
    assert _collapse_cjk_spaces("金 額 結 欠") == "金額結欠"
    assert _collapse_cjk_spaces("貸款人姓名： Zero Finance") == "貸款人姓名： Zero Finance"
    assert _collapse_cjk_spaces("Flat 6 15th Floor") == "Flat 6 15th Floor"


def test_sort_vs_native_order(tmp_path):
    """sort=True orders by position (y,x); sort=False keeps native text-stream
    order. Where they disagree is exactly what the audit tool flags."""
    from seek_probe.scripts.convert_contract_pdf import convert_pdf_to_pages
    pdf = tmp_path / "uo.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 300), "ZZHIGH")   # inserted first, higher y
    page.insert_text((50, 100), "ZZLOW")    # inserted second, lower y
    doc.save(str(pdf))
    doc.close()
    sort_p = convert_pdf_to_pages(pdf, sort=True)[0]
    native_p = convert_pdf_to_pages(pdf, sort=False)[0]
    # positional order: ZZLOW (y=100) before ZZHIGH (y=300)
    assert sort_p.index("ZZLOW") < sort_p.index("ZZHIGH")
    # native (text-stream / insertion) order: ZZHIGH before ZZLOW
    assert native_p.index("ZZHIGH") < native_p.index("ZZLOW")
