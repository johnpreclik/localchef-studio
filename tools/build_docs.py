"""Vyrobí PDF dokumentace z Markdownu v docs/ (stejně jako PDF export v aplikaci: Qt QTextDocument + QPdfWriter).

Použití:  python tools/build_docs.py            (všechny docs/*.md → docs/*.pdf)
          python tools/build_docs.py soubor.md  (jen vybrané)
Okno se neotevírá (Qt běží mimo obrazovku). Potřebuje PyQt6.
"""
import os
import re
import sys
from pathlib import Path

if sys.platform != "win32":                      # na Windows by 'offscreen' nenačetl písma (prázdné PDF)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QMarginsF, QSizeF                     # noqa: E402
from PyQt6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument  # noqa: E402
from PyQt6.QtWidgets import QApplication                       # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "docs"
CSS = """
body { font-family: 'Segoe UI', 'Segoe UI Emoji', sans-serif; font-size: 10pt; color: #222; }
h1 { font-size: 20pt; color: #1B5E20; margin-bottom: 4px; }
h2 { font-size: 14pt; color: #1B5E20; margin-top: 18px; border-bottom: 1px solid #ccc; }
h3 { font-size: 11.5pt; color: #333; margin-top: 12px; }
code { font-family: Consolas, monospace; color: #6A1B9A; }
pre { font-family: Consolas, monospace; background: #F3F3F3; }
table { border-collapse: collapse; margin: 6px 0; }
th { background: #E8F5E9; font-weight: bold; padding: 4px; }
td { padding: 4px; vertical-align: top; }
"""


def build(md_path: Path) -> Path:
    text = md_path.read_text(encoding="utf-8")
    doc = QTextDocument()
    doc.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
    html = doc.toHtml()
    html = re.sub(r"<table", '<table border="1" cellspacing="0" cellpadding="4" width="100%"', html)
    doc2 = QTextDocument()
    doc2.setDefaultStyleSheet(CSS)
    doc2.setDefaultFont(QFont("Segoe UI", 10))
    doc2.setHtml(html)
    title = text.splitlines()[0].lstrip("# ").strip() if text else md_path.stem
    out = md_path.with_suffix(".pdf")
    writer = QPdfWriter(str(out))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(16, 14, 16, 14), QPageLayout.Unit.Millimeter)
    writer.setResolution(110)
    writer.setTitle(title)
    writer.setCreator("LocalChef Studio – tools/build_docs.py")
    doc2.print(writer)                       # QTextDocument sám přidá čísla stránek
    del writer
    return out


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    files = [Path(a) for a in sys.argv[1:]] or sorted(DOCS.glob("*.md"))
    for f in files:
        out = build(f)
        print(f"{f.name} -> {out.name} ({out.stat().st_size // 1024} kB)")
    del app


if __name__ == "__main__":
    main()
