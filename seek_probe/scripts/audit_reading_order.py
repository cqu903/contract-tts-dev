"""Audit PDF reading-order extraction by comparing two strategies.

The converter (convert_contract_pdf.py) orders text by position (y, x) -- right
for row/form layouts but wrong for some multi-column label/value fields.
pymupdf's NATIVE text-stream order is right for those columns but wrong for
label-first form regions. This tool runs BOTH and flags every page where they
disagree, so a human reviews only the ambiguous pages (not the whole document).

Character accuracy is never at risk: both strategies use pymupdf's exact text;
only the ORDER differs. For each flagged page the report shows both versions
side-by-side; pick the correct one and patch the converted .txt.

Usage:
    uv run python -m seek_probe.scripts.audit_reading_order \
        ~/Downloads/Contract+ZFACL0603.pdf -o audit.md
"""
from __future__ import annotations
import argparse
from pathlib import Path

from seek_probe.scripts.convert_contract_pdf import convert_pdf_to_pages


def _norm(s: str) -> str:
    """Whitespace-insensitive comparison key (order + chars only)."""
    return "".join(s.split())


def audit_reading_order(pdf_path: str | Path) -> list[dict]:
    """Return a list of {page, sort, native} for each page where the positional
    sort order and the native text-stream order produce different text."""
    sort_pages = convert_pdf_to_pages(pdf_path, sort=True)
    native_pages = convert_pdf_to_pages(pdf_path, sort=False)
    flagged = []
    for i, (s, n) in enumerate(zip(sort_pages, native_pages), start=1):
        if _norm(s) != _norm(n):
            flagged.append({"page": i, "sort": s, "native": n})
    return flagged


def format_report(flagged: list[dict]) -> str:
    if not flagged:
        return "No reading-order disagreements found (sort == native on every page)."
    lines = [f"# Reading-order audit: {len(flagged)} page(s) differ between sort and native order\n",
             "Review each page and patch the converted .txt with whichever version reads correctly.\n"]
    for f in flagged:
        lines.append(f"## Page {f['page']}\n")
        lines.append("**sort (positional y,x — default, right for row/form layouts):**")
        lines.append("```")
        lines.append(f["sort"])
        lines.append("```\n")
        lines.append("**native (text-stream — right for some multi-column label/value fields):**")
        lines.append("```")
        lines.append(f["native"])
        lines.append("```\n")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit PDF reading order: flag pages where sort != native.")
    ap.add_argument("pdf", help="path to the source PDF")
    ap.add_argument("-o", "--out", default=None, help="write markdown report to this path (default: stdout)")
    args = ap.parse_args()
    report = format_report(audit_reading_order(args.pdf))
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"wrote report -> {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
