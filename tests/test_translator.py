from pathlib import Path

import pytest

from pgx_translator.full_docx import render_full_docx
from pgx_translator.full_pdf import render_full_pdf
from pgx_translator.onepage import render_one_page
from pgx_translator.phenotypes import GREEN, RED, YELLOW, CYP2D6_ACTIVITY, diplotype_activity
from pgx_translator.quest_parser import parse_text
from pgx_translator.rules import DRUGS
from pgx_translator.summary import build_summary

FIXTURE = (Path(__file__).parent / "fixtures" / "quest_sample.txt").read_text()


@pytest.fixture(scope="module")
def report():
    return parse_text(FIXTURE)


def with_genes(report, **changes):
    """Copy of the sample with some rows replaced: gene=(genotype, phenotype)."""
    text = FIXTURE
    for gene, (geno, pheno) in changes.items():
        gene = gene.replace("_", "-", 1).replace("_", "*", 1).replace("_", ":") if gene.startswith("HLA") else gene
        old = next(l for l in text.splitlines() if l.startswith(gene + " "))
        text = text.replace(old, f"{gene} {geno} {pheno}")
    return parse_text(text)


def tiers(report):
    return {r.drug.name: r.tier for r in build_summary(report).results}


def test_patient_and_specimen(report):
    p = report.patient
    assert (p.first_name, p.last_name, p.suffix) == ("PAT", "SAMPLE", "")
    assert p.display_name == "Pat Sample"
    assert p.dob.isoformat() == "1980-01-02" and p.sex == "Male"
    assert report.specimen == "XX000000X"
    assert report.collected.isoformat() == "2026-09-18"
    assert report.reported.isoformat() == "2026-09-25"


def test_all_21_genes_parsed(report):
    assert len(report.genes) == 21
    g = report.genes
    assert (g["CYP2C19"].genotype, g["CYP2C19"].phenotype) == ("*17/*17", "Ultra-Rapid Metabolizer")
    assert g["DPYD"].phenotype == "Normal Metabolizer (Activity Score; 2.0)"
    assert (g["F5"].genotype, g["F5"].phenotype) == ("Negative (G/G)", "Normal Thrombosis Risk")
    assert g["ABCG2"].genotype == "c.421C>A (C/C)"
    assert g["HLA-B*57:01"].phenotype == "Negative"
    assert "XN(gene duplication)" in g["CYP2D6"].alleles_tested  # continuation lines joined


def test_suffix_parsing():
    r = parse_text(FIXTURE.replace("SAMPLE, PAT", "REID DO, JEFF"))
    assert r.patient.display_name == "Jeff Reid, DO"
    assert r.patient.file_stub == "Jeff_Reid"


def test_sample_tiers_match_reference(report):
    t = tiers(report)
    expected = {
        "Voriconazole": RED, "Citalopram": RED, "Amitriptyline": RED, "Simvastatin": RED, "Lovastatin": RED,
        "Omeprazole": YELLOW, "Hydralazine": YELLOW, "Efavirenz": YELLOW, "Paroxetine": YELLOW,
        "Tramadol": YELLOW, "Codeine": YELLOW, "Hydrocodone": YELLOW, "Tamoxifen": YELLOW,
        "Atomoxetine": YELLOW, "Nortriptyline": YELLOW, "Atorvastatin": YELLOW, "Rosuvastatin": YELLOW,
        "Pitavastatin": YELLOW, "Warfarin": YELLOW,
        "Clopidogrel": GREEN, "Sertraline": GREEN, "Metoprolol": GREEN, "Tacrolimus": GREEN,
        "Fluorouracil": GREEN, "Azathioprine": GREEN, "Carbamazepine": GREEN, "Allopurinol": GREEN,
        "Celecoxib": GREEN, "Phenytoin": GREEN, "Atazanavir": GREEN, "Pravastatin": GREEN,
        "Ondansetron": GREEN,
    }
    assert {k: t[k] for k in expected} == expected
    assert len(t) == len(DRUGS)


def test_other_phenotypes(report):
    r = with_genes(report,
                   CYP2C19=("*2/*2", "Poor Metabolizer"),
                   CYP2D6=("*1/*1xN", "Ultra-Rapid Metabolizer"),
                   SLCO1B1=("*5/*5", "Poor Function"),
                   DPYD=("c.1905+1G>A (G/A)", "Intermediate Metabolizer (Activity Score; 1.0)"),
                   HLA_B_15_02=("Pos/Neg", "Positive"),
                   TPMT=("*1/*3A", "Intermediate Metabolizer"))
    t = tiers(r)
    assert t["Clopidogrel"] == RED
    assert t["Codeine"] == RED and t["Tramadol"] == RED
    assert t["Ondansetron"] == RED
    assert t["Simvastatin"] == RED and t["Atorvastatin"] == YELLOW
    assert t["Fluorouracil"] == YELLOW
    assert t["Carbamazepine"] == RED and t["Phenytoin"] == RED and t["Oxcarbazepine"] == RED
    assert t["Azathioprine"] == YELLOW
    s = build_summary(r)
    assert "ondansetron" not in s.no_change
    assert any("Ondansetron" in c.title for c in s.cards[RED])


def test_activity_scores():
    assert diplotype_activity("*1/*5", CYP2D6_ACTIVITY) == 1.0
    assert diplotype_activity("*1x2/*4", CYP2D6_ACTIVITY) == 2.0
    assert diplotype_activity("*10/*41", CYP2D6_ACTIVITY) == 0.75
    assert diplotype_activity("*999/*1", CYP2D6_ACTIVITY) is None


def test_one_page_cards(report):
    s = build_summary(report)
    titles = {c.title: c for cs in s.cards.values() for c in cs}
    assert titles["Tramadol · codeine · hydrocodone"].genotype_line == "CYP2D6 *1/*5 · intermediate"
    assert titles["Warfarin"].genotype_line == "CYP2C9 *1/*1; VKORC1 no var; CYP4F2 *1/*1"
    assert titles["Tamoxifen"].genotype_line == "CYP2D6 *1/*5 · AS 1.0"
    assert titles["Carbamazepine · oxcarbazepine"].genotype_line == "HLA-B*15:02 / HLA-A*31:01 · negative"
    assert [g.name for g in s.flagged_genes][:3] == ["CYP2C19", "CYP2D6", "CYP2B6"]


def test_renderers(report, tmp_path):
    s = build_summary(report)
    for fn, name in ((render_one_page, "one.pdf"), (render_full_pdf, "full.pdf"), (render_full_docx, "full.docx")):
        out = fn(s, tmp_path / name)
        assert out.stat().st_size > 10_000
    import pdfplumber
    with pdfplumber.open(tmp_path / "one.pdf") as pdf:
        assert len(pdf.pages) == 1
        text = pdf.pages[0].extract_text()
    assert "PAT SAMPLE" in text and "Voriconazole" in text
