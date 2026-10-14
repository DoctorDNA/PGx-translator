"""Morpheus PGx rules table: genotype -> per-drug recommendation.

Each drug has a rule function that looks at the patient's normalized genotypes and
returns a Rec with:

* tier  - red (prefer alternative), yellow (modify / monitor), green (standard start)
* text  - full sentence for the multi-page report
* short - condensed phrase for the one-page summary

Recommendations follow CPIC guidelines (cpicpgx.org) unless ``source`` says
otherwise. A source with a year (e.g. "CPIC 2019") means the rule was checked against that
published guideline; see CPIC_REVIEW.md for the review log. This table is clinical decision
support only; update RULES_VERSION and CPIC_REVIEW.md when you change it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .phenotypes import GREEN, RED, YELLOW, Genotypes

RULES_VERSION = "2.1"

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


# CPIC TCA guideline (2016 update, Tables 2-4) covers depression-range doses only.
TCA_DOSE_SCOPE = (" Applies to depression-range doses; CPIC recommends no dose change for intermediate or "
                  "poor metabolizers on low doses (e.g., neuropathic pain).")


def tertiary_tca(gt: Genotypes) -> Rec:
    c19, d6 = gt.code("CYP2C19"), gt.code("CYP2D6")
    if d6 == "UM":
        return Rec(RED, "Avoid tricyclics (CYP2D6 ultrarapid metabolizer: likely lack of efficacy); select a "
                        "drug not metabolized by CYP2D6. If a TCA is warranted, titrate to a higher target dose "
                        "with therapeutic drug monitoring." + TCA_DOSE_SCOPE,
                   "Avoid TCAs; choose a non-CYP2D6 alternative.")
    if d6 == "PM":
        return Rec(RED, "Avoid tricyclics (CYP2D6 poor metabolizer: side-effect risk); select a drug not "
                        "metabolized by CYP2D6. If a TCA is warranted, consider a 50% reduction of the starting "
                        "dose with therapeutic drug monitoring." + TCA_DOSE_SCOPE,
                   "Avoid TCAs; choose a non-CYP2D6 alternative.")
    if c19 in ("UM", "RM", "PM"):
        tail = " (reduce 25%, with drug levels)" if d6 == "IM" else ""
        alt = "Avoid; if a TCA is needed, use nortriptyline or desipramine" + tail + "."
        if c19 == "PM" and d6 == "NM":
            alt += (" If a tertiary amine is warranted, consider a 50% reduction of the starting dose with "
                    "therapeutic drug monitoring.")
        elif c19 in ("UM", "RM"):
            alt += " If a tertiary amine is warranted, use therapeutic drug monitoring."
        return Rec(RED, alt + TCA_DOSE_SCOPE,
                   "Avoid tertiary TCAs if possible; use drug levels if needed.")
    if d6 == "IM":
        return Rec(YELLOW, "Consider 25% dose reduction; use therapeutic drug monitoring." + TCA_DOSE_SCOPE,
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
    # CPIC 2022, Table 2 (cardiovascular) and Table 3 (neurovascular).
    neuro = (" Neurovascular indications (stroke/TIA): consider an alternative P2Y12 inhibitor such as ticagrelor; "
             "prasugrel is contraindicated with a history of stroke or TIA.")
    if c == "IM":
        return Rec(RED, "ACS and/or PCI: avoid standard-dose clopidogrel (75 mg) if possible; use prasugrel or "
                        "ticagrelor at standard dose if no contraindication." + neuro +
                        " Other cardiovascular indications: no CPIC recommendation.",
                   "Reduced activation; prefer prasugrel/ticagrelor for ACS/PCI.")
    if c == "PM":
        return Rec(RED, "ACS, PCI and other cardiovascular indications: avoid clopidogrel if possible; use "
                        "prasugrel or ticagrelor at standard dose if no contraindication." + neuro,
                   "Avoid; prefer prasugrel/ticagrelor (no prasugrel after stroke/TIA).")
    if c in ("UM", "RM"):
        return _std("Standard for ACS/PCI; context for other indications.",
                    "If considering clopidogrel, use standard dose (75 mg/day). Rapid/ultrarapid status does not "
                    "reduce efficacy.")
    return _std("Standard start.", "If considering clopidogrel, use standard dose (75 mg/day).")


# --------------------------------------------------------------------------- CYP2D6

def _codeine_like(other: str) -> Callable[[Genotypes], Rec]:
    """CPIC 2021 opioid guideline, Tables 2 (codeine) and 3 (tramadol). `other` = the drug to avoid switching to."""
    def rule(gt: Genotypes) -> Rec:
        c = gt.code("CYP2D6")
        if c == "UM":
            return Rec(RED, "Avoid because of potential for serious toxicity. If opioid use is warranted, consider "
                            f"a non-{other} opioid.", "Avoid: toxicity risk. Use a non-codeine/tramadol option.")
        if c == "PM":
            return Rec(RED, "Avoid because of possibility of diminished analgesia. If opioid use is warranted, "
                            f"consider a non-{other} opioid.",
                       "Avoid: little analgesia. Use a non-codeine/tramadol option.")
        if c == "IM":
            return Rec(YELLOW, "Use label-recommended age- or weight-specific dosing. If no response and opioid "
                               f"use is warranted, consider a non-{other} opioid.",
                       "Usual start; tramadol may give less analgesia. Switch if ineffective.")
        if c == "IND":
            return Rec(GREEN, "CYP2D6 indeterminate: no CPIC recommendation.", "No CPIC recommendation.")
        return _std("Label dosing.", "Use label-recommended age- or weight-specific dosing.")
    return rule


def hydrocodone(gt: Genotypes) -> Rec:
    """CPIC 2021 opioid guideline, Table 4."""
    c = gt.code("CYP2D6")
    if c in ("IM", "PM"):
        return Rec(YELLOW, "Use label-recommended age- or weight-specific dosing. If no response and opioid use is "
                           "warranted, consider a non-codeine, non-tramadol opioid.",
                   "Usual start; tramadol may give less analgesia. Switch if ineffective."
                   if c == "IM" else "Label dosing; switch if ineffective.")
    if c in ("UM", "IND"):
        return Rec(GREEN, "No CPIC recommendation (minimal evidence); label dosing.", "Label dosing.")
    return _std("Label dosing.", "Use label-recommended age- or weight-specific dosing.")


def no_cyp2d6_change(gt: Genotypes) -> Rec:
    # CPIC 2021 reviewed these opioids and made no CYP2D6-based recommendation.
    return Rec(GREEN, "No CPIC recommendation based on CYP2D6; dose per usual practice.", "No CPIC dose change.")


def antiemetic_5ht3(gt: Genotypes) -> Rec:
    """CPIC 2026 update, Table 2 (adults and children)."""
    c = gt.code("CYP2D6")
    if c == "UM":
        return Rec(RED, "Select an alternative not predominantly metabolized by CYP2D6 (e.g., granisetron); consider "
                        "interacting drugs and patient factors when choosing.",
                   "Reduced efficacy; use granisetron instead.")
    if c in ("IM", "PM", "IND"):
        return Rec(GREEN, "No CPIC recommendation (insufficient evidence); dose per usual practice.",
                   "No CPIC dose change.")
    return _std("Standard start.", "Initiate therapy with recommended starting dose.")


def atomoxetine(gt: Genotypes) -> Rec:
    """CPIC 2019, Table 3 (adults). Activity score 1.0 is split by whether CYP2D6*10 is present."""
    c, s = gt.code("CYP2D6"), gt.score("CYP2D6")
    child = " Children: weight-based dosing per CPIC Table 2."
    standard = ("Adults: start 40 mg/day and increase to 80 mg/day after 3 days; if no response and no adverse "
                "effects after 2 weeks, consider 100 mg/day. If still no response after 2 weeks, consider a peak "
                "plasma level (1–2 h post-dose).")
    slow = ("Adults: start 40 mg/day; if no response and no adverse effects after 2 weeks, increase to "
            "80 mg/day. If response is inadequate after 2 more weeks, consider a plasma level (2–4 h post-dose). "
            "Reduce the dose if side effects occur.")
    if c == "UM" or c == "NM" or (s is not None and s >= 1.0 and not gt.has_allele("CYP2D6", "*10")):
        if c == "UM":
            standard += " Ultrarapid metabolizers may need >100 mg/day."
        return Rec(GREEN, standard + child, "Standard start; titrate to response; level if needed.")
    if c in ("IM", "PM") or s is not None:
        return Rec(YELLOW, slow + child, "Start 40 mg/day; 80 mg only after 2 weeks; level if needed.")
    return _std()


def nortriptyline(gt: Genotypes) -> Rec:
    c = gt.code("CYP2D6")
    if c == "UM":
        return Rec(RED, "Avoid; select a drug not metabolized by CYP2D6. If a TCA is warranted, titrate to a "
                        "higher target dose with therapeutic drug monitoring." + TCA_DOSE_SCOPE,
                   "Avoid; low levels likely.")
    if c == "PM":
        return Rec(RED, "Avoid; select a drug not metabolized by CYP2D6. If a TCA is warranted, consider a 50% "
                        "reduction of the starting dose with therapeutic drug monitoring." + TCA_DOSE_SCOPE,
                   "Avoid; if needed, 50% dose with levels.")
    if c == "IM":
        return Rec(YELLOW, "Consider 25% dose reduction; use therapeutic drug monitoring." + TCA_DOSE_SCOPE,
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
    """CPIC 2024 beta-blocker guideline, Table 2."""
    c = gt.code("CYP2D6")
    if c == "PM":
        return Rec(YELLOW, "Initiate at the lowest recommended starting dose; titrate carefully to clinical effect or "
                           "guideline dose; monitor closely for bradycardia. Alternatively, consider another "
                           "beta-blocker. If already tolerating a stable dose, a change is probably unnecessary.",
                   "Low start, slow titration; bradycardia risk.")
    if c in ("UM", "IND"):
        return _std("Standard start.", "No CPIC recommendation (insufficient evidence); dose per usual practice.")
    return _std("Standard start.", "Initiate standard dosing.")


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
    """CPIC 2019, Table 2 (adults and children >=40 kg)."""
    c = gt.code("CYP2B6")
    tdm = (" If drug levels are available, check plasma concentrations (target ~1–4 µg/mL). A lower dose may "
           "need more than one pill a day in multidrug regimens.")
    if c == "IM":
        return Rec(YELLOW, "Consider initiating at 400 mg/day instead of 600 mg (higher CNS adverse-event risk)." + tdm,
                   "Consider 400 instead of 600 mg/day.")
    if c == "PM":
        return Rec(YELLOW, "Consider initiating at 400 or 200 mg/day instead of 600 mg (significantly higher CNS "
                           "adverse-event and discontinuation risk)." + tdm,
                   "Consider 400 or 200 mg/day instead of 600.")
    return _std("Standard 600 mg/day.", "Initiate with standard dosing (600 mg/day).")


def methadone(gt: Genotypes) -> Rec:
    """CPIC 2024, Table 2: CYP2B6 does not change methadone dosing; follow ECG monitoring guidelines."""
    if gt.code("CYP2B6") in ("UM", "IND"):
        return Rec(GREEN, "No CPIC recommendation for this CYP2B6 phenotype. Follow ECG monitoring guidelines.",
                   "Standard start.")
    return Rec(GREEN, "Standard dosing, titration and monitoring of methadone. CPIC found no evidence to support a "
                      "slower titration or different ECG monitoring based on CYP2B6; follow ECG monitoring guidelines.",
               "Standard start.")


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


# CPIC 2020 NSAID guideline, Tables 2-4.
_NSAID_STD = "Initiate with the recommended starting dose; use the lowest effective dose for the shortest duration."
_NSAID_ALTS = ("Alternatives not primarily metabolized by CYP2C9 include aspirin, ketorolac, naproxen and sulindac.")
_NSAID_IND = Rec(GREEN, "CYP2C9 indeterminate: no CPIC recommendation.", "Usual CYP2C9 dosing.")


def _nsaid(steady_days: int, ibuprofen: bool = False) -> Callable[[Genotypes], Rec]:
    """Table 2: celecoxib (steady state ~8 days), flurbiprofen, lornoxicam, ibuprofen (~5 days)."""
    def rule(gt: Genotypes) -> Rec:
        if gt.code("CYP2C9") == "IND":
            return _NSAID_IND
        s = _cyp2c9_as(gt)
        caution = (" Use extra caution with ibuprofen in CYP2C9*2 carriers (linked to CYP2C8*3)."
                   if ibuprofen and gt.has_allele("CYP2C9", "*2") else "")
        if s >= 1.5:
            extra = (" Intermediate metabolizers (AS 1.5) may have a higher risk of adverse events, especially with "
                     "hepatic impairment or advanced age." if s == 1.5 else "")
            return _std("Usual CYP2C9 dosing.", _NSAID_STD + extra + caution)
        if s >= 1.0:
            return Rec(YELLOW, "Initiate with the lowest recommended starting dose; titrate to clinical effect or "
                               "maximum dose with caution. Monitor blood pressure and kidney function." + caution,
                       "Lowest starting dose; titrate cautiously.")
        return Rec(YELLOW, "Initiate with 25–50% of the lowest recommended starting dose; titrate to clinical effect or "
                           f"25–50% of the maximum dose with caution, not before steady state (at least {steady_days} "
                           "days). Monitor blood pressure and kidney function. Alternatively, choose a drug not "
                           "metabolized by CYP2C9. " + _NSAID_ALTS + caution,
                   "Start 25–50% of lowest dose, or alternative.")
    return rule


def meloxicam(gt: Genotypes) -> Rec:
    """Table 3."""
    if gt.code("CYP2C9") == "IND":
        return _NSAID_IND
    s = _cyp2c9_as(gt)
    if s >= 1.5:
        return _std("Usual CYP2C9 dosing.", _NSAID_STD)
    if s >= 1.0:
        return Rec(YELLOW, "Initiate with 50% of the lowest recommended starting dose; titrate to clinical effect or 50% "
                           "of the maximum dose with caution, not before steady state (at least 7 days). Monitor "
                           "blood pressure and kidney function. Alternatively, choose an alternative therapy. "
                           + _NSAID_ALTS, "Start 50% of lowest dose.")
    return Rec(RED, "Choose an alternative not metabolized by CYP2C9 or not significantly affected by CYP2C9 "
                    "variants, or an NSAID metabolized by CYP2C9 but with a shorter half-life. " + _NSAID_ALTS,
               "Use an alternative NSAID/analgesic.")


def piroxicam(gt: Genotypes) -> Rec:
    """Table 4 (piroxicam and tenoxicam)."""
    if gt.code("CYP2C9") == "IND":
        return _NSAID_IND
    s = _cyp2c9_as(gt)
    if s >= 1.5:
        return _std("Usual CYP2C9 dosing.", _NSAID_STD)
    return Rec(RED, "Choose an alternative not metabolized by CYP2C9 or not significantly affected by CYP2C9 "
                    "variants, or an NSAID metabolized by CYP2C9 but with a shorter half-life. " + _NSAID_ALTS,
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

# CPIC 2017 update, Tables 2-3.
_HLA_TOLERANCE = (" If the patient has taken it continuously for more than 3 months without a skin reaction, "
                  "cautiously consider continued use.")
_AROMATIC = (" Use caution choosing another aromatic anticonvulsant (eslicarbazepine, lamotrigine, phenytoin, "
             "fosphenytoin, phenobarbital).")


def carbamazepine(gt: Genotypes) -> Rec:
    if gt.code("HLA-B*15:02") == "POS":
        return Rec(RED, "HLA-B*15:02 positive: if carbamazepine-naive, do not use (SJS/TEN risk)." + _HLA_TOLERANCE +
                   _AROMATIC, "HLA-B*15:02 positive: avoid if drug-naive.")
    if gt.code("HLA-A*31:01") == "POS":
        return Rec(RED, "HLA-A*31:01 positive: if carbamazepine-naive and alternatives are available, do not use "
                        "(SJS/TEN, DRESS, MPE risk). If no alternative, consider use with more frequent clinical "
                        "monitoring and stop at the first sign of a skin reaction." + _HLA_TOLERANCE,
                   "HLA-A*31:01 positive: prefer alternative.")
    return _std("No tested HLA restriction.", "Use per standard dosing guidelines.")


def oxcarbazepine(gt: Genotypes) -> Rec:
    if gt.code("HLA-B*15:02") == "POS":
        return Rec(RED, "HLA-B*15:02 positive: if oxcarbazepine-naive, do not use (SJS/TEN risk)." + _HLA_TOLERANCE +
                   _AROMATIC, "HLA-B*15:02 positive: avoid if drug-naive.")
    return _std("No tested HLA restriction.", "Use per standard dosing guidelines.")


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
    """CPIC 2025, Table 2 (oral, adults with resistant hypertension). NAT2 'normal' is the rapid phenotype."""
    c = gt.code("NAT2")
    if c == "PM":
        return Rec(YELLOW, "Resistant hypertension: initiate at a total daily dose of 40–75 mg; titrate carefully to "
                           "clinical effect or guideline-recommended dose; use caution at total daily doses of "
                           "200 mg or more (drug-induced lupus risk).",
                   "Resistant HTN: start 40–75 mg/day; caution ≥200.")
    if c in ("IM", "RM", "NM"):
        return Rec(YELLOW, "Resistant hypertension: consider a starting total daily dose of at least 75 mg and titrate "
                           "up to 300 mg/day as tolerated; rapid and intermediate acetylators typically need a 50–100% "
                           "higher maintenance dose than poor acetylators. Avoid twice-daily dosing; three or four "
                           "times daily is preferred.",
                   "Resistant HTN: start ≥75 mg/day; up to 300.")
    return Rec(GREEN, "NAT2 indeterminate: no CPIC recommendation.", "No CPIC recommendation.")


def _nat2_literature(slow_tier: str, text: str, short: str, note: str = "") -> Callable[[Genotypes], Rec]:
    def rule(gt: Genotypes) -> Rec:
        if gt.code("NAT2") == "PM":
            return Rec(slow_tier, text + note, short)
        return _std("Standard dosing.", "No acetylator-based change." + note)
    return rule


# CPIC 2023 G6PD guideline, Table 2: dapsone is high risk (strong) in G6PD deficiency. G6PD is not on the Quest panel.
G6PD_DAPSONE = (" G6PD is not tested on this panel: CPIC (2023) rates dapsone high risk for hemolysis in G6PD "
                "deficiency, so confirm G6PD status before use.")


def amifampridine(gt: Genotypes) -> Rec:
    if gt.code("NAT2") == "PM":
        return Rec(YELLOW, "Start 15 mg/day in poor metabolizers.", "Start 15 mg/day.")
    return _std("Label dosing.", "Label dosing.")


# --------------------------------------------------------------------------- other genes

def _fluoropyrimidine(tegafur: bool = False) -> Callable[[Genotypes], Rec]:
    """CPIC 2017 update, Table 2 (5-fluorouracil and capecitabine)."""
    note = (" Evidence for tegafur is very limited; CPIC's recommendations are for 5-FU and capecitabine."
            if tegafur else "")
    titrate = (" Then titrate: increase the dose in later cycles if there is no or tolerable toxicity in the first "
               "two cycles (or levels are subtherapeutic); decrease it if the starting dose is not tolerated.")

    def rule(gt: Genotypes) -> Rec:
        s = gt.score("DPYD")
        s = 2.0 if s is None else s
        if s >= 2.0:
            return _std("Standard DPYD starting dose.",
                        "No indication to change dose based on DPYD genotype; use label-recommended dosing." + note)
        if s >= 1.5:
            return Rec(YELLOW, "DPYD activity score 1.5: reduce the starting dose by 25% to 50%." + titrate + note,
                       "Start at 50–75% dose; titrate by toxicity.")
        if s >= 1.0:
            return Rec(YELLOW, "DPYD activity score 1.0: reduce the starting dose by 50%." + titrate + note,
                       "Start at 50% dose; titrate by toxicity.")
        if s > 0:
            return Rec(RED, f"DPYD activity score {s:.1f}: avoid 5-fluorouracil and its prodrugs. If no "
                            "fluoropyrimidine-free regimen is suitable, use a strongly reduced dose (estimated <25% "
                            "of normal) with early therapeutic drug monitoring; a DPD phenotyping test is advisable."
                            + note, "Avoid; severe toxicity risk.")
        return Rec(RED, "DPYD activity score 0: avoid 5-fluorouracil and 5-fluorouracil prodrug-based regimens." + note,
                   "Avoid; severe toxicity risk.")
    return rule


def _thiopurine(drug: str) -> Callable[[Genotypes], Rec]:
    """CPIC 2025 update: Table 2 (mercaptopurine), 3 (thioguanine, malignancy), 4 (azathioprine, nonmalignant).
    'Possible intermediate' phenotypes are treated as intermediate (the lab text contains 'Intermediate')."""
    std_dose = {"mercaptopurine": "75 mg/m²/day for malignancy or 1.5 mg/kg/day for nonmalignancy",
                "thioguanine": "40 mg/m²/day", "azathioprine": "2 mg/kg/day"}[drug]
    adjust = (" If the starting dose is already below standard, a reduction may not be needed. Adjust by "
              "myelosuppression and disease-specific guidelines; allow 2–4 weeks at each dose to reach steady state.")

    def rule(gt: Genotypes) -> Rec:
        t, n = gt.code("TPMT"), gt.code("NUDT15")
        if "PM" in (t, n):
            if drug == "azathioprine":
                return Rec(RED, "Consider an alternative nonthiopurine immunosuppressant (fatal toxicity possible "
                                "without dose decrease).", "Use a nonthiopurine alternative.")
            text = ("Malignancy: start with drastically reduced doses (reduce the daily dose 10-fold and give 3 "
                    "times weekly instead of daily); adjust by myelosuppression, allowing 4–6 weeks at each dose.")
            if drug == "mercaptopurine":
                text += " Nonmalignancy: consider an alternative nonthiopurine immunosuppressant."
            return Rec(RED, text, "Drastic reduction (10× lower, 3×/week) or alternative.")
        if t == "IM" and n == "IM":
            return Rec(YELLOW, f"TPMT/NUDT15 compound intermediate: start at 20–50% of the standard dose if the "
                               f"standard starting dose is ≥{std_dose}." + adjust,
                       "Start 20–50% dose; CBC monitoring.")
        if "IM" in (t, n):
            return Rec(YELLOW, f"Start at 30–80% of the standard dose if the standard starting dose is "
                               f"≥{std_dose}." + adjust, "Start 30–80% dose; CBC monitoring.")
        return _std("Standard start; CBC monitoring.",
                    f"Normal starting dose (e.g., {std_dose}); adjust per standard practice.")
    return rule


def atazanavir(gt: Genotypes) -> Rec:
    if gt.code("UGT1A1") == "PM":
        return Rec(RED, "Consider an alternative, particularly where jaundice would concern the patient. If "
                        "atazanavir is used, jaundice is likely: at least 20% (up to 60%) of poor metabolizers stop "
                        "it for that reason.", "Jaundice likely; consider alternative.")
    return _std("Usual start; monitor clinically.",
                "No need to avoid based on UGT1A1. Jaundice-related discontinuation is unlikely (less than about "
                "1 in 20); tell the patient this.")


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
    Drug("Clopidogrel", C, ("CYP2C19",), clopidogrel, source="CPIC 2022"),
    Drug("Metoprolol", C, ("CYP2D6",), metoprolol, source="CPIC 2024"),
    Drug("Simvastatin", C, ("SLCO1B1",), simvastatin),
    Drug("Lovastatin", C, ("SLCO1B1",), lovastatin),
    Drug("Atorvastatin", C, ("SLCO1B1",), atorvastatin),
    Drug("Rosuvastatin", C, ("SLCO1B1", "ABCG2"), rosuvastatin),
    Drug("Pitavastatin", C, ("SLCO1B1",), pitavastatin),
    Drug("Pravastatin", C, ("SLCO1B1",), pravastatin),
    Drug("Fluvastatin", C, ("SLCO1B1", "CYP2C9"), fluvastatin),
    Drug("Warfarin", C, ("CYP2C9", "VKORC1", "CYP4F2"), warfarin),
    Drug("Hydralazine", C, ("NAT2",), hydralazine, source="CPIC 2025"),
    Drug("Procainamide", C, ("NAT2",), _nat2_literature(
        RED, "Higher exposure and drug-induced lupus risk in slow acetylators.",
        "Higher exposure and lupus risk."), source="Literature"),
    # Pain & Anesthesia
    Drug("Codeine", P, ("CYP2D6",), _codeine_like("tramadol"), source="CPIC 2021"),
    Drug("Tramadol", P, ("CYP2D6",), _codeine_like("codeine"), source="CPIC 2021"),
    Drug("Hydrocodone", P, ("CYP2D6",), hydrocodone, source="CPIC 2021"),
    Drug("Oxycodone", P, ("CYP2D6",), no_cyp2d6_change, source="CPIC 2021"),
    Drug("Morphine", P, ("CYP2D6",), no_cyp2d6_change, source="CPIC 2021"),
    Drug("Hydromorphone", P, ("CYP2D6",), no_cyp2d6_change, source="CPIC 2021"),
    Drug("Fentanyl", P, ("CYP2D6",), no_cyp2d6_change, source="CPIC 2021"),
    Drug("Methadone", P, ("CYP2B6",), methadone, source="CPIC 2024"),
    Drug("Midazolam", P, ("CYP3A5",), midazolam, source="Literature"),
    Drug("Ondansetron", P, ("CYP2D6",), antiemetic_5ht3, source="CPIC 2026"),
    Drug("Tropisetron", P, ("CYP2D6",), antiemetic_5ht3, source="CPIC 2026"),
    Drug("Celecoxib", P, ("CYP2C9",), _nsaid(8), source="CPIC 2020"),
    Drug("Flurbiprofen", P, ("CYP2C9",), _nsaid(5), source="CPIC 2020"),
    Drug("Ibuprofen", P, ("CYP2C9",), _nsaid(5, ibuprofen=True), source="CPIC 2020"),
    Drug("Lornoxicam", P, ("CYP2C9",), _nsaid(5), source="CPIC 2020"),
    Drug("Meloxicam", P, ("CYP2C9",), meloxicam, source="CPIC 2020"),
    Drug("Piroxicam", P, ("CYP2C9",), piroxicam, source="CPIC 2020"),
    Drug("Tenoxicam", P, ("CYP2C9",), piroxicam, source="CPIC 2020"),
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
    Drug("Amitriptyline", Y, ("CYP2C19", "CYP2D6"), tertiary_tca, source="CPIC 2016"),
    Drug("Clomipramine", Y, ("CYP2C19", "CYP2D6"), tertiary_tca, source="CPIC 2016"),
    Drug("Doxepin", Y, ("CYP2C19", "CYP2D6"), tertiary_tca, source="CPIC 2016"),
    Drug("Imipramine", Y, ("CYP2C19", "CYP2D6"), tertiary_tca, source="CPIC 2016"),
    Drug("Trimipramine", Y, ("CYP2C19", "CYP2D6"), tertiary_tca, source="CPIC 2016"),
    Drug("Nortriptyline", Y, ("CYP2D6",), nortriptyline, source="CPIC 2016"),
    Drug("Desipramine", Y, ("CYP2D6",), nortriptyline, source="CPIC 2016"),
    Drug("Paroxetine", Y, ("CYP2D6",), paroxetine),
    Drug("Fluvoxamine", Y, ("CYP2D6",), fluvoxamine),
    Drug("Vortioxetine", Y, ("CYP2D6",), vortioxetine),
    Drug("Venlafaxine", Y, ("CYP2D6",), venlafaxine),
    Drug("Fluoxetine", Y, ("CYP2D6",), fluoxetine),
    Drug("Atomoxetine", Y, ("CYP2D6",), atomoxetine, source="CPIC 2019"),
    # Neurology
    Drug("Phenytoin", N, ("CYP2C9", "HLA-B*15:02"), phenytoin),
    Drug("Fosphenytoin", N, ("CYP2C9", "HLA-B*15:02"), phenytoin),
    Drug("Carbamazepine", N, ("HLA-B*15:02", "HLA-A*31:01"), carbamazepine, source="CPIC 2017"),
    Drug("Oxcarbazepine", N, ("HLA-B*15:02",), oxcarbazepine, source="CPIC 2017"),
    Drug("Amifampridine", N, ("NAT2",), amifampridine, source="FDA label"),
    # Infectious Disease
    Drug("Voriconazole", I, ("CYP2C19",), voriconazole),
    Drug("Efavirenz", I, ("CYP2B6",), efavirenz, source="CPIC 2019"),
    Drug("Isoniazid", I, ("NAT2",), _nat2_literature(
        RED, "Higher hepatotoxicity risk in slow acetylators; consider dose reduction.",
        "Hepatotoxicity risk; consider lower dose."), source="Literature"),
    Drug("Dapsone", I, ("NAT2",), _nat2_literature(
        YELLOW, "Higher adverse-effect risk in slow acetylators.", "Higher adverse-effect risk.",
        G6PD_DAPSONE),
         source="Literature"),
    Drug("Atazanavir", I, ("UGT1A1",), atazanavir, source="CPIC 2015"),
    Drug("Abacavir", I, ("HLA-B*57:01",), abacavir, source="CPIC 2012/2014"),
    Drug("Peginterferon alfa", I, ("IFNL3",), ifnl3),
    Drug("Ribavirin", I, ("IFNL3",), ifnl3),
    # Oncology, Immunology & Transplant
    Drug("Tamoxifen", O, ("CYP2D6",), tamoxifen),
    Drug("Tacrolimus", O, ("CYP3A5", "CYP3A4"), tacrolimus),
    Drug("Fluorouracil", O, ("DPYD",), _fluoropyrimidine(), source="CPIC 2017", short_name="5-FU"),
    Drug("Capecitabine", O, ("DPYD",), _fluoropyrimidine(), source="CPIC 2017"),
    Drug("Tegafur", O, ("DPYD",), _fluoropyrimidine(tegafur=True), source="CPIC 2017"),
    Drug("Azathioprine", O, ("TPMT", "NUDT15"), _thiopurine("azathioprine"), source="CPIC 2025"),
    Drug("Mercaptopurine", O, ("TPMT", "NUDT15"), _thiopurine("mercaptopurine"), source="CPIC 2025"),
    Drug("Thioguanine", O, ("TPMT", "NUDT15"), _thiopurine("thioguanine"), source="CPIC 2025"),
    Drug("Irinotecan", O, ("UGT1A1",), irinotecan, source="FDA/DPWG"),
    # Other
    Drug("Allopurinol", X, ("HLA-B*58:01",), allopurinol, source="CPIC 2013/2015"),
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
