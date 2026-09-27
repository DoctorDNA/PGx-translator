"""Register the bundled fonts with ReportLab (idempotent)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ASSETS = Path(__file__).parent / "assets"
FONT_DIR = ASSETS / "fonts"

_done = False


def register_fonts() -> None:
    global _done
    if _done:
        return
    for name, file in [
        ("DejaVu", "DejaVuSans.ttf"),
        ("DejaVu-Bold", "DejaVuSans-Bold.ttf"),
        ("Carlito", "Carlito-Regular.ttf"),
        ("Carlito-Bold", "Carlito-Bold.ttf"),
        ("Carlito-Italic", "Carlito-Italic.ttf"),
        ("Carlito-BoldItalic", "Carlito-BoldItalic.ttf"),
    ]:
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    addMapping("DejaVu", 0, 0, "DejaVu")
    addMapping("DejaVu", 1, 0, "DejaVu-Bold")
    addMapping("DejaVu", 0, 1, "DejaVu")
    addMapping("DejaVu", 1, 1, "DejaVu-Bold")
    addMapping("Carlito", 0, 0, "Carlito")
    addMapping("Carlito", 1, 0, "Carlito-Bold")
    addMapping("Carlito", 0, 1, "Carlito-Italic")
    addMapping("Carlito", 1, 1, "Carlito-BoldItalic")
    _done = True


# Carlito's Latin subset lacks these; render them with DejaVu inside Paragraph markup.
_MISSING_IN_CARLITO = "≤≥→"


def carlito_safe(text: str, bold: bool = False) -> str:
    """Escape text for a ReportLab Paragraph and patch glyphs missing from Carlito."""
    from xml.sax.saxutils import escape

    out = []
    face = "DejaVu-Bold" if bold else "DejaVu"
    for ch in escape(text):
        if ch in _MISSING_IN_CARLITO:
            out.append(f'<font name="{face}">{ch}</font>')
        else:
            out.append(ch)
    return "".join(out)
