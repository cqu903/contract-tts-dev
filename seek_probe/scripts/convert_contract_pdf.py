"""Convert a contract PDF to clean text, stripping running headers/footers.

Headers/footers are recognized by CONTENT (repeating strings/patterns), not by
page position. In this lender's PDFs the per-page warning "忠告: 借錢梗要還…" and
the page number "P.N / M" are real headers/footers; but the company name is baked
into the body text stream at body y-coordinates, so a y-band strip would wrongly
drop body content. Content matching avoids that.

Company-name text and all body content are left untouched.

Usage:
    uv run python -m seek_probe.scripts.convert_contract_pdf \
        ~/Downloads/Contract+ZFACL0603.pdf -o seek_probe/contracts/zacl0603.txt
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
import fitz  # pymupdf

# Real headers/footers for this lender's contract template.
DEFAULT_HEADER_PATTERNS = [
    r"^忠告",                    # HK Money Lenders Ordinance per-page warning
]
DEFAULT_FOOTER_PATTERNS = [
    r"^P\.\d+\s*/\s*\d+\s*$",    # page number "P.N / M"
]


def _drop_filters(header_patterns, footer_patterns):
    return [re.compile(p) for p in list(header_patterns) + list(footer_patterns)]


# CJK ideographs (no fullwidth punctuation) -- used to drop the spurious spaces
# pymupdf's line-wrap inserts between adjacent Han characters.
_CJK = r"一-鿿㐀-䶿"
_CJK_SPACE_CJK = re.compile(rf"([{_CJK}]) +(?=[{_CJK}])")


def _collapse_cjk_spaces(text: str) -> str:
    """Drop spaces between adjacent CJK ideographs (Cantonese has no word
    spacing). Spaces around Latin/digits/fullwidth punctuation are preserved."""
    return _CJK_SPACE_CJK.sub(r"\1", text)


def convert_pdf_to_pages(
    pdf_path: str | Path,
    header_patterns=DEFAULT_HEADER_PATTERNS,
    footer_patterns=DEFAULT_FOOTER_PATTERNS,
    line_gap_threshold: float = 8.0,
    sort: bool = True,
) -> list[str]:
    """Extract PDF text per page, dropping lines that match any header/footer
    pattern. Returns one text string per page.

    sort=True (default) orders lines by (y0, x0) -- correct for row/form layouts.
    sort=False keeps pymupdf's native text-stream order -- correct for some
    multi-column label/value layouts. The audit tool compares both to flag pages
    where reading order is ambiguous.

    Consecutive lines are space-joined when their vertical gap is small (same
    visual row / wrapped line) and newline-joined when the gap is large. Spaces
    between adjacent CJK ideographs are then collapsed."""
    drop = _drop_filters(header_patterns, footer_patterns)
    doc = fitz.open(str(pdf_path))
    try:
        pages: list[str] = []
        for page in doc:
            lines: list[tuple[float, float, float, str]] = []
            for blk in page.get_text("dict").get("blocks", []):
                for ln in blk.get("lines", []):
                    txt = "".join(s.get("text", "") for s in ln.get("spans", []))
                    t = " ".join(txt.split())
                    if not t or any(p.search(t) for p in drop):
                        continue
                    bx0, by0, bx1, by1 = ln["bbox"]
                    lines.append((by0, bx0, by1, t))
            if sort:
                lines.sort()
            out: list[str] = []
            prev_y1 = None
            for y0, _x0, y1, t in lines:
                if out and prev_y1 is not None and (y0 - prev_y1) > line_gap_threshold:
                    out.append("\n" + t)          # gap -> new field/paragraph
                elif out:
                    out.append(" " + t)           # tight -> same row / wrapped line
                else:
                    out.append(t)
                prev_y1 = y1
            pages.append(_collapse_cjk_spaces("".join(out)))
    finally:
        doc.close()
    return pages


def convert_pdf_to_text(
    pdf_path: str | Path,
    header_patterns=DEFAULT_HEADER_PATTERNS,
    footer_patterns=DEFAULT_FOOTER_PATTERNS,
    line_gap_threshold: float = 8.0,
    sort: bool = True,
) -> str:
    """Extract PDF text in reading order (pages newline-joined). See
    convert_pdf_to_pages for the sort semantics."""
    return "\n".join(convert_pdf_to_pages(
        pdf_path, header_patterns, footer_patterns, line_gap_threshold, sort))


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert a contract PDF to clean text.")
    ap.add_argument("pdf", help="path to the source PDF")
    ap.add_argument("-o", "--out", required=True, help="output .txt path")
    args = ap.parse_args()
    text = convert_pdf_to_text(args.pdf)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    n_hdr = len(re.findall(r"^忠告", text, flags=re.MULTILINE))
    n_ftr = len(re.findall(r"^P\.\d+\s*/\s*\d+", text, flags=re.MULTILINE))
    print(f"wrote {len(text)} chars -> {out}  (residual headers={n_hdr}, footers={n_ftr})")


if __name__ == "__main__":
    main()
