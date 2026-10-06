"""Render the full multi-page Morpheus Pharmacogenomics Report as a PDF."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (CondPageBreak, Flowable, Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .fonts import ASSETS, carlito_safe as esc, register_fonts
from .phenotypes import GREEN, RED, YELLOW
from .report_text import (HOW_TO_READ, LINK_BLUE, LINK_HINT, QUICK_REF_NOTE, REPORT_GUIDE, SHARE_NOTE,
                          STATUS_LABEL, drug_anchor, footer_text, interpretation_notes, key_drug_segments,
                          patient_rows)
from .summary import Summary

NAVY = HexColor("#0A1628")
GRID = HexColor("#808080")
LIGHT = HexColor("#F2F2F2")
FOOT = HexColor("#7F7F7F")
TIER_COLOR = {RED: HexColor("#FF0000"), YELLOW: HexColor("#FFC000"), GREEN: HexColor("#00B050")}

PAGE_W, PAGE_H = letter
MARGIN = 0.5 * inch
CONTENT_W = PAGE_W - 2 * MARGIN

F, FB, FI = "Carlito", "Carlito-Bold", "Carlito-Italic"

ST = {
    "title": ParagraphStyle("title", fontName=FB, fontSize=17.5, leading=22, textColor=NAVY, alignment=TA_CENTER),
    "h1c": ParagraphStyle("h1c", fontName=FB, fontSize=16, leading=20, textColor=NAVY, alignment=TA_CENTER),
    "h1": ParagraphStyle("h1", fontName=FB, fontSize=15, leading=19, textColor=NAVY, leftIndent=5),
    "h3": ParagraphStyle("h3", fontName=FB, fontSize=15, leading=19, textColor=NAVY, spaceBefore=8,
                         spaceAfter=4),
    "body": ParagraphStyle("body", fontName=F, fontSize=14, leading=18, spaceAfter=8),
    "bullet": ParagraphStyle("bullet", fontName=F, fontSize=14, leading=18, leftIndent=14,
                             bulletIndent=0, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName=F, fontSize=12, leading=14.5),
    "cellb": ParagraphStyle("cellb", fontName=FB, fontSize=12, leading=14.5),
    "pcell": ParagraphStyle("pcell", fontName=F, fontSize=12.5, leading=15),
    "pcellb": ParagraphStyle("pcellb", fontName=FB, fontSize=12.5, leading=15),
    "qr": ParagraphStyle("qr", fontName=F, fontSize=11, leading=14, spaceAfter=6),
    "qrh": ParagraphStyle("qrh", fontName=FB, fontSize=11.5, leading=14, textColor=NAVY, spaceAfter=2),
    "qrhead": ParagraphStyle("qrhead", fontName=FB, fontSize=12.5, leading=15, alignment=TA_CENTER),
    "legend": ParagraphStyle("legend", fontName=FB, fontSize=12.5, leading=15, alignment=TA_CENTER),
    "note": ParagraphStyle("note", fontName=FI, fontSize=9, leading=11, textColor=HexColor("#404040")),
    "hint": ParagraphStyle("hint", fontName=FI, fontSize=10.5, leading=13, textColor=HexColor("#404040")),
    "notec": ParagraphStyle("notec", fontName=FI, fontSize=9, leading=11, alignment=TA_CENTER,
                            textColor=HexColor("#404040")),
    "small": ParagraphStyle("small", fontName=F, fontSize=10, leading=13, spaceAfter=3),
    "smallb": ParagraphStyle("smallb", fontName=FB, fontSize=11, leading=14, spaceAfter=3),
    # drug cards
    "cardname": ParagraphStyle("cardname", fontName=FB, fontSize=15, leading=18),
    "cardlab": ParagraphStyle("cardlab", fontName=FB, fontSize=11, leading=14),
    "cardrec": ParagraphStyle("cardrec", fontName=FB, fontSize=12.5, leading=15.5),
    "cardval": ParagraphStyle("cardval", fontName=F, fontSize=11.5, leading=14),
}
INNER = HexColor("#BFBFBF")


class Rule(Flowable):
    """Thick navy underline used under section headings."""

    def __init__(self, width=CONTENT_W, thickness=2, color=NAVY, space=4):
        super().__init__()
        self.width, self.thickness, self.color, self.space = width, thickness, color, space

    def wrap(self, aw, ah):
        return self.width, self.thickness + self.space

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, self.space, self.width, self.space)


def P(text: str, style: str, bold_glyphs: bool = False) -> Paragraph:
    return Paragraph(esc(text, bold=bold_glyphs), ST[style])


def _heading(text: str) -> list:
    return [P(text, "h1"), Spacer(1, 3), Rule(), Spacer(1, 6)]


def _boxed_row(cells: list, widths: list[float], color, box_width: float = 1.6, pad: float = 4) -> Table:
    t = Table([cells], colWidths=widths)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), box_width, color),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad + 1),
    ]))
    return t


def _header_row(labels: list[str], widths: list[float]) -> Table:
    t = Table([[P(x, "cellb") for x in labels]], colWidths=widths)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, GRID),
        ("LINEABOVE", (0, 0), (-1, 0), 2, NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _cover(summary: Summary) -> list:
    story: list = []
    logo = Image(str(ASSETS / "logo_wide.png"), width=226, height=226 * 438 / 1600)
    story += [logo, Spacer(1, 14), P("PHARMACOGENOMICS REPORT", "title"), Spacer(1, 12)]

    rows = [[P(a, "pcellb"), P(b, "pcell"), P(c, "pcellb"), P(d, "pcell")] for a, b, c, d in patient_rows(summary)]
    widths = [CONTENT_W * w for w in (0.14, 0.36, 0.14, 0.36)]
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [t, Spacer(1, 18)]

    legend_cells = [P("Normal: standard dosing", "legend"), P("Intermediate: adjust or monitor", "legend"),
                    P("Rapid or poor: avoid or change", "legend")]
    lt = Table([legend_cells], colWidths=[CONTENT_W / 3] * 3)
    lt.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, GRID),
        ("LINEBEFORE", (0, 0), (0, 0), 4, TIER_COLOR[GREEN]),
        ("LINEBEFORE", (1, 0), (1, 0), 4, TIER_COLOR[YELLOW]),
        ("LINEBEFORE", (2, 0), (2, 0), 4, TIER_COLOR[RED]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [lt, Spacer(1, 22)]

    story += _heading("How to Read This Report")
    for para in HOW_TO_READ:
        story.append(Paragraph(para, ST["body"]))
    story.append(Paragraph("Report guide", ST["h3"]))
    for label, desc in REPORT_GUIDE(summary):
        story.append(Paragraph(f"<b>{label}:</b> {desc}", ST["bullet"], bulletText="•"))
    story += [Spacer(1, 6), Paragraph(f"<b>{SHARE_NOTE}</b>", ST["body"]), PageBreak()]
    return story


def _key_drugs_para(summary: Summary, gene: str) -> Paragraph:
    """Key-drugs cell: each drug name links to its card in All Medications."""
    parts = []
    for text, anchor in key_drug_segments(summary, gene):
        if anchor:
            parts.append(f'<a href="#{anchor}" color="#{LINK_BLUE}"><u>{esc(text)}</u></a>')
        else:
            parts.append(esc(text))
    return Paragraph("".join(parts), ST["cell"])


def _gene_table(summary: Summary) -> list:
    story = [P("Gene Results", "h1"), Spacer(1, 4), P(LINK_HINT, "hint"), Spacer(1, 6)]
    widths = [CONTENT_W * w for w in (0.155, 0.165, 0.225, 0.455)]
    story.append(_header_row(["Gene", "Genotype", "Phenotype", "Key drugs affected"], widths))
    footnote = False
    for g in summary.genes_sorted:
        pheno = g.phenotype
        if g.name == "CYP3A5" and g.code == "PM":
            pheno += "*"
            footnote = True
        story.append(Spacer(1, 1.5))
        story.append(_boxed_row([P(g.name, "cellb"), P(g.genotype, "cell"), P(pheno, "cellb"),
                                 _key_drugs_para(summary, g.name)], widths, TIER_COLOR[g.tier], pad=1.5))
    if footnote:
        story += [Spacer(1, 4), P("*CYP3A5 *3/*3 is the most common genotype in people of European ancestry "
                                  "and means standard tacrolimus dosing.", "note")]
    story.append(PageBreak())
    return story


def _quick_reference(summary: Summary) -> list:
    story = _heading("Medication Quick Reference")
    heads = [("AVOID OR CHANGE", RED), ("ADJUST OR MONITOR", YELLOW), ("STANDARD DOSING", GREEN)]
    cols = []
    for _, tier in heads:
        col = []
        for cat, rows in summary.by_category((tier,)).items():
            col.append(P(cat, "qrh"))
            col.append(P(", ".join(r.drug.name for r in rows), "qr"))
        if not col:
            col.append(P("None", "qr"))
        cols.append(col)
    w = CONTENT_W / 3
    t = Table([[P(h, "qrhead") for h, _ in heads], cols], colWidths=[w] * 3)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 1), (-1, 1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 1), (-1, 1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i, (_, tier) in enumerate(heads):
        style.append(("LINEBEFORE", (i, 0), (i, 0), 4, TIER_COLOR[tier]))
    t.setStyle(TableStyle(style))
    story += [t, Spacer(1, 4), P(QUICK_REF_NOTE, "note"), PageBreak()]
    return story


def _card(r, bookmark: bool) -> Table:
    """One drug as a vertical card: name/status, recommendation, gene(s) + source."""
    name = esc(r.drug.name)
    if bookmark:
        name = f'<a name="{drug_anchor(r.drug.name)}"/>' + name
    head = Paragraph(f'{name}<font size="10.5">&nbsp;&nbsp;&nbsp;\u2013&nbsp;&nbsp;&nbsp;'
                     f'{STATUS_LABEL[r.tier]}</font>', ST["cardname"])
    genes = Paragraph(f'{esc(", ".join(r.drug.genes))}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
                      f'<font name="{FB}" size="11">Source:</font> {esc(r.source)}', ST["cardval"])
    data = [[head, ""],
            [P("Recommendation", "cardlab"), P(r.rec.text, "cardrec", bold_glyphs=True)],
            [P("Gene(s)", "cardlab"), genes]]
    t = Table(data, colWidths=[1.6 * inch, CONTENT_W - 1.6 * inch])
    t.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BOX", (0, 0), (-1, -1), 1.8, TIER_COLOR[r.tier]),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, INNER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _drug_tables(summary: Summary, tiers, title: str, subtitle: str = "", bookmark: bool = False) -> list:
    """Drugs as vertical cards, grouped by system. bookmark=True makes each card a link target."""
    story = [P(title, "h1c")]
    if subtitle:
        story += [Spacer(1, 2), P(subtitle, "notec")]
    story.append(Spacer(1, 8))
    for cat, rows in summary.by_category(tiers).items():
        heading = [Spacer(1, 6)] + _heading(cat)
        for i, r in enumerate(rows):
            card = [_card(r, bookmark), Spacer(1, 7)]
            # keep each card whole, and keep the category heading with its first card
            story.append(KeepTogether((heading if i == 0 else []) + card))
    return story


def _notes(summary: Summary) -> list:
    story = [CondPageBreak(2 * inch)] + _heading("Limitations & Interpretation Notes")
    story.append(P("Interpretation notes", "smallb"))
    for n in interpretation_notes(summary):
        story.append(Paragraph(esc(n), ST["small"], bulletText="•"))
    return story


def render_full_pdf(summary: Summary, out_path: str | Path) -> Path:
    register_fonts()
    out_path = Path(out_path)
    footer = footer_text(summary)

    def on_page(canv, doc):
        canv.saveState()
        canv.setFont(F, 8)
        canv.setFillColor(FOOT)
        canv.drawCentredString(PAGE_W / 2, 0.42 * inch, f"{footer}  |  Page {doc.page}")
        canv.restoreState()

    doc = SimpleDocTemplate(str(out_path), pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=0.7 * inch,
                            title=f"Pharmacogenomics Report – {summary.report.patient.display_name}",
                            author="Morpheus Precision Health")
    story: list = []
    story += _cover(summary)
    story += _gene_table(summary)
    story += _quick_reference(summary)
    actions = summary.by_category((RED, YELLOW))
    if actions:
        story += _drug_tables(summary, (RED, YELLOW), "ACTION REQUIRED: MEDICATIONS NEEDING ADJUSTMENT",
                              "Red and yellow medications only, grouped by system. Full list of all "
                              "medications follows.")
        story.append(PageBreak())
    story += _drug_tables(summary, (RED, YELLOW, GREEN), "ALL MEDICATIONS: DETAILED RECOMMENDATIONS",
                          bookmark=True)
    story += _notes(summary)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return out_path
