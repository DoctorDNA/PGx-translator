"""Morpheus PGx rules table: genotype -> per-drug recommendation.

Each drug has a rule function that looks at the patient's normalized genotypes and
returns a Rec with:

* tier  - red (prefer alternative), yellow (modify / monitor), green (standard start)
* text  - full sentence for the multi-page report
* short - condensed phrase for the one-page summary

Recommendations follow CPIC guidelines (cpicpgx.org) unless ``source`` says
otherwise. This table is clinical decision support only; review it against current
CPIC guidance before relying on it and update RULES_VERSION when you change it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .phenotypes import GREEN, RED, YELLOW, Genotypes

RULES_VERSION = "2.0"
RULES_REVIEWED = "2026-09-27"

CATEGORIES = [
    "Cardiology & Lipids",
    "Pain & Anesthesia",
    "Gastrointestinal",
    "Psychiatry",
    "Neurology",
    "Infectious Disease",
    "Oncology, Immunology & Transplant",
    "Other",
]
TIER_ORDER = {RED: 0, YELLOW: 1, GREEN: 2}


@dataclass
class Rec:
    tier: str
    text: str
    short: str
    source: Optional[str] = None  # overrides Drug.source when set


@dataclass
class Drug:
    name: str
    category: str
    genes: tuple[str, ...]
    rule: Callable[[Genotypes], Rec]
    source: str = "CPIC"
    short_name: Optional[str] = None  # name used on the one-page summary

    @property
    def one_page_name(self) -> str:
        return self.short_name or self.name


@dataclass
class DrugResult:
    drug: Drug
    rec: Rec

    @property
    def tier(self) -> str:
        return self.rec.tier

    @property
    def source(self) -> str:
        return self.rec.source or self.drug.source


def evaluate(gt: Genotypes) -> list[DrugResult]:
    """Evaluate every drug whose genes were all tested."""
    out = []
    for drug in DRUGS:
        if all(g in gt for g in drug.genes):
            out.append(DrugResult(drug, drug.rule(gt)))
    return out


def _std(short: str = "Standard start.", text: str = "Standard dosing.") -> Rec:
    return Rec(GREEN, text, short)


# --------------------------------------------------------------------------- CYP2C19

def voriconazole(gt: Genotypes) -> Rec:
    c = gt.code("CYP2C19")
    if c in ("UM", "RM"):
        return Rec(RED, "Use an alternative: isavuconazole, posaconazole or liposomal amphotericin B.",
                   "Select another antifungal; low exposure likely.")
    if c == "PM":
        return Rec(RED, "Use an alternative not dependent on CYP2C19; if voriconazole is required, "
                        "use a reduced dose with therapeutic drug monitoring.",
                   "Select another antifungal; toxicity risk. If used, lower dose + levels.")
    return _std("Standard start; levels per usual practice.")


def citalopram(gt: Genotypes) -> Rec:
    c = gt.code("CYP2C19")
    if c == "UM":
        return Rec(RED, "Consider an alternative not predominantly metabolized by CYP2C19; "
                        "if used, may need higher maintenance dose.",
                   "Prefer an antidepressant less CYP2C19-dependent.")
    if c == "PM":
        return Rec(RED, "Consider an alternative not predominantly metabolized by CYP2C19; if used, "
                        "start low, titrate slowly and use about 50% of the usual maintenance dose "
                        "(citalopram maximum 20 mg/day).",
                   "Prefer alternative; if used, ~50% dose (citalopram ≤20 mg).")
    if c == "IM":
        return Rec(YELLOW, "Standard starting dose; consider slower titration and a lower maintenance dose.",
                   "Standard start; slower titration, lower maintenance.")
    if c == "RM":
        return _std("Standard start; titrate if response inadequate.",
                    "Standard starting dose; if response is inadequate, titrate higher or switch.")
    return _std()


def sertraline(gt: Genotypes) -> Rec:
    c19, b6 = gt.code("CYP2C19"), gt.code("CYP2B6")
    if c19 == "PM" or b6 == "PM":
        return Rec(YELLOW, "Consider a lower starting dose, slower titration and about 50% of the usual "
                           "maintenance dose, or an alternative.",
                   "Lower start, slower titration; ~50% maintenance.")
    if c19 == "IM" or (b6 == "IM" and c19 == "NM"):
        return Rec(YELLOW, "Standard starting dose; consider slower titration and a lower maintenance dose.",
                   "Standard start; slower titration, lower maintenance.")
    return _std("Standard start.",
                "Standard starting dose; if response is inadequate, titrate higher or switch.")


def tertiary_tca(gt: Genotypes) -> Rec:
    c19, d6 = gt.code("CYP2C19"), gt.code("CYP2D6")
    if d6 in ("UM", "PM"):
        return Rec(RED, "Avoid tricyclics (CYP2D6 " + ("ultrarapid" if d6 == "UM" else "poor") +
                   " metabolizer); select a drug not metabolized by CYP2D6. If a TCA is required, "
                   "use therapeutic drug monitoring.",
                   "Avoid TCAs; choose a non-CYP2D6 alternative.")
    if c19 in ("UM", "RM", "PM"):
        tail = " (reduce 25%, with drug levels)" if d6 == "IM" else ""
        return Rec(RED, "Avoid; if a TCA is needed, use nortriptyline or desipramine" + tail + ".",
                   "Avoid tertiary TCAs if possible; use drug levels if needed.")
    if d6 == "IM":
        return Rec(YELLOW, "Consider 25% dose reduction; use therapeutic drug monitoring.",
                   "Consider ~25% lower dose; drug levels.")
    return _std("Standard start; drug levels if needed.")


def ppi(gt: Genotypes) -> Rec:
    c = gt.code("CYP2C19")
    if c == "UM":
        return Rec(YELLOW, "Increase starting daily dose by 100%, in divided doses; monitor efficacy.",
                   "Consider 2× starting daily dose; assess response.")
    if c == "RM":
        return Rec(YELLOW, "Increase starting daily dose by 50–100% for H. pylori or erosive esophagitis; "
                           "monitor efficacy.",
                   "Consider 1.5–2× starting dose for H. pylori/EE.")
    if c == "PM":
        return Rec(YELLOW, "Standard starting dose; for chronic therapy (>12 weeks) with efficacy achieved, "
                           "consider 50% dose reduction and monitor.",
                   "Standard start; for chronic use consider 50% reduction.")
    if c == "IM":
        return _std("Standard start; chronic use may allow 50% reduction.",
                    "Standard starting dose; for chronic therapy with efficacy achieved, consider 50% dose "
                    "reduction.")
    return _std("Standard start.", "Standard dosing; consider 50–100% higher dose for H. pylori or "
                                   "erosive esophagitis.")


def ppi_no_rec(gt: Genotypes) -> Rec:
    return Rec(GREEN, "No CPIC recommendation; less CYP2C19-dependent PPI.",
               "No CPIC recommendation.", source="CPIC (no rec)")


def clopidogrel(gt: Genotypes) -> Rec:
    c = gt.code("CYP2C19")
    if c in ("IM", "PM"):
        return Rec(RED, "Avoid standard-dose clopidogrel for ACS/PCI and neurovascular indications; use "
                        "prasugrel or ticagrelor if not contraindicated.",
                   "Reduced activation; prefer prasugrel/ticagrelor for ACS/PCI.")
    if c in ("UM", "RM"):
        return _std("Standard for ACS/PCI; context for other indications.",
                    "Standard dosing. Rapid/ultrarapid status does not reduce efficacy.")
    return _std()


# --------------------------------------------------------------------------- CYP2D6

def codeine_tramadol(gt: Genotypes) -> Rec:
    c = gt.code("CYP2D6")
    if c == "UM":
        return Rec(RED, "Avoid: risk of toxicity. Use a non-codeine, non-tramadol opioid or a non-opioid.",
                   "Avoid: toxicity risk. Use a non-codeine/tramadol option.")
    if c == "PM":
        return Rec(RED, "Avoid: lack of efficacy. Use a non-codeine, non-tramadol opioid or a non-opioid.",
                   "Avoid: little analgesia. Use a non-codeine/tramadol option.")
    if c == "IM":
        return Rec(YELLOW, "Label dosing; if no response, use a non-codeine, non-tramadol opioid.",
                   "Usual start; tramadol may give less analgesia. Switch if ineffective.")
    return _std("Label dosing.")


def hydrocodone(gt: Genotypes) -> Rec:
    c = gt.code("CYP2D6")
    if c in ("IM", "PM"):
        return Rec(YELLOW, "Label dosing; if no response, consider a non-tramadol/codeine alternative.",
                   "Usual start; tramadol may give less analgesia. Switch if ineffective."
                   if c == "IM" else "Label dosing; switch if ineffective.")
    return _std("Label dosing.", "Label dosing; no CYP2D6-based change.")


def no_cyp2d6_change(gt: Genotypes) -> Rec:
    return Rec(GREEN, "No CYP2D6-based change.", "No CPIC dose change.")


def antiemetic_5ht3(gt: Genotypes) -> Rec:
    if gt.code("CYP2D6") == "UM":
        return Rec(RED, "Select an alternative not predominantly metabolized by CYP2D6 (e.g., granisetron).",
                   "Reduced efficacy; use granisetron instead.")
    return _std()


def atomoxetine(gt: Genotypes) -> Rec:
    c = gt.code("CYP2D6")
    if c == "IM":
        return Rec(YELLOW, "Start 40 mg/day, increase to 80 mg/day after 3 days; consider 100 mg/day at "
                           "2 weeks if needed and tolerated.",
                   "Standard start; titrate to response; level if needed.")
    if c == "PM":
        return Rec(YELLOW, "Start 40 mg/day; if no response and no adverse effects after 2 weeks, increase "
                           "to 80 mg/day; consider a drug level.",
                   "Start 40 mg/day; slower titration; level if needed.")
    if c == "UM":
        return _std("Standard start; may need higher dose; level if no response.",
                    "Standard starting dose; if no response, titrate higher and consider a drug level.")
    return _std()


def nortriptyline(gt: Genotypes) -> Rec:
    c = gt.code("CYP2D6")
    if c == "UM":
        return Rec(RED, "Avoid; select a drug not metabolized by CYP2D6. If a TCA is required, titrate "
                        "with therapeutic drug monitoring.", "Avoid; low levels likely.")
    if c == "PM":
        return Rec(RED, "Avoid; if a TCA is required, use 50% of the usual starting dose with therapeutic "
                        "drug monitoring.", "Avoid; if needed, 50% dose with levels.")
    if c == "IM":
        return Rec(YELLOW, "Consider 25% dose reduction; use therapeutic drug monitoring.",
                   "Consider ~25% lower depression dose; drug levels.")
    return _std()


def paroxetine(gt: Genotypes) -> Rec:
    c = gt.code("CYP2D6")
    if c == "UM":
        return Rec(RED, "Consider an alternative not predominantly metabolized by CYP2D6.",
                   "Low levels likely; prefer an alternative.")
    if c == "IM":
        return Rec(YELLOW, "Consider a lower starting dose and slower titration.",
                   "Consider lower start and slower titration.")
    if c == "PM":
        return Rec(YELLOW, "Consider 50% of the usual starting dose and slower titration, or an alternative.",
                   "Consider 50% starting dose, slower titration.")
    return _std()


def fluvoxamine(gt: Genotypes) -> Rec:
    if gt.code("CYP2D6") == "PM":
        return Rec(YELLOW, "Consider a lower starting dose and slower titration.",
                   "Consider lower start and slower titration.")
    return _std()


def vortioxetine(gt: Genotypes) -> Rec:
    c = gt.code("CYP2D6")
    if c == "PM":
        return Rec(YELLOW, "Start at 50% of the usual starting dose; maximum 10 mg/day.",
                   "Start 50% dose; max 10 mg/day.")
    if c == "UM":
        return _std("Standard start; may need higher dose or alternative.",
                    "Standard starting dose; if no response, consider titrating higher or an alternative.")
    return _std()


def venlafaxine(gt: Genotypes) -> Rec:
    if gt.code("CYP2D6") == "PM":
        return Rec(YELLOW, "Consider an alternative not predominantly metabolized by CYP2D6, or a lower "
                           "dose with close monitoring.", "Consider alternative or lower dose.")
    return _std()


def fluoxetine(gt: Genotypes) -> Rec:
    return Rec(GREEN, "No CPIC dose change.", "No CPIC dose change.")


def metoprolol(gt: Genotypes) -> Rec:
    c = gt.code("CYP2D6")
    if c == "PM":
        return Rec(YELLOW, "Start low and titrate slowly to heart rate/BP; consider bisoprolol or carvedilol "
                           "if bradycardia or intolerance.", "Low start, slow titration; bradycardia risk.")
    if c == "UM":
        return _std("Standard start; may need higher dose or alternative.",
                    "Standard dosing; if response is inadequate, titrate or use bisoprolol/carvedilol.")
    return _std("Standard start.")


def tamoxifen(gt: Genotypes) -> Rec:
    c = gt.code("CYP2D6")
    if c == "PM":
        return Rec(RED, "Use alternative hormonal therapy (e.g., aromatase inhibitor, with ovarian "
                        "suppression if premenopausal). Avoid CYP2D6 inhibitors.",
                   "Oncology review: prefer alternative hormonal therapy.")
    if c == "IM":
        return Rec(YELLOW, "Consider 40 mg/day, or an alternative where one exists. Avoid CYP2D6 inhibitors.",
                   "Oncology review: alternative or dose strategy; AS 1 optional."
                   if gt.score("CYP2D6") == 1.0 else "Oncology review: alternative or 40 mg/day.")
    return _std("Standard 20 mg/day; avoid CYP2D6 inhibitors.",
                "Standard dosing (20 mg/day); avoid strong CYP2D6 inhibitors.")


# --------------------------------------------------------------------------- CYP2B6 / CYP3A

def efavirenz(gt: Genotypes) -> Rec:
    c = gt.code("CYP2B6")
    if c == "IM":
        return Rec(YELLOW, "Consider starting at 400 mg/day instead of 600 mg.",
                   "Consider 400 instead of 600 mg/day.")
    if c == "PM":
        return Rec(YELLOW, "Consider starting at 400 or 200 mg/day instead of 600 mg; monitor for CNS effects.",
                   "Consider 400 or 200 mg/day instead of 600.")
    return _std("Standard 600 mg/day.")


def methadone(gt: Genotypes) -> Rec:
    if gt.code("CYP2B6") == "PM":
        return Rec(YELLOW, "No CPIC guideline; poor CYP2B6 function may raise exposure and QT risk. "
                           "Start low and titrate cautiously.",
                   "Start low; higher exposure and QT risk possible.", source="Literature")
    return Rec(GREEN, "No CPIC guideline; reduced CYP2B6 function may modestly raise exposure. "
                      "Standard start with usual QT monitoring.",
               "Standard start.", source="Literature")


def tacrolimus(gt: Genotypes) -> Rec:
    c = gt.code("CYP3A5")
    note = ""
    if gt.code("CYP3A4") in ("IM", "PM"):
        note = " CYP3A4*22 may lower the dose requirement, so monitor troughs closely."
    if c in ("NM", "IM"):
        return Rec(YELLOW, "CYP3A5 expresser: increase starting dose 1.5–2× (max 0.3 mg/kg/day) and "
                           "use therapeutic drug monitoring." + note,
                   "Higher start (1.5–2×); drug levels.")
    return Rec(GREEN, "Standard starting dose (CYP3A5 non-expresser); use therapeutic drug monitoring." + note,
               "Standard start; needs drug levels.")


def midazolam(gt: Genotypes) -> Rec:
    return Rec(GREEN, "No PGx dose change; titrate to effect.", "No CPIC dose change.", source="Literature")


# --------------------------------------------------------------------------- SLCO1B1 statins

def simvastatin(gt: Genotypes) -> Rec:
    c = gt.code("SLCO1B1")
    if c == "DF":
        return Rec(RED, "Use an alternative statin; if necessary, keep dose <20 mg/day.",
                   "Alternative statin; if used: simva <20, lova ≤20 mg/day.")
    if c == "PF":
        return Rec(RED, "Use an alternative statin.", "Alternative statin.")
    return _std()


def lovastatin(gt: Genotypes) -> Rec:
    c = gt.code("SLCO1B1")
    if c == "DF":
        return Rec(RED, "Use an alternative statin; if necessary, keep dose ≤20 mg/day.",
                   "Alternative statin; if used: simva <20, lova ≤20 mg/day.")
    if c == "PF":
        return Rec(RED, "Use an alternative statin.", "Alternative statin.")
    return _std()


def atorvastatin(gt: Genotypes) -> Rec:
    c = gt.code("SLCO1B1")
    if c == "DF":
        return Rec(YELLOW, "Start ≤40 mg/day; if more intensity is needed, use rosuvastatin or combination "
                           "therapy.", "Usual start; muscle-risk vigilance at high doses.")
    if c == "PF":
        return Rec(YELLOW, "Start ≤20 mg/day; if more intensity is needed, use rosuvastatin or combination "
                           "therapy.", "Start ≤20 mg/day; monitor muscle symptoms.")
    return _std()


def rosuvastatin(gt: Genotypes) -> Rec:
    s, a = gt.code("SLCO1B1"), gt.code("ABCG2")
    cap = min({"PF": 10, "DF": 20}.get(s, 40), {"PF": 10, "DF": 20}.get(a, 40))
    if cap == 40:
        return _std("Standard start.", "Desired starting dose; adjust per disease-specific guidelines.")
    if cap == 10:
        return Rec(YELLOW, "Start ≤10 mg/day; if more is needed, use an alternative or combination therapy.",
                   "Start ≤10 mg/day; monitor muscle symptoms.")
    return Rec(YELLOW, "Start ≤20 mg/day; if more is needed, use an alternative or combination therapy.",
               "Usual start; muscle-risk vigilance above 20 mg/day.")


def pitavastatin(gt: Genotypes) -> Rec:
    c = gt.code("SLCO1B1")
    if c == "DF":
        return Rec(YELLOW, "Start ≤2 mg/day; if more is needed, use an alternative.",
                   "Start ≤2 mg/day; monitor muscle symptoms.")
    if c == "PF":
        return Rec(YELLOW, "Start ≤1 mg/day; if more is needed, use an alternative.",
                   "Start ≤1 mg/day; monitor muscle symptoms.")
    return _std()


def pravastatin(gt: Genotypes) -> Rec:
    c = gt.code("SLCO1B1")
    if c == "PF":
        return Rec(YELLOW, "Start ≤40 mg/day; if more is needed, use an alternative or combination therapy.",
                   "Start ≤40 mg/day; monitor muscle symptoms.")
    if c == "DF":
        return _std("Usual start; myopathy risk higher above 40 mg/day.",
                    "Desired starting dose; adjust per disease-specific guidelines. Myopathy risk is higher "
                    "above 40 mg/day.")
    return _std()


def fluvastatin(gt: Genotypes) -> Rec:
    s, c9 = gt.code("SLCO1B1"), gt.code("CYP2C9")
    if s == "PF" and c9 in ("IM", "PM"):
        return Rec(RED, "Use an alternative statin.", "Alternative statin.")
    if c9 == "PM":
        return Rec(YELLOW, "Start ≤20 mg/day; if more is needed, use an alternative or combination therapy.",
                   "Start ≤20 mg/day.")
    if c9 == "IM" or s == "PF":
        return Rec(YELLOW, "Start ≤40 mg/day; if more is needed, use an alternative or combination therapy.",
                   "Start ≤40 mg/day.")
    return _std("Standard start.", "Desired starting dose; adjust per disease-specific guidelines.")


# --------------------------------------------------------------------------- warfarin

def warfarin(gt: Genotypes) -> Rec:
    v = gt.code("VKORC1")
    detail = {
        "LOW": "VKORC1 result predicts a higher-than-average dose requirement.",
        "INT": "VKORC1 result predicts an intermediate dose requirement.",
        "HIGH": "VKORC1 result predicts a lower-than-average dose requirement.",
    }[v]
    c9 = gt.code("CYP2C9")
    if c9 in ("IM", "PM"):
        detail += " Reduced CYP2C9 function lowers the dose and slows time to stable INR."
    tier = RED if (v == "HIGH" and c9 == "PM") else YELLOW
    return Rec(tier, "Use a validated pharmacogenetic dosing algorithm; " + detail,
               "Use PGx dosing algorithm; titrate to INR.")


# --------------------------------------------------------------------------- CYP2C9

def _cyp2c9_as(gt: Genotypes) -> float:
    s = gt.score("CYP2C9")
    return 2.0 if s is None else s


def nsaid(gt: Genotypes) -> Rec:
    s = _cyp2c9_as(gt)
    if s >= 1.5:
        return _std("Usual CYP2C9 dosing.")
    if s >= 1.0:
        return Rec(YELLOW, "Start at the lowest recommended dose; titrate cautiously to effect; use the lowest "
                           "effective dose for the shortest time.", "Lowest starting dose; titrate cautiously.")
    return Rec(RED, "Start at 25–50% of the lowest recommended dose with cautious titration, or use an "
                    "alternative not metabolized by CYP2C9.", "25–50% of lowest dose, or alternative.")


def meloxicam(gt: Genotypes) -> Rec:
    s = _cyp2c9_as(gt)
    if s >= 1.5:
        return _std("Usual CYP2C9 dosing.")
    if s >= 1.0:
        return Rec(YELLOW, "Start at 50% of the lowest recommended dose; titrate cautiously.",
                   "Start 50% of lowest dose.")
    return Rec(RED, "Use an alternative not metabolized by CYP2C9 or not prolonged by reduced CYP2C9 "
                    "function.", "Use an alternative NSAID/analgesic.")


def piroxicam(gt: Genotypes) -> Rec:
    s = _cyp2c9_as(gt)
    if s >= 1.5:
        return _std("Usual CYP2C9 dosing.")
    return Rec(RED, "Use an alternative not metabolized by CYP2C9 or with a shorter half-life.",
               "Use an alternative NSAID/analgesic.")


def phenytoin(gt: Genotypes) -> Rec:
    if gt.code("HLA-B*15:02") == "POS":
        return Rec(RED, "HLA-B*15:02 positive: if phenytoin-naive, do not use (SJS/TEN risk).",
                   "HLA-B*15:02 positive: avoid if drug-naive.")
    s = _cyp2c9_as(gt)
    if s >= 2.0:
        return _std("Standard start; drug levels.", "Standard dosing.")
    if s >= 1.0:
        return Rec(YELLOW, "Standard loading dose; consider 25% lower maintenance dose; adjust by drug levels.",
                   "~25% lower maintenance dose; drug levels.")
    return Rec(YELLOW, "Standard loading dose; consider 50% lower maintenance dose; adjust by drug levels.",
               "~50% lower maintenance dose; drug levels.")


# --------------------------------------------------------------------------- HLA

def carbamazepine(gt: Genotypes) -> Rec:
    if gt.code("HLA-B*15:02") == "POS":
        return Rec(RED, "HLA-B*15:02 positive: if carbamazepine-naive, do not use (SJS/TEN risk).",
                   "HLA-B*15:02 positive: avoid if drug-naive.")
    if gt.code("HLA-A*31:01") == "POS":
        return Rec(RED, "HLA-A*31:01 positive: if carbamazepine-naive, use an alternative; if none, "
                        "monitor closely for skin reactions.", "HLA-A*31:01 positive: prefer alternative.")
    return _std("No tested HLA restriction.", "Standard dosing.")


def oxcarbazepine(gt: Genotypes) -> Rec:
    if gt.code("HLA-B*15:02") == "POS":
        return Rec(RED, "HLA-B*15:02 positive: if oxcarbazepine-naive, do not use (SJS/TEN risk).",
                   "HLA-B*15:02 positive: avoid if drug-naive.")
    return _std("No tested HLA restriction.", "Standard dosing.")


def abacavir(gt: Genotypes) -> Rec:
    if gt.code("HLA-B*57:01") == "POS":
        return Rec(RED, "HLA-B*57:01 positive: do not use (hypersensitivity risk).",
                   "HLA-B*57:01 positive: do not use.")
    return _std("No tested HLA restriction.", "May be used.")


def allopurinol(gt: Genotypes) -> Rec:
    if gt.code("HLA-B*58:01") == "POS":
        return Rec(RED, "HLA-B*58:01 positive: do not use (SCAR risk); choose an alternative.",
                   "HLA-B*58:01 positive: do not use.")
    return _std("No tested HLA restriction.", "Use per standard practice.")


# --------------------------------------------------------------------------- NAT2

def hydralazine(gt: Genotypes) -> Rec:
    c = gt.code("NAT2")
    if c == "PM":
        return Rec(YELLOW, "Start 40–75 mg/day total; titrate carefully to effect; use caution at ≥200 mg/day "
                           "(drug-induced lupus risk).", "Resistant HTN: start 40–75 mg/day; caution ≥200.")
    if c == "NM":
        return _std("Standard start; may need higher dose.",
                    "Standard dosing; rapid acetylators may need higher doses for effect.")
    return _std()


def _nat2_literature(slow_tier: str, text: str, short: str) -> Callable[[Genotypes], Rec]:
    def rule(gt: Genotypes) -> Rec:
        if gt.code("NAT2") == "PM":
            return Rec(slow_tier, text, short)
        return _std("Standard dosing.", "No acetylator-based change.")
    return rule


def amifampridine(gt: Genotypes) -> Rec:
    if gt.code("NAT2") == "PM":
        return Rec(YELLOW, "Start 15 mg/day in poor metabolizers.", "Start 15 mg/day.")
    return _std("Label dosing.", "Label dosing.")


# --------------------------------------------------------------------------- other genes

def fluoropyrimidine(gt: Genotypes) -> Rec:
    s = gt.score("DPYD")
    s = 2.0 if s is None else s
    if s >= 2.0:
        return _std("Standard DPYD starting dose.", "Full standard dose.")
    if s >= 1.0:
        return Rec(YELLOW, f"DPYD activity score {s:.1f}: reduce starting dose by 50%, then titrate by "
                           "toxicity (and drug levels if available).", "Start at 50% dose; titrate by toxicity.")
    return Rec(RED, f"DPYD activity score {s:.1f}: avoid fluoropyrimidines; if no alternative, use a "
                    "strongly reduced dose with drug-level monitoring.", "Avoid; severe toxicity risk.")


def thiopurine(gt: Genotypes) -> Rec:
    t, n = gt.code("TPMT"), gt.code("NUDT15")
    if "PM" in (t, n):
        return Rec(RED, "For non-malignant conditions use a non-thiopurine alternative; for malignancy, "
                        "drastically reduce dose (about 10-fold, 3×/week) with close CBC monitoring.",
                   "Prefer non-thiopurine; if needed, ~10× lower dose.")
    if "IM" in (t, n):
        return Rec(YELLOW, "Start at 30–80% of the normal dose (50–80% for thioguanine); adjust by "
                           "myelosuppression.", "Start 30–80% dose; CBC monitoring.")
    return _std("Standard start; CBC monitoring.", "Normal starting dose.")


def atazanavir(gt: Genotypes) -> Rec:
    if gt.code("UGT1A1") == "PM":
        return Rec(RED, "High likelihood of jaundice-related discontinuation; consider an alternative.",
                   "Jaundice likely; consider alternative.")
    return _std("Usual start; monitor clinically.", "No genetic reason to avoid.")


def irinotecan(gt: Genotypes) -> Rec:
    if gt.code("UGT1A1") == "PM":
        return Rec(YELLOW, "Reduce starting dose (about 30% lower); increase by neutrophil count.",
                   "Start ~30% lower dose.")
    return _std("Standard dosing.", "Standard dosing.")


def ifnl3(gt: Genotypes) -> Rec:
    if gt.code("IFNL3") == "UNFAV":
        return Rec(YELLOW, "Unfavorable response genotype: lower cure rate with peginterferon-based regimens; "
                           "prefer direct-acting antivirals.", "Lower response; prefer DAAs.")
    return Rec(GREEN, "Favorable response genotype.", "Favorable response genotype.")


def estrogen(gt: Genotypes) -> Rec:
    c = gt.code("F5")
    if c in ("HET", "HOM"):
        return Rec(RED, "Factor V Leiden " + ("homozygous" if c == "HOM" else "heterozygous") +
                   ": increased VTE risk with estrogen-containing therapy; prefer non-estrogen options.",
                   "Increased VTE risk; prefer non-estrogen options.")
    return Rec(GREEN, "No added Factor V Leiden risk.", "No added Factor V Leiden risk.")


# --------------------------------------------------------------------------- registry

C, P, G, Y, N, I, O, X = CATEGORIES

DRUGS: list[Drug] = [
    # Cardiology & Lipids
    Drug("Clopidogrel", C, ("CYP2C19",), clopidogrel),
    Drug("Metoprolol", C, ("CYP2D6",), metoprolol),
    Drug("Simvastatin", C, ("SLCO1B1",), simvastatin),
    Drug("Lovastatin", C, ("SLCO1B1",), lovastatin),
    Drug("Atorvastatin", C, ("SLCO1B1",), atorvastatin),
    Drug("Rosuvastatin", C, ("SLCO1B1", "ABCG2"), rosuvastatin),
    Drug("Pitavastatin", C, ("SLCO1B1",), pitavastatin),
    Drug("Pravastatin", C, ("SLCO1B1",), pravastatin),
    Drug("Fluvastatin", C, ("SLCO1B1", "CYP2C9"), fluvastatin),
    Drug("Warfarin", C, ("CYP2C9", "VKORC1", "CYP4F2"), warfarin),
    Drug("Hydralazine", C, ("NAT2",), hydralazine),
    Drug("Procainamide", C, ("NAT2",), _nat2_literature(
        RED, "Higher exposure and drug-induced lupus risk in slow acetylators.",
        "Higher exposure and lupus risk."), source="Literature"),
    # Pain & Anesthesia
    Drug("Codeine", P, ("CYP2D6",), codeine_tramadol),
    Drug("Tramadol", P, ("CYP2D6",), codeine_tramadol),
    Drug("Hydrocodone", P, ("CYP2D6",), hydrocodone),
    Drug("Oxycodone", P, ("CYP2D6",), no_cyp2d6_change),
    Drug("Morphine", P, ("CYP2D6",), no_cyp2d6_change),
    Drug("Hydromorphone", P, ("CYP2D6",), no_cyp2d6_change),
    Drug("Fentanyl", P, ("CYP2D6",), no_cyp2d6_change),
    Drug("Methadone", P, ("CYP2B6",), methadone, source="Literature"),
    Drug("Midazolam", P, ("CYP3A5",), midazolam, source="Literature"),
    Drug("Ondansetron", P, ("CYP2D6",), antiemetic_5ht3),
    Drug("Tropisetron", P, ("CYP2D6",), antiemetic_5ht3),
    Drug("Celecoxib", P, ("CYP2C9",), nsaid),
    Drug("Flurbiprofen", P, ("CYP2C9",), nsaid),
    Drug("Ibuprofen", P, ("CYP2C9",), nsaid),
    Drug("Lornoxicam", P, ("CYP2C9",), nsaid),
    Drug("Meloxicam", P, ("CYP2C9",), meloxicam),
    Drug("Piroxicam", P, ("CYP2C9",), piroxicam),
    Drug("Tenoxicam", P, ("CYP2C9",), piroxicam),
    # Gastrointestinal
    Drug("Omeprazole", G, ("CYP2C19",), ppi),
    Drug("Lansoprazole", G, ("CYP2C19",), ppi),
    Drug("Pantoprazole", G, ("CYP2C19",), ppi),
    Drug("Dexlansoprazole", G, ("CYP2C19",), ppi),
    Drug("Esomeprazole", G, ("CYP2C19",), ppi_no_rec),
    Drug("Rabeprazole", G, ("CYP2C19",), ppi_no_rec),
    Drug("Sulfasalazine", G, ("NAT2",), _nat2_literature(
        YELLOW, "Higher adverse-effect risk in slow acetylators.", "Higher adverse-effect risk."),
         source="Literature"),
    # Psychiatry
    Drug("Citalopram", Y, ("CYP2C19",), citalopram),
    Drug("Escitalopram", Y, ("CYP2C19",), citalopram),
    Drug("Sertraline", Y, ("CYP2C19", "CYP2B6"), sertraline),
    Drug("Amitriptyline", Y, ("CYP2C19", "CYP2D6"), tertiary_tca),
    Drug("Clomipramine", Y, ("CYP2C19", "CYP2D6"), tertiary_tca),
    Drug("Doxepin", Y, ("CYP2C19", "CYP2D6"), tertiary_tca),
    Drug("Imipramine", Y, ("CYP2C19", "CYP2D6"), tertiary_tca),
    Drug("Trimipramine", Y, ("CYP2C19", "CYP2D6"), tertiary_tca),
    Drug("Nortriptyline", Y, ("CYP2D6",), nortriptyline),
    Drug("Desipramine", Y, ("CYP2D6",), nortriptyline),
    Drug("Paroxetine", Y, ("CYP2D6",), paroxetine),
    Drug("Fluvoxamine", Y, ("CYP2D6",), fluvoxamine),
    Drug("Vortioxetine", Y, ("CYP2D6",), vortioxetine),
    Drug("Venlafaxine", Y, ("CYP2D6",), venlafaxine),
    Drug("Fluoxetine", Y, ("CYP2D6",), fluoxetine),
    Drug("Atomoxetine", Y, ("CYP2D6",), atomoxetine),
    # Neurology
    Drug("Phenytoin", N, ("CYP2C9", "HLA-B*15:02"), phenytoin),
    Drug("Fosphenytoin", N, ("CYP2C9", "HLA-B*15:02"), phenytoin),
    Drug("Carbamazepine", N, ("HLA-B*15:02", "HLA-A*31:01"), carbamazepine),
    Drug("Oxcarbazepine", N, ("HLA-B*15:02",), oxcarbazepine),
    Drug("Amifampridine", N, ("NAT2",), amifampridine, source="FDA label"),
    # Infectious Disease
    Drug("Voriconazole", I, ("CYP2C19",), voriconazole),
    Drug("Efavirenz", I, ("CYP2B6",), efavirenz),
    Drug("Isoniazid", I, ("NAT2",), _nat2_literature(
        RED, "Higher hepatotoxicity risk in slow acetylators; consider dose reduction.",
        "Hepatotoxicity risk; consider lower dose."), source="Literature"),
    Drug("Dapsone", I, ("NAT2",), _nat2_literature(
        YELLOW, "Higher adverse-effect risk in slow acetylators.", "Higher adverse-effect risk."),
         source="Literature"),
    Drug("Atazanavir", I, ("UGT1A1",), atazanavir),
    Drug("Abacavir", I, ("HLA-B*57:01",), abacavir),
    Drug("Peginterferon alfa", I, ("IFNL3",), ifnl3),
    Drug("Ribavirin", I, ("IFNL3",), ifnl3),
    # Oncology, Immunology & Transplant
    Drug("Tamoxifen", O, ("CYP2D6",), tamoxifen),
    Drug("Tacrolimus", O, ("CYP3A5", "CYP3A4"), tacrolimus),
    Drug("Fluorouracil", O, ("DPYD",), fluoropyrimidine, short_name="5-FU"),
    Drug("Capecitabine", O, ("DPYD",), fluoropyrimidine),
    Drug("Tegafur", O, ("DPYD",), fluoropyrimidine),
    Drug("Azathioprine", O, ("TPMT", "NUDT15"), thiopurine),
    Drug("Mercaptopurine", O, ("TPMT", "NUDT15"), thiopurine),
    Drug("Thioguanine", O, ("TPMT", "NUDT15"), thiopurine),
    Drug("Irinotecan", O, ("UGT1A1",), irinotecan, source="FDA/DPWG"),
    # Other
    Drug("Allopurinol", X, ("HLA-B*58:01",), allopurinol),
    Drug("Estrogen-containing therapy", X, ("F5",), estrogen, source="Literature"),
]

DRUGS_BY_NAME = {d.name: d for d in DRUGS}

# "Key drugs affected" column of the gene table.
GENE_KEY_DRUGS = {
    "ABCG2": "Rosuvastatin",
    "CYP2B6": "Efavirenz, sertraline, methadone",
    "CYP2C9": "NSAIDs, phenytoin, warfarin, fluvastatin",
    "CYP2C19": "PPIs, citalopram/escitalopram, sertraline, tertiary TCAs, voriconazole, clopidogrel",
    "CYP2D6": "Codeine, tramadol, hydrocodone, TCAs, SSRIs, atomoxetine, tamoxifen, ondansetron, metoprolol",
    "CYP3A4": "Tacrolimus",
    "CYP3A5": "Tacrolimus",
    "CYP4F2": "Warfarin",
    "DPYD": "Fluorouracil, capecitabine",
    "F5": "Estrogen-containing therapy",
    "HLA-A*31:01": "Carbamazepine",
    "HLA-B*15:02": "Carbamazepine, oxcarbazepine, phenytoin",
    "HLA-B*57:01": "Abacavir",
    "HLA-B*58:01": "Allopurinol",
    "IFNL3": "Peginterferon alfa + ribavirin",
    "NAT2": "Hydralazine, isoniazid, procainamide, sulfasalazine, dapsone",
    "NUDT15": "Thiopurines",
    "SLCO1B1": "Statins",
    "TPMT": "Thiopurines",
    "UGT1A1": "Atazanavir, irinotecan",
    "VKORC1": "Warfarin",
}
