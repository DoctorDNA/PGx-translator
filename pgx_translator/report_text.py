"""Fixed wording shared by the PDF and DOCX versions of the full report."""

from __future__ import annotations

from .rules import RULES_REVIEWED, RULES_VERSION
from .summary import Summary

HOW_TO_READ = [
    "This report shows how your genes affect the way your body processes certain medications. "
    "It does not diagnose disease.",
    "<b>Green (normal):</b> standard dosing is expected.",
    "<b>Yellow (intermediate or decreased):</b> some medications need a dose change or closer monitoring.",
    "<b>Red (rapid or poor):</b> some medications should be avoided or changed significantly.",
    "The color next to a gene describes that gene. The color next to a medication tells you what to do "
    "with that specific drug, so a red gene can still have green medications.",
]

SHARE_NOTE = ("Share this report with every prescriber and pharmacist. Do not stop or change any "
              "medication without talking to your healthcare provider.")

QUICK_REF_NOTE = ("See detailed recommendations on the following pages. Drugs marked Literature or "
                  "FDA label are not CPIC guidelines.")


def REPORT_GUIDE(summary: Summary) -> list[tuple[str, str]]:
    n = len(summary.genotypes.genes)
    return [
        ("Gene Results", f"your result for each of the {n} genes tested"),
        ("Medication Quick Reference", "every medication at a glance, sorted by color"),
        ("Action Required", "only the red and yellow medications, by body system"),
        ("All Medications", "full recommendations for every medication"),
        ("Interpretation Notes", "test limitations and important cautions"),
    ]


def _d(d) -> str:
    return d.strftime("%m/%d/%Y") if d else "Not provided"


def patient_rows(summary: Summary) -> list[tuple[str, str, str, str]]:
    r = summary.report
    p = r.patient
    return [
        ("Patient", p.display_name or "Not provided", "DOB / Sex",
         f"{_d(p.dob)} / {p.sex or 'Not provided'}"),
        ("Test", r.test_name or "Not provided", "Specimen", r.specimen or "Not provided"),
        ("Collected", _d(r.collected), "Reported", _d(r.reported)),
    ]


def footer_text(summary: Summary) -> str:
    p = summary.report.patient
    return (f"Morpheus Precision Health  |  {p.display_name or 'Patient'}  |  "
            f"DOB {_d(p.dob)}  |  Pharmacogenomics Report")


def interpretation_notes(summary: Summary) -> list[str]:
    r = summary.report
    notes = [
        "Strong CYP2D6 inhibitors (bupropion, fluoxetine, paroxetine) can convert a CYP2D6 normal or "
        "intermediate metabolizer to a functional poor metabolizer.",
        "Phenotypes are as reported by the laboratory. CYP2D6 phenotype follows activity-score "
        "classification (2020 consensus).",
        "Several CYP2C9 recommendations depend on activity score (1.0 vs 1.5), which may not appear on "
        "the lab report.",
        "Only the alleles tested by the laboratory were assessed; untested variants default to normal (*1).",
        f"Recommendations are from the Morpheus PGx rules table v{RULES_VERSION}, reviewed against CPIC on "
        f"{RULES_REVIEWED}. Confirm current guidance before prescribing decisions.",
        f"Source: {r.lab}{', ' + r.test_name if r.test_name else ''}, specimen "
        f"{r.specimen or 'Not provided'}{', reporting ID ' + r.reporting_id if r.reporting_id else ''}.",
    ]
    return notes


# --------------------------------------------------------------------------- clickable drug links
# The Gene Results "Key drugs affected" column links each drug to its card in "All Medications".

import re as _re

LINK_HINT = "Click or tap any underlined medication to jump to its full recommendation."
LINK_BLUE = "0563C1"

# Group words in GENE_KEY_DRUGS -> the drug card they jump to.
_GROUP_TARGET = {"PPIs": "Omeprazole", "tertiary TCAs": "Amitriptyline", "TCAs": "Amitriptyline",
                 "SSRIs": "Paroxetine", "NSAIDs": "Celecoxib"}
# Group words shown as individual (each linked) drug names instead.
_GROUP_EXPAND = {"Statins": ["Simvastatin", "Lovastatin", "Atorvastatin", "Rosuvastatin", "Pitavastatin",
                             "Pravastatin", "Fluvastatin"],
                 "Thiopurines": ["Azathioprine", "Mercaptopurine", "Thioguanine"]}


def drug_anchor(name: str) -> str:
    """Bookmark name for a drug's card, e.g. 'drug_Omeprazole'."""
    return "drug_" + _re.sub(r"[^A-Za-z0-9]", "_", name)


def key_drug_segments(summary: Summary, gene: str) -> list[tuple[str, str | None]]:
    """Split a gene's key-drugs text into (text, anchor) pieces; anchor is None for plain text
    (separators, or drugs not assessed for this patient)."""
    from .rules import GENE_KEY_DRUGS
    present = {r.drug.name.lower(): r.drug.name for r in summary.results}
    out: list[tuple[str, str | None]] = []
    for piece in _re.split(r"(, | \+ |/)", GENE_KEY_DRUGS.get(gene, "")):
        if not piece:
            continue
        if piece in (", ", " + ", "/"):
            out.append((piece, None))
        elif piece in _GROUP_EXPAND:
            for i, name in enumerate(_GROUP_EXPAND[piece]):
                if i:
                    out.append((", ", None))
                label = name if i == 0 else name.lower()
                out.append((label, drug_anchor(name) if name.lower() in present else None))
        else:
            target = _GROUP_TARGET.get(piece) or present.get(piece.lower())
            ok = target is not None and target.lower() in present
            out.append((piece, drug_anchor(target) if ok else None))
    return out


STATUS_LABEL = {"red": "AVOID OR CHANGE", "yellow": "ADJUST OR MONITOR", "green": "STANDARD DOSING"}
