"""Normalize lab-reported genotypes/phenotypes into codes the rules can use.

Codes
-----
Metabolizer genes: UM, RM, NM, IM, PM, IND (indeterminate)
Transporter genes (SLCO1B1, ABCG2): IF, NF, DF, PF
HLA: POS, NEG
F5: NEG, HET, HOM
IFNL3: FAV, UNFAV
VKORC1: LOW (G/G, "low sensitivity"), INT (G/A), HIGH (A/A)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import GeneResult, LabReport

RED, YELLOW, GREEN = "red", "yellow", "green"

# CYP2D6 allele activity values (CPIC). Anything not listed falls back to the lab phenotype.
CYP2D6_ACTIVITY = {
    **dict.fromkeys(["*1", "*2", "*27", "*33", "*34", "*35", "*39", "*45", "*46", "*48", "*53"], 1.0),
    **dict.fromkeys(["*9", "*17", "*29", "*41", "*49", "*50", "*54", "*55", "*59", "*72"], 0.5),
    "*10": 0.25,
    **dict.fromkeys(["*3", "*4", "*5", "*6", "*7", "*8", "*11", "*12", "*13", "*14", "*15",
                     "*16", "*18", "*19", "*20", "*21", "*31", "*36", "*38", "*40", "*42", "*44",
                     "*47", "*51", "*56", "*57", "*62", "*68", "*69", "*92", "*100", "*101",
                     "*114"], 0.0),
}

# CYP2C9 allele activity values (CPIC).
CYP2C9_ACTIVITY = {
    "*1": 1.0, "*9": 1.0,
    **dict.fromkeys(["*2", "*5", "*8", "*11", "*12", "*14", "*29", "*31", "*61"], 0.5),
    **dict.fromkeys(["*3", "*4", "*6", "*13", "*15", "*25", "*35"], 0.0),
}


@dataclass
class Gene:
    """A lab result plus its normalized code."""

    name: str
    genotype: str
    phenotype: str
    code: str
    activity_score: Optional[float] = None

    @property
    def tier(self) -> str:
        return gene_tier(self)

    @property
    def short_label(self) -> str:
        """Lower-case phenotype label for the one-page summary, e.g. 'ultrarapid'."""
        return SHORT_LABELS.get((self.name, self.code)) or SHORT_LABELS.get(self.code, self.phenotype.lower())

    @property
    def genotype_short(self) -> str:
        """Compact genotype for the one-page summary."""
        g = self.genotype
        if self.name.startswith("HLA-"):
            return ""
        if self.name == "DPYD" and self.activity_score is not None:
            return f"AS {self.activity_score:.1f}"
        if re.fullmatch(r"No Variants? Detected", g, re.I):
            return "no var"
        m = re.search(r"\(([ACGT]+/[ACGT]+)\)", g)
        if m:
            return m.group(1)
        return g


SHORT_LABELS = {
    "UM": "ultrarapid", "RM": "rapid", "NM": "normal", "IM": "intermediate", "PM": "poor",
    "IND": "indeterminate", "IF": "increased", "NF": "normal", "DF": "decreased",
    "PF": "poor function", "POS": "POSITIVE", "NEG": "negative", "HET": "heterozygous",
    "HOM": "homozygous", "FAV": "favorable", "UNFAV": "unfavorable", "LOW": "low sensitivity",
    "INT": "intermediate sensitivity", "HIGH": "high sensitivity",
    ("CYP3A5", "PM"): "nonexpresser", ("CYP3A5", "IM"): "expresser", ("CYP3A5", "NM"): "expresser",
    ("NAT2", "PM"): "poor", ("NAT2", "NM"): "rapid",
}


def gene_tier(g: Gene) -> str:
    """Colour of the gene itself (not of any drug)."""
    c = g.code
    if c in ("UM", "PM", "PF", "POS", "HOM", "HIGH"):
        return RED
    if c in ("RM", "IM", "DF", "HET", "UNFAV", "INT", "IND"):
        return YELLOW
    if g.name == "DPYD" and g.activity_score is not None and g.activity_score < 2:
        return RED if g.activity_score <= 0.5 else YELLOW
    return GREEN


def normalize(result: GeneResult) -> Gene:
    name, genotype, pheno = result.gene, result.genotype, result.phenotype
    p = pheno.lower()
    score = None
    if name.startswith("HLA-"):
        code = "POS" if ("positive" in p or "pos" in genotype.lower()) else "NEG"
    elif name == "F5":
        if "normal" in p or genotype.lower().startswith("negative"):
            code = "NEG"
        elif re.search(r"\(A/A\)", genotype) or "homozyg" in genotype.lower() or "highly" in p:
            code = "HOM"
        else:
            code = "HET"
    elif name == "IFNL3":
        code = "UNFAV" if "unfavorable" in p else "FAV"
    elif name == "VKORC1":
        if "high" in p or re.search(r"A/A", genotype):
            code = "HIGH"
        elif "low" in p or "normal" in p or re.fullmatch(r"No Variants? Detected", genotype, re.I):
            code = "LOW"
        else:
            code = "INT"
    elif name in ("SLCO1B1", "ABCG2"):
        if "increased" in p:
            code = "IF"
        elif "decreased" in p:
            code = "DF"
        elif "poor" in p:
            code = "PF"
        else:
            code = "NF"
    else:
        code = _metabolizer_code(p)
        if name == "DPYD":
            m = re.search(r"activity score;?\s*([\d.]+)", p)
            score = float(m.group(1)) if m else {"NM": 2.0, "IM": 1.0, "PM": 0.0}.get(code)
        elif name == "CYP2D6":
            score = diplotype_activity(genotype, CYP2D6_ACTIVITY)
        elif name == "CYP2C9":
            score = diplotype_activity(genotype, CYP2C9_ACTIVITY)
            if score is None:
                score = {"NM": 2.0, "IM": 1.0, "PM": 0.0}.get(code)
    return Gene(name=name, genotype=genotype, phenotype=pheno, code=code, activity_score=score)


def _metabolizer_code(p: str) -> str:
    if "ultra" in p:
        return "UM"
    if "rapid" in p:
        return "RM"
    if "intermediate" in p:
        return "IM"
    if "poor" in p or "slow" in p:
        return "PM"
    if "normal" in p or "extensive" in p:
        return "NM"
    return "IND"


def diplotype_activity(genotype: str, table: dict[str, float]) -> Optional[float]:
    """Sum allele activity values for a single '*a/*b' diplotype; None if unknown."""
    m = re.fullmatch(r"(\*[\w.]+?)(?:x(\d+|N))?/(\*[\w.]+?)(?:x(\d+|N))?", genotype.strip())
    if not m:
        return None
    total = 0.0
    for allele, copies in ((m.group(1), m.group(2)), (m.group(3), m.group(4))):
        base = allele.split(".")[0]  # *4.009 -> *4 (sub-alleles share function)
        if base not in table:
            return None
        n = 1 if copies is None else (2 if copies == "N" else int(copies))
        total += table[base] * n
    return total


class Genotypes:
    """All normalized gene results for one patient."""

    def __init__(self, report: LabReport):
        self.genes: dict[str, Gene] = {k: normalize(v) for k, v in report.genes.items()}

    def __contains__(self, name: str) -> bool:
        return name in self.genes

    def __getitem__(self, name: str) -> Gene:
        return self.genes[name]

    def code(self, name: str) -> Optional[str]:
        g = self.genes.get(name)
        return g.code if g else None

    def score(self, name: str) -> Optional[float]:
        g = self.genes.get(name)
        return g.activity_score if g else None
