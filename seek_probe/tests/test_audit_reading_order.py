import fitz  # pymupdf
from seek_probe.scripts.audit_reading_order import audit_reading_order, format_report


def _make_pdf(path, inserts):
    """inserts: list of (x, y, text) in insertion order."""
    doc = fitz.open()
    page = doc.new_page()
    for x, y, txt in inserts:
        page.insert_text((x, y), txt, fontsize=11)
    doc.save(str(path))
    doc.close()


def test_audit_flags_page_where_sort_and_native_disagree(tmp_path):
    pdf = tmp_path / "uo.pdf"
    # inserted out of positional order: HIGH (y=300) before LOW (y=100)
    _make_pdf(pdf, [(50, 300, "ZZHIGH"), (50, 100, "ZZLOW")])
    flagged = audit_reading_order(pdf)
    assert len(flagged) == 1
    assert flagged[0]["page"] == 1
    assert "sort" in flagged[0] and "native" in flagged[0]


def test_audit_no_flag_when_orders_agree(tmp_path):
    pdf = tmp_path / "ok.pdf"
    # inserted in positional order (low y first) -> sort == native
    _make_pdf(pdf, [(50, 100, "AA"), (50, 300, "BB")])
    flagged = audit_reading_order(pdf)
    assert flagged == []


def test_format_report_shows_both_versions():
    flagged = [{"page": 2, "sort": "AAA sorttext", "native": "AAA nativetext"}]
    report = format_report(flagged)
    assert "Page 2" in report
    assert "sorttext" in report and "nativetext" in report
    assert "1 page(s) differ" in format_report(flagged) or "1" in format_report(flagged)[:60]
    assert "No reading-order disagreements" in format_report([])
