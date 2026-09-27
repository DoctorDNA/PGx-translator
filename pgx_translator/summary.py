"""Build the view model shared by the one-page summary and the full report."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import LabReport
from .phenotypes import GREEN, RED, YELLOW, Gene, Genotypes
from .rules import CATEGORIES, TIER_ORDER, DrugResult, evaluate

# One-page cards, in display order. Drugs in a card that end up with the same tier and
# short text are shown together; the rest split into their own cards.
ONE_PAGE_CARDS: list[tuple[str, ...]] = [
    ("Voriconazole",),
    ("Citalopram", "Escitalopram"),
    ("Amitriptyline", "Clomipramine", "Doxepin", "Imipramine", "Trimipramine"),
    ("Simvastatin", "Lovastatin"),
    ("Omeprazole", "Lansoprazole", "Pantoprazole", "Dexlansoprazole"),
    ("Atomoxetine",),
    ("Hydralazine",),
    ("Nortriptyline", "Desipramine"),
    ("Efavirenz",),
    ("Atorvastatin",),
    ("Paroxetine",),
    ("Rosuvastatin",),
    ("Tramadol", "Codeine", "Hydrocodone"),
    ("Pitavastatin",),
    ("Tamoxifen",),
    ("Warfarin",),
    ("Clopidogrel",),
    ("Fluorouracil", "Capecitabine", "Tegafur"),
    ("Sertraline", "Fluvoxamine", "Venlafaxine", "Vortioxetine"),
    ("Azathioprine", "Mercaptopurine", "Thioguanine"),
    ("Metoprolol", "Methadone", "Tacrolimus"),
    ("Carbamazepine", "Oxcarbazepine"),
    ("Celecoxib", "Ibuprofen", "Flurbiprofen", "Meloxicam", "Piroxicam", "Tenoxicam", "Lornoxicam"),
    ("Allopurinol", "Abacavir"),
    ("Phenytoin", "Fosphenytoin"),
    ("Atazanavir",),
    ("Pravastatin",),
]
# Listed on one line in the footer while green; promoted to a card otherwise.
NO_CHANGE_LINE = ["Ondansetron", "Tropisetron", "Oxycodone", "Midazolam", "Fentanyl", "Fluoxetine",
                  "Morphine", "Hydromorphone", "Fluvastatin"]
# Not on the one-page unless flagged red/yellow.
FLAGGED_ONLY = ["Estrogen-containing therapy", "Irinotecan"]

# Order of genes in the one-page "flagged genes" strip.
GENE_PRIORITY = ["CYP2C19", "CYP2D6", "CYP2C9", "CYP2B6", "NAT2", "SLCO1B1", "CYP3A5", "CYP3A4", "DPYD",
                 "TPMT", "NUDT15", "UGT1A1", "VKORC1", "ABCG2", "HLA-B*15:02", "HLA-A*31:01",
                 "HLA-B*57:01", "HLA-B*58:01", "F5", "IFNL3", "CYP4F2"]


@dataclass
class Card:
    title: str
    short: str
    genotype_line: str
    tier: str


@dataclass
class Summary:
    report: LabReport
    genotypes: Genotypes
    results: list[DrugResult]
    cards: dict[str, list[Card]] = field(default_factory=dict)
    no_change: list[str] = field(default_factory=list)

    @property
    def flagged_genes(self) -> list[Gene]:
        genes = [g for g in self.genotypes.genes.values() if g.tier != GREEN]
        return sorted(genes, key=lambda g: GENE_PRIORITY.index(g.name) if g.name in GENE_PRIORITY else 99)

    @property
    def genes_sorted(self) -> list[Gene]:
        """Gene-table order: flagged genes first, each group alphabetical."""
        return sorted(self.genotypes.genes.values(), key=lambda g: (g.tier == GREEN, g.name))

    def by_category(self, tiers=(RED, YELLOW, GREEN)) -> dict[str, list[DrugResult]]:
        out: dict[str, list[DrugResult]] = {}
        for cat in CATEGORIES:
            rows = [r for r in self.results if r.drug.category == cat and r.tier in tiers]
            if rows:
                out[cat] = rows
        return out


def build_summary(report: LabReport) -> Summary:
    gt = Genotypes(report)
    results = evaluate(gt)
    s = Summary(report=report, genotypes=gt, results=results)
    by_name = {r.drug.name: r for r in results}
    s.cards = {RED: [], YELLOW: [], GREEN: []}

    card_defs = list(ONE_PAGE_CARDS)
    for name in NO_CHANGE_LINE:
        r = by_name.get(name)
        if r is None:
            continue
        if r.tier == GREEN:
            s.no_change.append(name.lower())
        else:
            card_defs.append((name,))
    for name in FLAGGED_ONLY:
        r = by_name.get(name)
        if r is not None and r.tier != GREEN:
            card_defs.append((name,))

    for names in card_defs:
        present = [by_name[n] for n in names if n in by_name]
        groups: dict[tuple[str, str], list[DrugResult]] = {}
        for r in present:
            groups.setdefault((r.tier, r.rec.short), []).append(r)
        for (tier, short), rs in groups.items():
            s.cards[tier].append(Card(title=_card_title(rs), short=short,
                                      genotype_line=_genotype_line(rs, gt), tier=tier))
    return s


def _card_title(rs: list[DrugResult]) -> str:
    names = [r.drug.one_page_name for r in rs]
    return " · ".join([names[0]] + [n if n.isupper() or "-" in n[:3] else n.lower() for n in names[1:]])


def _gene_token(g: Gene, with_label: bool) -> str:
    if g.name.startswith("HLA-"):
        return f"{g.name} {g.short_label}" if with_label else g.name
    return f"{g.name} {g.genotype_short}".strip()


def _gene_set_line(genes: list[Gene], show_as: bool = False) -> str:
    if len(genes) == 1:
        g = genes[0]
        if g.name.startswith("HLA-"):
            return f"{g.name} · {g.short_label}"
        if show_as and g.activity_score is not None:
            return f"{_gene_token(g, False)} · AS {g.activity_score:.1f}"
        return f"{_gene_token(g, False)} · {g.short_label}"
    labels = {g.short_label for g in genes}
    if len(labels) == 1:
        return "; ".join(_gene_token(g, False) for g in genes) + f" · {labels.pop()}"
    return "; ".join(_gene_token(g, True) for g in genes)


def _genotype_line(rs: list[DrugResult], gt: Genotypes) -> str:
    show_as = any(r.drug.name == "Tamoxifen" for r in rs)
    gene_sets: dict[tuple[str, ...], list[str]] = {}
    for r in rs:
        gene_sets.setdefault(r.drug.genes, []).append(r.drug.one_page_name)
    if len(gene_sets) == 1:
        genes = [gt[n] for n in next(iter(gene_sets))]
        return _gene_set_line(genes, show_as)

    union = list(dict.fromkeys(n for genes in gene_sets for n in genes))
    if all(n.startswith("HLA-") for n in union):
        genes = [gt[n] for n in union]
        labels = {g.short_label for g in genes}
        if len(labels) == 1:
            return " / ".join(union) + f" · {labels.pop()}"
        return "; ".join(f"{g.name} {g.short_label}" for g in genes)

    # Different gene sets: "Sertraline: CYP2C19 *17/*17 + CYP2B6 *1/*7; others: CYP2D6 *1/*5"
    items = sorted(gene_sets.items(), key=lambda kv: len(kv[1]))
    parts = []
    for i, (genes, drug_names) in enumerate(items):
        tokens = " + ".join(_gene_token(gt[n], True) for n in genes)
        is_last = i == len(items) - 1
        who = "others" if (is_last and len(drug_names) > 1) else " · ".join(drug_names)
        if i > 0 and who[:1].isupper() and not who.isupper():
            who = who.lower()
        parts.append(f"{who}: {tokens}")
    line = "; ".join(parts)
    return line[0].upper() + line[1:]


def tier_sort_key(r: DrugResult) -> int:
    return TIER_ORDER[r.tier]
