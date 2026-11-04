"""Render the Morpheus one-page pharmacogenomic medication summary (PDF)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas

from .fonts import ASSETS, register_fonts
from .phenotypes import GREEN, RED, YELLOW
from .summary import Card, Summary

PAGE_W, PAGE_H = letter
MARGIN = 24
NAVY = HexColor("#10243C")
PANEL = HexColor("#F3F7FA")
INK = HexColor("#21364D")
MUTED = HexColor("#4D657C")
BLUE = HexColor("#155B93")
HEADER_DATE = HexColor("#ABD6EA")
RULE = HexColor("#D5DEE7")

TIERS = {
    RED: dict(bg=HexColor("#FFF0F2"), accent=HexColor("#AA263A"),
              title="RED  |  PREFER ALTERNATIVE", note="Alternative when feasible"),
    YELLOW: dict(bg=HexColor("#FFF8E8"), accent=HexColor("#925F00"),
                 title="YELLOW  |  MODIFY / MONITOR", note="Dose or response consideration"),
    GREEN: dict(bg=HexColor("#EEF8F3"), accent=HexColor("#126A53"),
                title="GREEN  |  STANDARD PGx START", note="Clinical monitoring still applies"),
}
GENE_COLORS = {RED: HexColor("#AA263A"), YELLOW: HexColor("#925F00"), GREEN: HexColor("#126A53")}
GREY = HexColor("#7A8794")
MED_BORDER = {RED: HexColor("#D62839"), YELLOW: HexColor("#E0A100"), GREEN: HexColor("#1E9E6A"), "grey": GREY}
MED_TEXT = {RED: GENE_COLORS[RED], YELLOW: GENE_COLORS[YELLOW], GREEN: GENE_COLORS[GREEN], "grey": GREY}

BOLD, REG = "Carlito-Bold", "Carlito"
_FALLBACK = {"Carlito": "DejaVu", "Carlito-Bold": "DejaVu-Bold"}
_MISSING = set("≤≥→★")


class _Canvas(Canvas):
    """Canvas that draws the few glyphs Carlito lacks (≤ ≥ → ★) with DejaVu."""

    def drawString(self, x, y, text, *a, **k):
        font, size = self._fontname, self._fontsize
        if font not in _FALLBACK or not (_MISSING & set(text)):
            return super().drawString(x, y, text, *a, **k)
        seg, segs = "", []
        for ch in text:
            if ch in _MISSING:
                if seg:
                    segs.append((seg, font))
                segs.append((ch, _FALLBACK[font]))
                seg = ""
            else:
                seg += ch
        if seg:
            segs.append((seg, font))
        for part, f in segs:
            self.setFont(f, size * (0.85 if f != font else 1))
            super().drawString(x, y, part)
            x += self.stringWidth(part, f, size * (0.85 if f != font else 1))
        self.setFont(font, size)

    def drawRightString(self, x, y, text, *a, **k):
        self.drawString(x - _w(text, self._fontname, self._fontsize), y, text)


def _w(text, font, size):
    """String width, measuring the DejaVu fallback glyphs correctly."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    if font not in _FALLBACK:
        return stringWidth(text, font, size)
    return sum(stringWidth(ch, _FALLBACK[font], size * 0.85) if ch in _MISSING else stringWidth(ch, font, size)
               for ch in text)


def fmt_day(d: Optional[date], upper: bool = False) -> str:
    if d is None:
        return "—"
    s = f"{d.day} {d.strftime('%b')} {d.year}"
    return s.upper() if upper else s


class _Layout:
    """Font sizes and spacings, scaled down together if the content does not fit."""

    def __init__(self, scale: float):
        self.s = scale
        self.title = 12.0 * scale
        self.short = 11.5 * scale
        self.geno = 10.4 * scale
        self.lh_title = 12.9 * scale
        self.lh_short = 12.4 * scale
        self.lh_geno = 11.0 * scale
        self.card_gap = 3.2 * scale
        self.panel_head = 8 + 18 * scale
        self.panel_pad = 2 * scale


COL_GAP = 16
PANEL_X = MARGIN
PANEL_W = PAGE_W - 2 * MARGIN
CARD_X0 = PANEL_X + 10
COL_W = (PANEL_W - 20 - COL_GAP) / 2


def _rich_wrap(parts, width, size):
    """Greedy word wrap over [(text, font)] runs; returns lines of [(text, font)]."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words = [(w, f) for text, f in parts for w in text.split(" ") if w]
    lines, cur, cur_w = [], [], 0.0
    for w, f in words:
        ww = _w(w, f, size)
        sp = stringWidth(" ", f, size) if cur else 0
        if cur and cur_w + sp + ww > width:
            lines.append(cur); cur, cur_w, sp = [], 0.0, 0
        cur.append((w, f)); cur_w += sp + ww
    if cur:
        lines.append(cur)
    return lines


def _card_lines(card: Card, L: _Layout):
    t = _rich_wrap([(card.title.replace("★", "★ ") + " —", BOLD), (card.short, REG)], COL_W, L.title)
    g = simpleSplit(card.genotype_line, BOLD, L.geno, COL_W)
    h = len(t) * L.lh_title + 0.5 * L.s + len(g) * L.lh_geno + L.card_gap
    return t, [], g, h


def _med_lines(med, summary: Summary, L: _Layout):
    status_w = simpleSplit(med.status, BOLD, 7.6 * L.s, COL_W)[0]
    name = ("★ " if med.kind == "rule" else "") + med.display_name
    if med.entered_differs:
        name += f" ({med.entered})"
    sw = _width(status_w, BOLD, 7.6 * L.s)
    t = simpleSplit(name, BOLD, L.title, COL_W - sw - 8)
    g_text = summary.med_genotype_line(med)
    g = simpleSplit(g_text, BOLD, L.geno, COL_W) if g_text else []
    sh = simpleSplit(med.short, REG, L.short, COL_W)
    h = 2 * L.s + len(t) * L.lh_title + len(g) * L.lh_geno + len(sh) * L.lh_short + 3.5 * L.s
    return t, g, sh, h


OUTLINE = HexColor("#C5D0DB")


def _outline(c, x, y_bottom, w, h, color, width=1.0, radius=5):
    """Section border (no background fill)."""
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.roundRect(x, y_bottom, w, h, radius, stroke=1, fill=0)


def _width(text: str, font: str, size: float) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return stringWidth(text, font, size)


def _meds_height(summary: Summary, L: _Layout) -> float:
    meds = summary.patient_meds
    if not meds:
        return 0
    hs = [_med_lines(m, summary, L)[3] for m in meds]
    rows = [max(hs[i:i + 2]) + 3 * L.s for i in range(0, len(hs), 2)]
    return L.panel_head + sum(rows) + L.panel_pad


def _columns(cards: list[Card], L: _Layout):
    """Stack cards into two columns independently (each card goes to the shorter column), so a short
    card never leaves a gap next to a tall one. Returns [(card, col, y_offset, height)], total height."""
    tops = [0.0, 0.0]
    placed = []
    for card in cards:
        h = _card_lines(card, L)[3]
        col = 0 if tops[0] <= tops[1] + 0.1 else 1
        placed.append((card, col, tops[col], h))
        tops[col] += h
    return placed, max(tops)


def _panel_height(cards: list[Card], L: _Layout) -> float:
    if not cards:
        return 0
    return L.panel_head + _columns(cards, L)[1] + L.panel_pad


_SCALE_USED = [1.0]


def render_one_page(summary: Summary, out_path: str | Path) -> Path:
    register_fonts()
    out_path = Path(out_path)
    rep = summary.report
    c = _Canvas(str(out_path), pagesize=letter)
    c.setTitle(f"Morpheus PGx Summary – {summary.report.patient.display_name}")
    c.setAuthor("Morpheus Precision Health")

    def y(top: float) -> float:  # convert top-down coordinate
        return PAGE_H - top

    # ---- header: logo on white, title and date at right (no filled bar)
    logo_h = 36
    c.drawImage(str(ASSETS / "logo_wide.png"), MARGIN, y(6 + logo_h), logo_h * 1600 / 438, logo_h, mask="auto")
    c.setFillColor(NAVY)
    c.setFont(BOLD, 13)
    c.drawRightString(PAGE_W - MARGIN, y(23), "PHARMACOGENOMIC MEDICATION SUMMARY")
    c.setFillColor(MUTED)
    c.setFont(REG, 9)
    c.drawRightString(PAGE_W - MARGIN, y(36), fmt_day(rep.reported or date.today(), upper=True))

    # ---- patient bar
    _outline(c, MARGIN, y(80), PANEL_W, 28, OUTLINE)
    p = rep.patient
    name = " ".join(x for x in (p.first_name, p.last_name) if x).upper()
    if p.suffix:
        name += f", {p.suffix}"
    c.setFillColor(NAVY)
    c.setFont(BOLD, 12)
    c.drawString(34, y(70), name)
    meta = f"Quest/CLS  ·  collected {fmt_day(rep.collected)}  ·  reported {fmt_day(rep.reported)}"
    if p.dob:
        meta = f"DOB {p.dob.strftime('%m/%d/%Y')}  ·  " + meta
    c.setFillColor(MUTED)
    c.setFont(REG, 9)
    c.drawString(max(160, 34 + c.stringWidth(name, BOLD, 12) + 24), y(69.5), meta)

    # ---- flagged genes strip
    genes = summary.flagged_genes[:8]
    top = 84
    _outline(c, MARGIN, y(top + 26), PANEL_W, 26, OUTLINE)
    if genes:
        col = (PANEL_W - 20) / max(6, len(genes))
        for i, g in enumerate(genes):
            x = 34 + i * col
            if g.name in summary.patient_genes:  # gene affects one of the patient's medications
                c.setStrokeColor(MED_BORDER[g.tier])
                c.setLineWidth(1.2)
                c.roundRect(x - 4, y(top + 24.5), col - 2, 22, 3, stroke=1, fill=0)
            c.setFillColor(GENE_COLORS[g.tier])
            label = g.short_label.upper()
            fit = col - 6
            c.setFont(BOLD, min(10, 10 * fit / max(c.stringWidth(g.name, BOLD, 10), 1)))
            c.drawString(x, y(top + 11.5), g.name)
            c.setFont(BOLD, min(8.5, 8.5 * fit / max(c.stringWidth(label, BOLD, 8.5), 1)))
            c.drawString(x, y(top + 22), label)
    else:
        c.setFillColor(GENE_COLORS[GREEN])
        c.setFont(BOLD, 8)
        c.drawString(34, y(top + 16), "No non-normal gene results on this panel")

    # ---- tier panels, auto-scaled to fit
    avail_top, avail_bottom = 114, 738
    gap = 5
    tiers = [t for t in (RED, YELLOW, GREEN) if summary.cards.get(t)]
    n_panels = len(tiers) + (1 if summary.patient_meds else 0)
    scale = 1.0
    while scale > 0.6:
        _SCALE_USED[0] = scale
        L = _Layout(scale)
        total = (sum(_panel_height(summary.cards[t], L) for t in tiers) + _meds_height(summary, L)
                 + gap * (n_panels - 1))
        if total <= avail_bottom - avail_top:
            break
        scale -= 0.02
    L = _Layout(scale)

    cur = avail_top
    if summary.patient_meds:
        h = _meds_height(summary, L)
        _outline(c, PANEL_X, y(cur + h), PANEL_W, h, NAVY, width=1.4)
        c.setFillColor(NAVY)
        c.setFont(BOLD, 11 * L.s)
        c.drawString(34, y(cur + 4 + 11 * L.s), f"★ PATIENT MEDICATIONS  ({len(summary.patient_meds)})")
        c.setFillColor(MUTED)
        c.setFont(REG, 8)
        c.drawRightString(PANEL_X + PANEL_W - 10, y(cur + 4 + 11 * L.s),
                          "Box color = this patient's recommendation  ·  grey = no CPIC gene-based guidance")
        row_top = cur + L.panel_head
        meds = summary.patient_meds
        for i in range(0, len(meds), 2):
            row = meds[i:i + 2]
            heights = [_med_lines(m, summary, L)[3] for m in row]
            rh = max(heights)
            for j, med in enumerate(row):
                t_lines, g_lines, s_lines, _ = _med_lines(med, summary, L)
                x = CARD_X0 + j * (COL_W + COL_GAP)
                c.setFillColor(white)
                c.setStrokeColor(MED_BORDER[med.tier])
                c.setLineWidth(1.6)
                c.roundRect(x - 5, y(row_top + rh), COL_W + 10, rh, 3, stroke=1, fill=1)
                yy = row_top + 2 * L.s
                c.setFillColor(MED_TEXT[med.tier])
                c.setFont(BOLD, 7.6 * L.s)
                c.drawRightString(x + COL_W, y(yy + L.lh_title - 2.4 * L.s), med.status)
                c.setFillColor(INK)
                c.setFont(BOLD, L.title)
                for line in t_lines:
                    yy += L.lh_title
                    c.drawString(x, y(yy - 2.2 * L.s), line)
                c.setFillColor(BLUE if med.kind == "rule" else GREY)
                c.setFont(BOLD, L.geno)
                for line in g_lines:
                    yy += L.lh_geno
                    c.drawString(x, y(yy - 1.8 * L.s), line)
                c.setFillColor(MUTED)
                c.setFont(REG, L.short)
                for line in s_lines:
                    yy += L.lh_short
                    c.drawString(x, y(yy - 2 * L.s), line)
            row_top += rh + 3 * L.s
        cur += h + gap

    for t in tiers:
        cards = summary.cards[t]
        style = TIERS[t]
        h = _panel_height(cards, L)
        _outline(c, PANEL_X, y(cur + h), PANEL_W, h, style["accent"], width=1.4)
        c.setFillColor(style["accent"])
        c.setFont(BOLD, 11 * L.s)
        c.drawString(34, y(cur + 4 + 11 * L.s), style["title"])
        c.setFillColor(MUTED)
        c.setFont(REG, 8)
        c.drawRightString(PANEL_X + PANEL_W - 10, y(cur + 4 + 11 * L.s), style["note"])

        placed, _ = _columns(cards, L)
        for card, j, off, ch in placed:
            if True:
                t_lines, s_lines, g_lines, _ = _card_lines(card, L)
                row_top = cur + L.panel_head + off
                x = CARD_X0 + j * (COL_W + COL_GAP)
                yy = row_top
                if card.patient:  # outline cards holding the patient's medications
                    c.setStrokeColor(MED_BORDER[card.tier])
                    c.setLineWidth(1.6)
                    c.roundRect(x - 5, y(row_top + ch - L.card_gap + 3 * L.s), COL_W + 10,
                                ch - L.card_gap + 4 * L.s, 3, stroke=1, fill=0)
                for line in t_lines:
                    yy += L.lh_title
                    xx = x
                    for k, (w, f) in enumerate(line):
                        c.setFillColor(INK if f == BOLD else MUTED)
                        c.setFont(f, L.title)
                        txt = w if k == 0 else " " + w
                        c.drawString(xx, y(yy - 2.2 * L.s), txt)
                        xx += _w(txt, f, L.title)
                yy += 0.5 * L.s
                c.setFillColor(BLUE)
                c.setFont(BOLD, L.geno)
                for line in g_lines:
                    yy += L.lh_geno
                    c.drawString(x, y(yy - 1.8 * L.s), line)
        cur += h + gap

    # ---- footer
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.line(MARGIN, y(744), PAGE_W - MARGIN, y(744))
    c.setFillColor(BLUE)
    c.setFont(BOLD, 8.5)
    c.drawString(MARGIN, y(755), "NO CPIC DOSE CHANGE:")
    c.setFillColor(INK)
    c.setFont(REG, 8.5)
    nc = "  ·  ".join(summary.no_change) if summary.no_change else "—"
    nc_lines = simpleSplit(nc.replace("  ·  ", " · "), REG, 8.5, PAGE_W - 2 * MARGIN - 122)
    for i, line in enumerate(nc_lines[:2]):
        c.drawString(MARGIN + 122, y(755 + i * 8.5), line)
    extra = 8.5 * (min(len(nc_lines), 2) - 1)
    c.setFillColor(MUTED)
    c.setFont(REG, 7.8)
    c.drawString(MARGIN, y(767 + extra),
                 "Colors reflect tested PGx results only. Consider interactions, organ function, "
                 "indication and monitoring.")
    c.drawString(MARGIN, y(782),
                 f"Quest panel {fmt_day(rep.reported)}  |  CPIC: cpicpgx.org/guidelines  |  "
                 "Morpheus Precision Health")
    c.setFillColor(BLUE)
    c.setFont(BOLD, 7.8)
    c.drawRightString(PAGE_W - 36, y(782), "1 / 1")

    c.showPage()
    c.save()
    return out_path
