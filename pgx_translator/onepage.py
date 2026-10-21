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

BOLD, REG = "DejaVu-Bold", "DejaVu"


def fmt_day(d: Optional[date], upper: bool = False) -> str:
    if d is None:
        return "—"
    s = f"{d.day} {d.strftime('%b')} {d.year}"
    return s.upper() if upper else s


class _Layout:
    """Font sizes and spacings, scaled down together if the content does not fit."""

    def __init__(self, scale: float):
        self.s = scale
        self.title = 8.6 * scale
        self.short = 7.8 * scale
        self.geno = 7.0 * scale
        self.lh_title = 10.4 * scale
        self.lh_short = 9.6 * scale
        self.lh_geno = 9.0 * scale
        self.card_gap = 6.5 * scale
        self.panel_head = 26 * scale
        self.panel_pad = 6 * scale


COL_GAP = 16
PANEL_X = MARGIN
PANEL_W = PAGE_W - 2 * MARGIN
CARD_X0 = PANEL_X + 10
COL_W = (PANEL_W - 20 - COL_GAP) / 2


def _card_lines(card: Card, L: _Layout):
    t = simpleSplit(card.title, BOLD, L.title, COL_W)
    s = simpleSplit(card.short, REG, L.short, COL_W)
    g = simpleSplit(card.genotype_line, BOLD, L.geno, COL_W)
    h = len(t) * L.lh_title + len(s) * L.lh_short + 3 * L.s + len(g) * L.lh_geno + L.card_gap
    return t, s, g, h


def _med_lines(med, summary: Summary, L: _Layout):
    status_w = simpleSplit(med.status, BOLD, 6.2 * L.s, COL_W)[0]
    name = ("★ " if med.kind == "rule" else "") + med.display_name
    if med.entered_differs:
        name += f" ({med.entered})"
    sw = _width(status_w, BOLD, 6.2 * L.s)
    t = simpleSplit(name, BOLD, L.title, COL_W - sw - 8)
    g_text = summary.med_genotype_line(med)
    g = simpleSplit(g_text, BOLD, L.geno, COL_W) if g_text else []
    sh = simpleSplit(med.short, REG, L.short, COL_W)
    h = 4 * L.s + len(t) * L.lh_title + len(g) * L.lh_geno + len(sh) * L.lh_short + 5 * L.s
    return t, g, sh, h


def _width(text: str, font: str, size: float) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return stringWidth(text, font, size)


def _meds_height(summary: Summary, L: _Layout) -> float:
    meds = summary.patient_meds
    if not meds:
        return 0
    hs = [_med_lines(m, summary, L)[3] for m in meds]
    rows = [max(hs[i:i + 2]) + 4 * L.s for i in range(0, len(hs), 2)]
    return L.panel_head + sum(rows) + L.panel_pad


def _panel_height(cards: list[Card], L: _Layout) -> float:
    if not cards:
        return 0
    heights = [_card_lines(c, L)[3] for c in cards]
    rows = [max(heights[i:i + 2]) for i in range(0, len(heights), 2)]
    return L.panel_head + sum(rows) + L.panel_pad


def render_one_page(summary: Summary, out_path: str | Path) -> Path:
    register_fonts()
    out_path = Path(out_path)
    rep = summary.report
    c = Canvas(str(out_path), pagesize=letter)
    c.setTitle(f"Morpheus PGx Summary – {summary.report.patient.display_name}")
    c.setAuthor("Morpheus Precision Health")

    def y(top: float) -> float:  # convert top-down coordinate
        return PAGE_H - top

    # ---- header bar
    c.setFillColor(NAVY)
    c.rect(0, y(48), PAGE_W, 48, stroke=0, fill=1)
    c.drawImage(str(ASSETS / "logo_square.png"), 27, y(42), 37, 37, mask="auto")
    c.setFillColor(white)
    c.setFont(BOLD, 14)
    c.drawString(72, y(22), "MORPHEUS")
    c.setFont(REG, 7.8)
    c.drawString(72, y(35), "PRECISION HEALTH  |  PHARMACOGENOMIC MEDICATION SUMMARY")
    c.setFillColor(HEADER_DATE)
    c.setFont(REG, 7)
    c.drawRightString(PAGE_W - 36, y(20), fmt_day(rep.reported or date.today(), upper=True))

    # ---- patient bar
    c.setFillColor(PANEL)
    c.roundRect(MARGIN, y(80), PANEL_W, 28, 4, stroke=0, fill=1)
    p = rep.patient
    name = " ".join(x for x in (p.first_name, p.last_name) if x).upper()
    if p.suffix:
        name += f", {p.suffix}"
    c.setFillColor(NAVY)
    c.setFont(BOLD, 9.3)
    c.drawString(34, y(69), name)
    meta = f"Quest/CLS  ·  collected {fmt_day(rep.collected)}  ·  reported {fmt_day(rep.reported)}"
    if p.dob:
        meta = f"DOB {p.dob.strftime('%m/%d/%Y')}  ·  " + meta
    c.setFillColor(MUTED)
    c.setFont(REG, 7)
    c.drawString(max(160, 34 + c.stringWidth(name, BOLD, 9.3) + 24), y(68.5), meta)

    # ---- flagged genes strip
    genes = summary.flagged_genes[:8]
    top = 84
    c.setFillColor(PANEL)
    c.roundRect(MARGIN, y(top + 26), PANEL_W, 26, 4, stroke=0, fill=1)
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
            c.setFont(BOLD, min(8, 8 * fit / max(c.stringWidth(g.name, BOLD, 8), 1)))
            c.drawString(x, y(top + 11), g.name)
            c.setFont(BOLD, min(7, 7 * fit / max(c.stringWidth(label, BOLD, 7), 1)))
            c.drawString(x, y(top + 21.5), label)
    else:
        c.setFillColor(GENE_COLORS[GREEN])
        c.setFont(BOLD, 8)
        c.drawString(34, y(top + 16), "No non-normal gene results on this panel")

    # ---- tier panels, auto-scaled to fit
    avail_top, avail_bottom = 114, 738
    gap = 7
    tiers = [t for t in (RED, YELLOW, GREEN) if summary.cards.get(t)]
    n_panels = len(tiers) + (1 if summary.patient_meds else 0)
    scale = 1.0
    while scale > 0.6:
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
        c.setFillColor(PANEL)
        c.roundRect(PANEL_X, y(cur + h), PANEL_W, h, 5, stroke=0, fill=1)
        c.setFillColor(NAVY)
        c.rect(PANEL_X, y(cur + 7 + 15 * L.s), 3.5, 15 * L.s, stroke=0, fill=1)
        c.setFont(BOLD, 9.3 * L.s)
        c.drawString(34, y(cur + 7 + 11 * L.s), f"★ PATIENT MEDICATIONS  ({len(summary.patient_meds)})")
        c.setFillColor(MUTED)
        c.setFont(REG, 6.2)
        c.drawRightString(PANEL_X + PANEL_W - 10, y(cur + 7 + 10.5 * L.s),
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
                yy = row_top + 4 * L.s
                c.setFillColor(MED_TEXT[med.tier])
                c.setFont(BOLD, 6.2 * L.s)
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
            row_top += rh + 4 * L.s
        cur += h + gap

    for t in tiers:
        cards = summary.cards[t]
        style = TIERS[t]
        h = _panel_height(cards, L)
        c.setFillColor(style["bg"])
        c.roundRect(PANEL_X, y(cur + h), PANEL_W, h, 5, stroke=0, fill=1)
        c.setFillColor(style["accent"])
        c.rect(PANEL_X, y(cur + 7 + 15 * L.s), 3.5, 15 * L.s, stroke=0, fill=1)
        c.setFont(BOLD, 9.3 * L.s)
        c.drawString(34, y(cur + 7 + 11 * L.s), style["title"])
        c.setFillColor(MUTED)
        c.setFont(REG, 6.2)
        c.drawRightString(PANEL_X + PANEL_W - 10, y(cur + 7 + 10.5 * L.s), style["note"])

        row_top = cur + L.panel_head
        for i in range(0, len(cards), 2):
            row = cards[i:i + 2]
            heights = []
            for j, card in enumerate(row):
                t_lines, s_lines, g_lines, ch = _card_lines(card, L)
                heights.append(ch)
                x = CARD_X0 + j * (COL_W + COL_GAP)
                yy = row_top
                if card.patient:  # outline cards holding the patient's medications
                    c.setStrokeColor(MED_BORDER[card.tier])
                    c.setLineWidth(1.6)
                    c.roundRect(x - 5, y(row_top + ch - L.card_gap + 3 * L.s), COL_W + 10,
                                ch - L.card_gap + 4 * L.s, 3, stroke=1, fill=0)
                c.setFillColor(INK)
                c.setFont(BOLD, L.title)
                for line in t_lines:
                    yy += L.lh_title
                    c.drawString(x, y(yy - 2.2 * L.s), line)
                c.setFillColor(MUTED)
                c.setFont(REG, L.short)
                for line in s_lines:
                    yy += L.lh_short
                    c.drawString(x, y(yy - 2 * L.s), line)
                yy += 3 * L.s
                c.setFillColor(BLUE)
                c.setFont(BOLD, L.geno)
                for line in g_lines:
                    yy += L.lh_geno
                    c.drawString(x, y(yy - 1.8 * L.s), line)
            row_top += max(heights)
        cur += h + gap

    # ---- footer
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.line(MARGIN, y(744), PAGE_W - MARGIN, y(744))
    c.setFillColor(BLUE)
    c.setFont(BOLD, 7)
    c.drawString(MARGIN, y(755), "NO CPIC DOSE CHANGE:")
    c.setFillColor(INK)
    c.setFont(REG, 7)
    nc = "  ·  ".join(summary.no_change) if summary.no_change else "—"
    nc_lines = simpleSplit(nc.replace("  ·  ", " · "), REG, 7, PAGE_W - 2 * MARGIN - 122)
    for i, line in enumerate(nc_lines[:2]):
        c.drawString(MARGIN + 122, y(755 + i * 8.5), line)
    extra = 8.5 * (min(len(nc_lines), 2) - 1)
    c.setFillColor(MUTED)
    c.setFont(REG, 6.2)
    c.drawString(MARGIN, y(767 + extra),
                 "Colors reflect tested PGx results only. Consider interactions, organ function, "
                 "indication and monitoring.")
    c.drawString(MARGIN, y(782),
                 f"Quest panel {fmt_day(rep.reported)}  |  CPIC: cpicpgx.org/guidelines  |  "
                 "Morpheus Precision Health")
    c.setFillColor(BLUE)
    c.setFont(BOLD, 6.2)
    c.drawRightString(PAGE_W - 36, y(782), "1 / 1")

    c.showPage()
    c.save()
    return out_path
