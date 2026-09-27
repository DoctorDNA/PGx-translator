"""Parse a Quest Diagnostics "Pharmacogenomics Panel" PDF into a LabReport.

The parser works on the plain text that pdfplumber extracts, so ``parse_text`` can
be unit-tested without a PDF. Only the "Test Results" table and the patient /
specimen header are read; the methodology boilerplate is ignored.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .models import GeneResult, LabReport, Patient

# Genes on the Quest PGx panel, in report order. Rows for genes not listed here are
# still picked up by the generic pattern below.
KNOWN_GENES = [
    "ABCG2", "CYP2B6", "CYP2C9", "CYP2C19", "CYP2D6", "CYP3A4", "CYP3A5", "CYP4F2",
    "DPYD", "F5", "HLA-A*31:01", "HLA-B*15:02", "HLA-B*57:01", "HLA-B*58:01", "IFNL3",
    "NAT2", "NUDT15", "SLCO1B1", "TPMT", "UGT1A1", "VKORC1",
]

NAME_SUFFIXES = {"MD", "DO", "PHD", "NP", "PA", "PA-C", "RN", "DDS", "DMD", "PHARMD",
                 "JR", "SR", "II", "III", "IV", "DC", "DPM", "OD", "APRN", "FNP"}

_STAR = r"\*[\w.]+(?:x(?:\d+|N))?"
_GENOTYPE_RE = re.compile(
    r"^(?:"
    r"No Variants? Detected"
    r"|(?:Negative|Positive|Heterozygous|Homozygous)\s*\([ACGT]+/[ACGT]+\)"
    r"|c\.\S+\s*\([ACGT]+/[ACGT]+\)"
    r"|(?:Neg|Pos)/(?:Neg|Pos)"
    rf"|{_STAR}/{_STAR}(?:\s+or\s+{_STAR}/{_STAR})*"
    r"|[ACGT]+/[ACGT]+"
    r"|\S+"
    r")"
)
_PHENOTYPE_RE = re.compile(
    r"^(?:"
    r"(?:(?:Likely|Possible)\s+)?(?:Ultra-?\s?[Rr]apid|Rapid|Normal|Intermediate|Poor|Indeterminate)"
    r"(?:/\w+)?\s+Metabolizer(?:\s*\(Activity Score;?\s*[\d.]+\))?"
    r"|(?:Possible\s+)?(?:Increased|Normal|Decreased|Poor)\s+Function"
    r"|(?:Normal|Increased|Moderately Increased|Highly Increased|High|Moderate)\s+Thrombosis Risk"
    r"|(?:Favorable|Unfavorable)\s+Response Genotype"
    r"|(?:Low|Normal|Moderate|Intermediate|High|Increased)\s+Sensitivity to Warfarin"
    r"|(?:Rapid|Intermediate|Slow)\s+Acetylator"
    r"|Negative|Positive|Indeterminate"
    r")",
    re.IGNORECASE,
)
_GENE_ROW_RE = re.compile(r"^(HLA-[A-Z]+\*\d+:\d+|[A-Z][A-Z0-9]{1,7})\s+(.*)$")
_NOT_GENES = {"SIGNATURE", "CLIENT", "PAGE", "REPORT", "COMMENTS", "GENE", "PERFORMING"}


def parse_pdf(path: str | Path) -> LabReport:
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    return parse_text(text)


def parse_text(text: str) -> LabReport:
    report = LabReport(patient=_parse_patient(text))
    report.specimen = _search(r"Specimen:\s*(\S+)", text)
    report.collected = _parse_date(_search(r"Collected:\s*(\d{1,2}/\d{1,2}/\d{4})", text))
    report.received = _parse_date(_search(r"Received:\s*(\d{1,2}/\d{1,2}/\d{4})", text))
    report.reported = _parse_date(_search(r"Reported:\s*(\d{1,2}/\d{1,2}/\d{4})", text))
    report.reporting_id = _search(r"REPORTING ID\s*:\s*(\S+)", text)
    report.cls_url = _search(r"(https?://\S*genedose\S*)", text)
    title = _search(r"^(PHARMACOGENOMICS[^\n]*)$", text, re.MULTILINE)
    report.test_name = _nice_test_name(title)
    report.genes = _parse_gene_table(text)
    if not report.genes:
        raise ValueError(
            "No gene results found. Is this a Quest Pharmacogenomics Panel report "
            "with a 'Test Results' table?"
        )
    return report


def _search(pattern: str, text: str, flags: int = 0) -> str:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else ""


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    return datetime.strptime(s, "%m/%d/%Y").date()


def _nice_test_name(title: str) -> str:
    if not title:
        return "Quest Pharmacogenomics Panel"
    t = title.title().replace("W/Cls", "w/ CLS").replace("Cls", "CLS")
    return f"Quest {t}"


def _parse_patient(text: str) -> Patient:
    p = Patient()
    # The patient name is the line right after "Report Status: ...", as "LAST [SUFFIX], FIRST".
    m = re.search(r"Report Status:[^\n]*\n([^\n]+)", text)
    if m:
        raw = m.group(1).strip()
        last, _, first = raw.partition(",")
        last_tokens = last.split()
        suffix = []
        while len(last_tokens) > 1 and last_tokens[-1].upper().replace(".", "") in NAME_SUFFIXES:
            suffix.insert(0, last_tokens.pop().replace(".", ""))
        first_tokens = first.split()
        while len(first_tokens) > 1 and first_tokens[-1].upper().replace(".", "") in NAME_SUFFIXES:
            suffix.insert(0, first_tokens.pop().replace(".", ""))
        p.last_name = " ".join(last_tokens)
        p.first_name = " ".join(first_tokens)
        p.suffix = " ".join(s.upper() for s in suffix)
    p.dob = _parse_date(_search(r"DOB:\s*(\d{1,2}/\d{1,2}/\d{4})", text))
    sex = _search(r"(?:Gender|Sex):\s*(\w+)", text).upper()
    p.sex = {"M": "Male", "MALE": "Male", "F": "Female", "FEMALE": "Female"}.get(sex, sex.title())
    return p


def _parse_gene_table(text: str) -> dict[str, GeneResult]:
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().startswith("Test Results"))
    except StopIteration:
        start = 0
    genes: dict[str, GeneResult] = {}
    current: Optional[GeneResult] = None
    for line in lines[start + 1:]:
        s = line.strip()
        if not s:
            continue
        if s.startswith(("SIGNATURE", "CLIENT SERVICES", "PAGE ", "Quest, Quest Diagnostics")):
            if current is not None:
                current = None
            if s.startswith("SIGNATURE"):
                break
            continue
        row = _match_gene_row(s)
        if row:
            gene, rest = row
            current = _parse_gene_row(gene, rest)
            genes[gene] = current
        elif current is not None:
            current.alleles_tested = f"{current.alleles_tested} {s}".strip()
    return genes


def _match_gene_row(s: str) -> Optional[tuple[str, str]]:
    for gene in sorted(KNOWN_GENES, key=len, reverse=True):
        if s.startswith(gene + " "):
            return gene, s[len(gene) + 1:].strip()
    m = _GENE_ROW_RE.match(s)
    if m and m.group(1) not in _NOT_GENES:
        rest = m.group(2)
        # Require something that looks like a genotype + phenotype after the gene name.
        g = _GENOTYPE_RE.match(rest)
        if g and _PHENOTYPE_RE.match(rest[g.end():].strip()):
            return m.group(1), rest
    return None


def _parse_gene_row(gene: str, rest: str) -> GeneResult:
    g = _GENOTYPE_RE.match(rest)
    genotype = g.group(0) if g else ""
    after = rest[len(genotype):].strip()
    p = _PHENOTYPE_RE.match(after)
    if p:
        phenotype = p.group(0)
        alleles = after[p.end():].strip()
    else:
        # Fall back to everything before the first allele-looking token.
        m = re.search(r"\s(?=\*|c\.|rs\d)", after)
        phenotype = after[: m.start()].strip() if m else after
        alleles = after[m.start():].strip() if m else ""
    return GeneResult(gene=gene, genotype=genotype.strip(), phenotype=_clean_phenotype(phenotype),
                      alleles_tested=alleles)


def _clean_phenotype(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?i)ultra-?\s?rapid", "Ultra-Rapid", s)
    return s
