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
        "Atomoxetine": GREEN, "Nortriptyline": YELLOW, "Atorvastatin": YELLOW, "Rosuvastatin": GREEN,
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


def test_full_report_links(report, tmp_path):
    """Gene Results drug names link to bookmarked drug cards in both full reports."""
    import zipfile
    from pgx_translator.report_text import drug_anchor
    s = build_summary(report)
    docx_path = render_full_docx(s, tmp_path / "r.docx")
    xml = zipfile.ZipFile(docx_path).read("word/document.xml").decode()
    assert xml.count("<w:hyperlink") >= 40
    assert f'w:name="{drug_anchor("Omeprazole")}"' in xml
    assert xml.count("w:bookmarkStart") == len(s.results)  # one target per drug card
    pdf_path = render_full_pdf(s, tmp_path / "r.pdf")
    data = pdf_path.read_bytes()
    assert data.count(b"/Subtype /Link") >= 40


def test_atomoxetine_cpic_2019(report):
    """AS 1.0 without *10 is dosed like a normal metabolizer; *10 or AS 0.5 gets the slow schedule."""
    def rec(geno, pheno):
        r = with_genes(report, CYP2D6=(geno, pheno))
        return next(x.rec for x in build_summary(r).results if x.drug.name == "Atomoxetine")
    assert rec("*1/*5", "Intermediate Metabolizer").tier == GREEN
    slow = rec("*10/*41", "Intermediate Metabolizer")
    assert slow.tier == YELLOW and "after 2 weeks, increase to 80 mg/day" in slow.text
    assert rec("*4/*41", "Intermediate Metabolizer").tier == YELLOW
    assert rec("*4/*4", "Poor Metabolizer").tier == YELLOW
    assert rec("*1/*1", "Normal Metabolizer").tier == GREEN


def test_tca_cpic_2016(report):
    def rec(drug, **genes):
        r = with_genes(report, **genes)
        return next(x.rec for x in build_summary(r).results if x.drug.name == drug)
    pm = rec("Amitriptyline", CYP2D6=("*4/*4", "Poor Metabolizer"), CYP2C19=("*1/*1", "Normal Metabolizer"))
    assert pm.tier == RED and "50% reduction" in pm.text and "neuropathic pain" in pm.text
    assert rec("Amitriptyline", CYP2D6=("*1/*1", "Normal Metabolizer"),
               CYP2C19=("*1/*2", "Intermediate Metabolizer")).tier == GREEN
    assert "higher target dose" in rec("Nortriptyline", CYP2D6=("*1/*1xN", "Ultra-Rapid Metabolizer")).text


def _rec(report, drug, **genes):
    r = with_genes(report, **genes) if genes else report
    return next(x.rec for x in build_summary(r).results if x.drug.name == drug)


def test_thiopurines_cpic_2025(report):
    single = _rec(report, "Mercaptopurine", TPMT=("*1/*3A", "Intermediate Metabolizer"))
    assert single.tier == YELLOW and "30–80%" in single.text
    compound = _rec(report, "Azathioprine", TPMT=("*1/*3A", "Intermediate Metabolizer"),
                    NUDT15=("*1/*3", "Intermediate Metabolizer"))
    assert compound.tier == YELLOW and "20–50%" in compound.text
    pm_aza = _rec(report, "Azathioprine", NUDT15=("*3/*3", "Poor Metabolizer"))
    assert pm_aza.tier == RED and "nonthiopurine" in pm_aza.text
    pm_tg = _rec(report, "Thioguanine", TPMT=("*3A/*3A", "Poor Metabolizer"))
    assert "10-fold" in pm_tg.text and "Nonmalignancy" not in pm_tg.text


def test_clopidogrel_cpic_2022(report):
    pm = _rec(report, "Clopidogrel", CYP2C19=("*2/*2", "Poor Metabolizer"))
    assert pm.tier == RED and "prasugrel is contraindicated with a history of stroke" in pm.text
    assert _rec(report, "Clopidogrel").tier == GREEN  # sample is *17/*17


def test_opioids_cpic_2021(report):
    um = _rec(report, "Codeine", CYP2D6=("*1/*1xN", "Ultra-Rapid Metabolizer"))
    assert um.tier == RED and "non-tramadol opioid" in um.text
    assert "non-codeine opioid" in _rec(report, "Tramadol", CYP2D6=("*4/*4", "Poor Metabolizer")).text
    assert _rec(report, "Hydrocodone", CYP2D6=("*1/*1xN", "Ultra-Rapid Metabolizer")).tier == GREEN


def test_dpyd_cpic_2017(report):
    as15 = _rec(report, "Capecitabine", DPYD=("c.2846A>T (A/T)", "Intermediate Metabolizer (Activity Score; 1.5)"))
    assert as15.tier == YELLOW and "25% to 50%" in as15.text
    as1 = _rec(report, "Fluorouracil", DPYD=("c.1905+1G>A (G/A)", "Intermediate Metabolizer (Activity Score; 1.0)"))
    assert "by 50%" in as1.text
    as0 = _rec(report, "Fluorouracil", DPYD=("c.1905+1G>A (A/A)", "Poor Metabolizer (Activity Score; 0.0)"))
    assert as0.tier == RED and "strongly reduced" not in as0.text


def test_efavirenz_and_dapsone(report):
    assert "400 or 200 mg/day" in _rec(report, "Efavirenz", CYP2B6=("*6/*6", "Poor Metabolizer")).text
    assert "G6PD" in _rec(report, "Dapsone").text


def test_batch4_cpic(report):
    hyd_im = _rec(report, "Hydralazine", NAT2=("*4/*5", "Intermediate Metabolizer"))
    assert hyd_im.tier == YELLOW and "at least 75 mg" in hyd_im.text
    assert "40–75 mg" in _rec(report, "Hydralazine").text  # sample NAT2 poor
    assert _rec(report, "Methadone", CYP2B6=("*6/*6", "Poor Metabolizer")).tier == GREEN
    assert "No CPIC recommendation" in _rec(report, "Metoprolol", CYP2D6=("*1/*1xN", "Ultra-Rapid Metabolizer")).text
    ond_pm = _rec(report, "Ondansetron", CYP2D6=("*4/*4", "Poor Metabolizer"))
    assert ond_pm.tier == GREEN and "No CPIC recommendation" in ond_pm.text
    cel_pm = _rec(report, "Celecoxib", CYP2C9=("*3/*3", "Poor Metabolizer"))
    assert cel_pm.tier == YELLOW and "8 days" in cel_pm.text
    assert _rec(report, "Meloxicam", CYP2C9=("*3/*3", "Poor Metabolizer")).tier == RED
    assert _rec(report, "Piroxicam", CYP2C9=("*1/*3", "Intermediate Metabolizer")).tier == RED
    assert "CYP2C8*3" in _rec(report, "Ibuprofen", CYP2C9=("*1/*2", "Intermediate Metabolizer")).text


def test_batch5_cpic(report):
    # PPIs (2020): rapid metabolizers standard start; poor metabolizers standard start, 50% for chronic use
    assert _rec(report, "Omeprazole", CYP2C19=("*1/*17", "Rapid Metabolizer")).tier == GREEN
    assert "50% reduction" in _rec(report, "Omeprazole", CYP2C19=("*2/*2", "Poor Metabolizer")).text
    # Phenytoin (2020): AS 1.5 needs no adjustment; AS 1 = 25% lower maintenance
    assert _rec(report, "Phenytoin", CYP2C9=("*1/*2", "Intermediate Metabolizer")).tier == GREEN
    assert "25% less" in _rec(report, "Phenytoin", CYP2C9=("*1/*3", "Intermediate Metabolizer")).text
    # Statins (2022), Tables 5-6
    assert _rec(report, "Rosuvastatin").tier == GREEN  # SLCO1B1 DF + ABCG2 normal
    assert "≤20 mg" in _rec(report, "Rosuvastatin", SLCO1B1=("*5/*5", "Poor Function")).text
    assert "≤10 mg" in _rec(report, "Rosuvastatin", ABCG2=("c.421C>A (A/A)", "Poor Function")).text
    assert _rec(report, "Fluvastatin", CYP2C9=("*3/*3", "Poor Metabolizer")).tier == RED  # with SLCO1B1 DF
    assert "≤20 mg" in _rec(report, "Fluvastatin", CYP2C9=("*1/*3", "Intermediate Metabolizer")).text
    # Sertraline (2023), Table 5
    assert _rec(report, "Sertraline").tier == GREEN  # CYP2C19 UM + CYP2B6 IM
    both_pm = _rec(report, "Sertraline", CYP2C19=("*2/*2", "Poor Metabolizer"), CYP2B6=("*6/*6", "Poor Metabolizer"))
    assert both_pm.tier == RED
    nm_pm = _rec(report, "Sertraline", CYP2C19=("*1/*1", "Normal Metabolizer"), CYP2B6=("*6/*6", "Poor Metabolizer"))
    assert "25% reduction" in nm_pm.text
    # SSRIs/SNRIs CYP2D6 (2023)
    assert _rec(report, "Venlafaxine", CYP2D6=("*4/*4", "Poor Metabolizer")).tier == RED
    assert _rec(report, "Vortioxetine", CYP2D6=("*1/*1xN", "Ultra-Rapid Metabolizer")).tier == RED


def test_final_batch_cpic(report):
    assert _rec(report, "Voriconazole", CYP2C19=("*1/*17", "Rapid Metabolizer")).tier == RED
    pm = _rec(report, "Voriconazole", CYP2C19=("*2/*2", "Poor Metabolizer"))
    assert "lower than standard dose" in pm.text
    im = _rec(report, "Tamoxifen")  # sample *1/*5, AS 1.0
    assert im.tier == YELLOW and "aromatase inhibitor" in im.text
    assert _rec(report, "Tamoxifen", CYP2D6=("*4/*4", "Poor Metabolizer")).tier == RED
    assert "0.3 mg/kg/day" in _rec(report, "Tacrolimus", CYP3A5=("*1/*3", "Intermediate Metabolizer")).text


# ---------------------------------------------------------------- patient medications

def test_medication_matching():
    from pgx_translator.medications import match_entry, split_entries
    assert match_entry("Lipitor 40 mg daily").names == ["Atorvastatin"]
    assert match_entry("Tylenol #3").names == ["Codeine"]
    assert set(match_entry("hydrocodone/acetaminophen 5/325").names) == {"Hydrocodone", "Acetaminophen"}
    assert match_entry("5-FU").names == ["Fluorouracil"]
    typo = match_entry("atorvastatn")
    assert typo.names == ["Atorvastatin"] and typo.fuzzy
    from pgx_translator.medications import NON_CPIC
    for other in ["lisinopril", "metformin", "trazodone", "hydroxyzine", "clonidine", "amlodipine", "gabapentin"]:
        names = match_entry(other).names
        assert names and all(n in NON_CPIC for n in names), (other, names)  # never mistaken for a CPIC drug
    assert match_entry("xylophonazine").names == []
    assert match_entry("vitamin D3").names == ["Vitamin D"]
    assert split_entries("a, b; c\nd") == ["a", "b", "c", "d"]


def test_patient_meds_in_summary(report):
    s = build_summary(report, ["Lipitor 40 mg", "sertraline", "sevoflurane", "naproxen", "xylophonazine"])
    kinds = {m.display_name: (m.kind, m.tier) for m in s.patient_meds}
    assert kinds["Atorvastatin"] == ("rule", YELLOW)
    assert kinds["Sertraline"] == ("rule", GREEN)
    assert kinds["Sevoflurane"][0] == "untested"
    assert kinds["Naproxen"][0] == "norec"
    assert kinds["xylophonazine"][0] == "unknown"
    assert [m.display_name for m in s.patient_meds][0] == "Atorvastatin"  # actionable first
    assert {"SLCO1B1", "CYP2C19", "CYP2B6"} <= s.patient_genes
    assert any(c.patient and "Atorvastatin" in c.drugs for c in s.cards[YELLOW])


def test_patient_meds_rendered(report, tmp_path):
    import zipfile
    import pdfplumber
    s = build_summary(report, ["Plavix 75", "Prilosec"])
    one = render_one_page(s, tmp_path / "one.pdf")
    with pdfplumber.open(one) as pdf:
        assert len(pdf.pages) == 1
        text = pdf.pages[0].extract_text()
    assert "PATIENT MEDICATIONS" in text and "Clopidogrel (Plavix 75)" in text
    full = render_full_pdf(s, tmp_path / "full.pdf")
    with pdfplumber.open(full) as pdf:
        assert "Patient Medications" in pdf.pages[0].extract_text()
        assert "CURRENT MEDICATION" in "".join(p.extract_text() or "" for p in pdf.pages)
    xml = zipfile.ZipFile(render_full_docx(s, tmp_path / "r.docx")).read("word/document.xml").decode()
    assert "Patient Medications" in xml and "CURRENT MEDICATION" in xml


def test_web_check_endpoint():
    pytest.importorskip("flask")
    from pgx_translator.web import app
    c = app.test_client()
    assert c.get("/check?q=Zoloft").json["cls"] == "ok"
    assert c.get("/check?q=lisinopril").json["cls"] == "none"


def test_owner_medication_list(report):
    """The owner's own list, entered without doses: citalopram, rosuvastatin, omeprazole, olmesartan
    (typed 'Olmasartan'), Pepcid."""
    s = build_summary(report, ["Citalopram", "Rosuvastatin", "Omeprazole", "Olmasartan", "pepcid"])
    got = {m.display_name: (m.kind, m.tier, m.fuzzy) for m in s.patient_meds}
    assert got["Citalopram"] == ("rule", RED, False)  # CYP2C19 ultrarapid
    assert got["Omeprazole"] == ("rule", YELLOW, False)  # CYP2C19 ultrarapid: increase dose 100%
    assert got["Rosuvastatin"] == ("rule", GREEN, False)  # SLCO1B1 decreased + ABCG2 normal
    assert got["Olmesartan"] == ("none", "grey", True)  # misspelling corrected, flagged
    assert got["Famotidine"] == ("none", "grey", False)  # Pepcid
    assert [m.display_name for m in s.patient_meds][:3] == ["Citalopram", "Omeprazole", "Rosuvastatin"]
    assert s.patient_genes == {"CYP2C19", "SLCO1B1", "ABCG2"}


def test_one_page_fits_busy_patient(report, tmp_path):
    """Many flagged genes and a long medication list still fit on one page."""
    import pdfplumber
    r = with_genes(report, CYP2C19=("*2/*2", "Poor Metabolizer"), CYP2D6=("*4/*4", "Poor Metabolizer"),
                   CYP2C9=("*1/*3", "Intermediate Metabolizer"), SLCO1B1=("*5/*5", "Poor Function"),
                   UGT1A1=("*28/*28", "Poor Metabolizer"), HLA_B_57_01=("Pos/Neg", "Positive"))
    meds = ["Citalopram", "Rosuvastatin", "Omeprazole", "Olmesartan", "Pepcid", "Plavix", "Norco", "Zoloft",
            "Lipitor", "Celebrex", "Toprol XL", "Coumadin", "Ziagen", "lisinopril"]
    out = render_one_page(build_summary(r, meds), tmp_path / "busy.pdf")
    with pdfplumber.open(out) as pdf:
        assert len(pdf.pages) == 1


def test_abacavir_cpic_wording(report):
    neg = _rec(report, "Abacavir")
    assert neg.tier == GREEN and "does not absolutely rule out" in neg.text
    pos = _rec(report, "Abacavir", HLA_B_57_01=("Pos/Neg", "Positive"))
    assert pos.tier == RED and "alternative antiretroviral" in pos.text


def test_warfarin_cpic_2017(report):
    base = _rec(report, "Warfarin")  # CYP2C9 *1/*1, VKORC1 G/G
    assert base.tier == YELLOW and "algorithm" in base.text and "15–30%" not in base.text
    assert _rec(report, "Warfarin", CYP2C9=("*2/*3", "Poor Metabolizer")).tier == RED
    assert "15–30%" in _rec(report, "Warfarin", CYP2C9=("*1/*8", "Intermediate Metabolizer")).text
    assert "20–40%" in _rec(report, "Warfarin", CYP2C9=("*5/*6", "Poor Metabolizer")).text
    assert "5–10%" in _rec(report, "Warfarin", CYP4F2=("*1/*3", "Decreased Function")).text
