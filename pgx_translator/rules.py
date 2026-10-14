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

RULES_VERSION = "3.0"

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
    """CPIC 2016 (CPT 2017), Table 2 (adults). Children: see CPIC Table 3."""
    c = gt.code("CYP2C19")
    alts = "isavuconazole, liposomal amphotericin B or posaconazole"
    if c in ("UM", "RM"):
        return Rec(RED, f"Choose an alternative agent not dependent on CYP2C19 as primary therapy ({alts}); therapeutic "
                        "concentrations are unlikely with standard dosing. Adult recommendation; see CPIC for children.",
                   "Select another antifungal; low exposure likely.")
    if c == "PM":
        return Rec(RED, f"Choose an alternative agent not dependent on CYP2C19 ({alts}). If voriconazole is the most "
                        "appropriate agent, give a preferably lower than standard dose with careful therapeutic drug "
                        "monitoring. Adult recommendation; see CPIC for children.",
                   "Select another antifungal; toxicity risk. If used, lower dose + levels.")
    return _std("Standard start; levels per usual practice.",
                "Initiate therapy with recommended standard-of-care dosing; trough levels per usual practice "
                "(suggested 1.0–4.0 mcg/mL for most invasive mycoses).")


def citalopram(gt: Genotypes) -> Rec:
    """CPIC 2023 SSRI guideline, Table 3a (citalopram, escitalopram)."""
    c = gt.code("CYP2C19")
    if c == "UM":
        return Rec(RED, "Consider a clinically appropriate alternative antidepressant not predominantly metabolized by "
                        "CYP2C19. If citalopram or escitalopram is warranted and efficacy is inadequate at standard "
                        "maintenance dosing, consider titrating to a higher maintenance dose.",
                   "Prefer an antidepressant less CYP2C19-dependent.")
    if c == "PM":
        return Rec(RED, "Consider a clinically appropriate alternative antidepressant not predominantly metabolized by "
                        "CYP2C19. If warranted, consider a lower starting dose, slower titration and a 50% reduction of "
                        "the standard maintenance dose (FDA: citalopram maximum 20 mg/day in CYP2C19 poor "
                        "metabolizers because of QT risk).",
                   "Prefer alternative; if used, ~50% dose (citalopram ≤20 mg).")
    if c == "IM":
        return Rec(YELLOW, "Initiate the recommended starting dose; consider a slower titration schedule and a lower "
                           "maintenance dose than normal metabolizers.",
                   "Standard start; slower titration, lower maintenance.")
    if c == "RM":
        return _std("Standard start; titrate if response inadequate.",
                    "Initiate the recommended starting dose. If the patient does not respond to recommended "
                    "maintenance dosing, consider a higher maintenance dose or an alternative not predominantly "
                    "metabolized by CYP2C19.")
    if c == "IND":
        return _std("Standard start.", "CYP2C19 indeterminate: no CPIC recommendation.")
    return _std("Standard start.", "Initiate therapy with the recommended starting dose.")


def sertraline(gt: Genotypes) -> Rec:
    """CPIC 2023 SSRI guideline, Table 5 (CYP2C19 x CYP2B6). Likely phenotypes count as confirmed."""
    c19, b6 = gt.code("CYP2C19"), gt.code("CYP2B6")
    c19 = {"RM": "UM"}.get(c19, c19)
    b6 = {"RM": "UM"}.get(b6, b6)
    std = Rec(GREEN, "Initiate therapy with the recommended starting dose.", "Standard start.")
    slow = Rec(YELLOW, "Initiate the recommended starting dose; consider a slower titration schedule and a lower "
                       "maintenance dose than normal metabolizers.",
               "Standard start; slower titration, lower maintenance.")

    def lower(pct: int, alt: bool) -> Rec:
        tail = " or select a clinically appropriate alternative antidepressant." if alt else "."
        return Rec(YELLOW, f"Consider a lower starting dose, slower titration and a {pct}% reduction of the standard "
                           "maintenance dose" + tail, f"Lower start, slower titration; ~{pct}% lower maintenance.")

    if c19 == "UM":
        if b6 == "UM":
            return Rec(GREEN, "Initiate the recommended starting dose. If the patient does not respond adequately, "
                              "consider a higher maintenance dose or switching to an antidepressant not predominantly "
                              "metabolized by CYP2C19 or CYP2B6.", "Standard start.")
        return std
    if c19 == "NM":
        return {"IM": slow, "PM": lower(25, True)}.get(b6, std)
    if c19 == "IM":
        return {"UM": std, "PM": lower(50, False)}.get(b6, slow)
    if c19 == "PM":
        if b6 == "PM":
            return Rec(RED, "Select an alternative antidepressant not primarily metabolized by CYP2C19 or CYP2B6.",
                       "Prefer an alternative antidepressant.")
        return lower(50, True)
    # CYP2C19 indeterminate
    return {"IM": slow, "PM": lower(25, True)}.get(b6, std)


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
    """CPIC 2020, Table 2 (omeprazole, lansoprazole, pantoprazole, dexlansoprazole)."""
    c = gt.code("CYP2C19")
    if c == "UM":
        return Rec(YELLOW, "Increase starting daily dose by 100%; the daily dose may be given in divided doses. "
                           "Monitor for efficacy.", "Consider 2× starting daily dose; assess response.")
    if c in ("RM", "NM"):
        return _std("Standard start.", "Initiate standard starting daily dose. Consider increasing the dose by "
                                       "50–100% for H. pylori infection or erosive esophagitis (may be divided). "
                                       "Monitor for efficacy.")
    if c in ("IM", "PM"):
        return _std("Standard start; chronic use may allow 50% reduction.",
                    "Initiate standard starting daily dose. For chronic therapy (>12 weeks) with efficacy achieved, "
                    "consider a 50% reduction in daily dose and monitor for continued efficacy.")
    return _std("Standard start.", "CYP2C19 indeterminate: no CPIC recommendation; use standard dosing.")


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
    """CPIC 2023 SSRI guideline, Table 2a."""
    c = gt.code("CYP2D6")
    if c == "UM":
        return Rec(RED, "Select an alternative drug not predominantly metabolized by CYP2D6.",
                   "Low levels likely; prefer an alternative.")
    if c == "IM":
        return Rec(YELLOW, "Consider a lower starting dose and slower titration schedule than normal metabolizers.",
                   "Consider lower start and slower titration.")
    if c == "PM":
        return Rec(YELLOW, "Consider a 50% reduction of the recommended starting dose, a slower titration schedule and "
                           "a 50% lower maintenance dose than normal metabolizers.",
                   "Consider 50% starting dose, slower titration.")
    if c == "IND":
        return _std("Standard start.", "CYP2D6 indeterminate: no CPIC recommendation.")
    return _std("Standard start.", "Initiate therapy with the recommended starting dose.")


def fluvoxamine(gt: Genotypes) -> Rec:
    """CPIC 2023 SSRI guideline, Table 2b."""
    c = gt.code("CYP2D6")
    if c == "PM":
        return Rec(YELLOW, "Consider a 25–50% lower starting dose and slower titration schedule than normal "
                           "metabolizers, or a clinically appropriate alternative not predominantly metabolized by "
                           "CYP2D6.", "Consider lower start and slower titration.")
    if c in ("UM", "IND"):
        return _std("Standard start.", "No CPIC recommendation for this CYP2D6 phenotype.")
    return _std("Standard start.", "Initiate therapy with the recommended starting dose.")


def vortioxetine(gt: Genotypes) -> Rec:
    """CPIC 2023 SSRI guideline, Table 2d."""
    c = gt.code("CYP2D6")
    if c == "PM":
        return Rec(YELLOW, "Initiate 50% of the starting dose (e.g., 5 mg) and titrate to a maximum of 10 mg, or "
                           "consider an alternative antidepressant not predominantly metabolized by CYP2D6.",
                   "Start 50% dose; max 10 mg/day.")
    if c == "UM":
        return Rec(RED, "Select an alternative drug not predominantly metabolized by CYP2D6. If vortioxetine is "
                        "warranted, start at the standard dose and titrate; the maintenance dose may need to be 50% or "
                        "more higher.", "Low levels likely; prefer an alternative.")
    if c == "IND":
        return _std("Standard start.", "CYP2D6 indeterminate: no CPIC recommendation.")
    return _std("Standard start.", "Initiate therapy with the recommended starting dose.")


def venlafaxine(gt: Genotypes) -> Rec:
    """CPIC 2023 SSRI guideline, Table 2c."""
    c = gt.code("CYP2D6")
    if c == "PM":
        return Rec(RED, "Consider a clinically appropriate alternative antidepressant not predominantly metabolized by "
                        "CYP2D6.", "Prefer an alternative antidepressant.")
    if c in ("UM", "IM", "IND"):
        return _std("Standard start.", "No action recommended based on CYP2D6 (minimal evidence).")
    return _std("Standard start.", "Initiate therapy with the recommended starting dose.")


def fluoxetine(gt: Genotypes) -> Rec:
    # CPIC 2023 SSRI guideline: no gene-based dosing recommendation for fluoxetine (CPIC level C).
    return Rec(GREEN, "No CPIC gene-based dosing recommendation; dose per usual practice.", "No CPIC dose change.")


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
    """CPIC 2018, Table 2. Activity score 1.0 is split by CYP2D6*10 (optional without *10, moderate with it)."""
    c = gt.code("CYP2D6")
    alt = ("Consider hormonal therapy such as an aromatase inhibitor for postmenopausal women, or an aromatase "
           "inhibitor with ovarian function suppression for premenopausal women, given these are superior to tamoxifen "
           "regardless of CYP2D6. If an aromatase inhibitor is contraindicated, consider the higher FDA-approved "
           "tamoxifen dose (40 mg/day). Avoid moderate and strong CYP2D6 inhibitors; switch to a weak inhibitor.")
    if c == "PM":
        return Rec(RED, "Recommend alternative hormonal therapy such as an aromatase inhibitor (with ovarian function "
                        "suppression if premenopausal). Higher-dose tamoxifen (40 mg/day) increases but does not "
                        "normalize endoxifen levels; consider it only if aromatase inhibitors are contraindicated.",
                   "Oncology review: prefer alternative hormonal therapy.")
    if c == "IM":
        return Rec(YELLOW, alt, "Oncology review: alternative or dose strategy; AS 1 optional."
                   if gt.score("CYP2D6") == 1.0 and not gt.has_allele("CYP2D6", "*10")
                   else "Oncology review: alternative or 40 mg/day.")
    return _std("Standard 20 mg/day; avoid CYP2D6 inhibitors.",
                "Initiate standard-of-care dosing (tamoxifen 20 mg/day). Avoid moderate and strong CYP2D6 inhibitors.")


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
    """CPIC 2015, Table 2 (kidney, heart, lung, HSCT; liver when donor and recipient genotypes match)."""
    c = gt.code("CYP3A5")
    note = ""
    if gt.code("CYP3A4") in ("IM", "PM"):
        note = (" CYP3A4*22 (not part of the CPIC guideline) may lower the dose requirement, so monitor troughs "
                "closely.")
    if c in ("NM", "IM"):
        return Rec(YELLOW, "CYP3A5 expresser: increase the starting dose 1.5–2 times the recommended starting dose; "
                           "total starting dose should not exceed 0.3 mg/kg/day. Use therapeutic drug monitoring to "
                           "guide dose adjustments." + note, "Higher start (1.5–2×); drug levels.")
    return Rec(GREEN, "CYP3A5 nonexpresser: initiate the standard recommended dose; use therapeutic drug monitoring to "
                      "guide dose adjustments." + note, "Standard start; needs drug levels.")


def midazolam(gt: Genotypes) -> Rec:
    return Rec(GREEN, "No PGx dose change; titrate to effect.", "No CPIC dose change.", source="Literature")


# --------------------------------------------------------------------------- SLCO1B1 statins

def simvastatin(gt: Genotypes) -> Rec:
    """CPIC 2022 statin guideline, Table 2."""
    c = gt.code("SLCO1B1")
    if c == "DF":
        return Rec(RED, "Prescribe an alternative statin depending on desired potency. If simvastatin is warranted, "
                        "limit the dose to <20 mg/day.", "Alternative statin; if used: simva <20, lova ≤20 mg/day.")
    if c == "PF":
        return Rec(RED, "Prescribe an alternative statin depending on desired potency.", "Alternative statin.")
    return _std("Standard start.", "Prescribe desired starting dose and adjust per disease-specific guidelines.")


def lovastatin(gt: Genotypes) -> Rec:
    """CPIC 2022 statin guideline, Table 2."""
    c = gt.code("SLCO1B1")
    if c == "DF":
        return Rec(RED, "Prescribe an alternative statin depending on desired potency. If lovastatin is warranted, "
                        "limit the dose to ≤20 mg/day.", "Alternative statin; if used: simva <20, lova ≤20 mg/day.")
    if c == "PF":
        return Rec(RED, "Prescribe an alternative statin depending on desired potency.", "Alternative statin.")
    return _std("Standard start.", "Prescribe desired starting dose and adjust per disease-specific guidelines.")


def atorvastatin(gt: Genotypes) -> Rec:
    """CPIC 2022 statin guideline, Table 2."""
    c = gt.code("SLCO1B1")
    if c == "DF":
        return Rec(YELLOW, "Prescribe ≤40 mg as a starting dose and adjust per disease-specific guidelines; myopathy "
                           "risk is higher, especially at 40 mg. If >40 mg is needed, consider combination therapy "
                           "(atorvastatin plus nonstatin guideline-directed therapy).",
                   "Usual start; muscle-risk vigilance at high doses.")
    if c == "PF":
        return Rec(YELLOW, "Prescribe ≤20 mg as a starting dose and adjust per disease-specific guidelines. If >20 mg "
                           "is needed, consider rosuvastatin or combination therapy (atorvastatin plus nonstatin "
                           "guideline-directed therapy).", "Start ≤20 mg/day; monitor muscle symptoms.")
    return _std("Standard start.", "Prescribe desired starting dose and adjust per disease-specific guidelines.")


def rosuvastatin(gt: Genotypes) -> Rec:
    """CPIC 2022 statin guideline, Table 5 (SLCO1B1 x ABCG2)."""
    s, a = gt.code("SLCO1B1"), gt.code("ABCG2")
    asian = " Consider Asian ancestry and population-specific dosing."
    if a == "PF":
        cap = 10 if s in ("DF", "PF") else 20
    elif s == "PF":
        cap = 20
    else:
        cap = None
    if cap:
        return Rec(YELLOW, f"Prescribe ≤{cap} mg as a starting dose and adjust per disease- and population-specific "
                           f"guidelines. If >{cap} mg is needed, consider an alternative statin or combination therapy "
                           "(rosuvastatin plus nonstatin guideline-directed therapy)." + asian,
                   f"Start ≤{cap} mg/day; monitor muscle symptoms.")
    if s == "DF":
        return Rec(GREEN, "Prescribe desired starting dose and adjust per disease- and population-specific guidelines; "
                          "be aware of possible increased myopathy risk, especially at doses >20 mg." + asian,
                   "Usual start; muscle-risk vigilance above 20 mg/day.")
    return _std("Standard start.", "Prescribe desired starting dose and adjust per disease- and population-specific "
                                   "guidelines." + asian)


def pitavastatin(gt: Genotypes) -> Rec:
    """CPIC 2022 statin guideline, Table 2."""
    c = gt.code("SLCO1B1")
    if c == "DF":
        return Rec(YELLOW, "Prescribe ≤2 mg as a starting dose and adjust per disease-specific guidelines. If >2 mg is "
                           "needed, consider an alternative statin or combination therapy.",
                   "Start ≤2 mg/day; monitor muscle symptoms.")
    if c == "PF":
        return Rec(YELLOW, "Prescribe ≤1 mg as a starting dose and adjust per disease-specific guidelines. If >1 mg is "
                           "needed, consider an alternative statin or combination therapy.",
                   "Start ≤1 mg/day; monitor muscle symptoms.")
    return _std("Standard start.", "Prescribe desired starting dose and adjust per disease-specific guidelines.")


def pravastatin(gt: Genotypes) -> Rec:
    """CPIC 2022 statin guideline, Table 2."""
    c = gt.code("SLCO1B1")
    if c == "PF":
        return Rec(YELLOW, "Prescribe ≤40 mg as a starting dose and adjust per disease-specific guidelines. If "
                           "tolerating 40 mg but higher potency is needed, a higher dose, an alternative statin or "
                           "combination therapy could be considered; myopathy risk is higher above 40 mg.",
                   "Start ≤40 mg/day; monitor muscle symptoms.")
    if c == "DF":
        return _std("Usual start; myopathy risk higher above 40 mg/day.",
                    "Prescribe desired starting dose and adjust per disease-specific guidelines. Be aware of possible "
                    "increased myopathy risk, especially at doses >40 mg/day.")
    return _std("Standard start.", "Prescribe desired starting dose and adjust per disease-specific guidelines.")


def fluvastatin(gt: Genotypes) -> Rec:
    """CPIC 2022 statin guideline, Table 6 (SLCO1B1 x CYP2C9)."""
    s, c9 = gt.code("SLCO1B1"), gt.code("CYP2C9")
    alt = Rec(RED, "Prescribe an alternative statin depending on desired potency.", "Alternative statin.")

    def cap(mg: int) -> Rec:
        return Rec(YELLOW, f"Prescribe ≤{mg} mg/day as a starting dose and adjust per disease-specific guidelines. "
                           f"If >{mg} mg is needed, consider an alternative statin or combination therapy.",
                   f"Start ≤{mg} mg/day.")
    if s == "PF":
        return cap(40) if c9 == "NM" else alt
    if s == "DF":
        if c9 == "PM":
            return alt
        if c9 == "IM":
            return cap(20)
        return _std("Standard start.", "Prescribe desired starting dose; be aware of possible increased myopathy "
                                       "risk, especially at doses >40 mg/day.")
    if c9 == "IM":
        return cap(40)
    if c9 == "PM":
        return cap(20)
    return _std("Standard start.", "Prescribe desired starting dose and adjust per disease-specific guidelines.")


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
    """CPIC 2020 update, Table 3 (phenytoin/fosphenytoin)."""
    if gt.code("HLA-B*15:02") == "POS":
        return Rec(RED, "HLA-B*15:02 positive: if phenytoin-naive, do not use phenytoin/fosphenytoin; avoid "
                        "carbamazepine and oxcarbazepine. If phenytoin has been used continuously for more than 3 "
                        "months without a skin reaction, cautiously consider future use. Use caution with other "
                        "aromatic anticonvulsants.", "HLA-B*15:02 positive: avoid if drug-naive.")
    if gt.code("CYP2C9") == "IND":
        return _std("Standard start; drug levels.", "CYP2C9 indeterminate: no CPIC recommendation.")
    s = _cyp2c9_as(gt)
    monitor = (" Adjust later doses by therapeutic drug monitoring, response and side effects. A negative "
               "HLA-B*15:02 result does not remove all SJS/TEN risk; monitor per standard practice.")
    if s >= 1.5:
        return _std("Standard start; drug levels.", "No adjustment needed; use typical dosing strategies." + monitor)
    if s >= 1.0:
        return Rec(YELLOW, "Typical first (loading) dose; use about 25% less than the typical maintenance dose for "
                           "subsequent doses." + monitor, "~25% lower maintenance dose; drug levels.")
    return Rec(YELLOW, "Typical first (loading) dose; use about 50% less than the typical maintenance dose for "
                       "subsequent doses." + monitor, "~50% lower maintenance dose; drug levels.")


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
    """CPIC 2014, Table 2 (peginterferon alfa and ribavirin regimens)."""
    if gt.code("IFNL3") == "UNFAV":
        return Rec(YELLOW, "Unfavorable response genotype: about 30% chance of SVR after 48 weeks of peginterferon "
                           "and ribavirin (about 60% with protease inhibitor combinations). Consider implications "
                           "before starting peginterferon-containing regimens.", "Lower response; prefer DAAs.")
    return Rec(GREEN, "Favorable response genotype: about 70% chance of SVR after 48 weeks of peginterferon and "
                      "ribavirin (about 90% with protease inhibitor combinations).", "Favorable response genotype.")


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
    Drug("Simvastatin", C, ("SLCO1B1",), simvastatin, source="CPIC 2022"),
    Drug("Lovastatin", C, ("SLCO1B1",), lovastatin, source="CPIC 2022"),
    Drug("Atorvastatin", C, ("SLCO1B1",), atorvastatin, source="CPIC 2022"),
    Drug("Rosuvastatin", C, ("SLCO1B1", "ABCG2"), rosuvastatin, source="CPIC 2022"),
    Drug("Pitavastatin", C, ("SLCO1B1",), pitavastatin, source="CPIC 2022"),
    Drug("Pravastatin", C, ("SLCO1B1",), pravastatin, source="CPIC 2022"),
    Drug("Fluvastatin", C, ("SLCO1B1", "CYP2C9"), fluvastatin, source="CPIC 2022"),
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
    Drug("Omeprazole", G, ("CYP2C19",), ppi, source="CPIC 2020"),
    Drug("Lansoprazole", G, ("CYP2C19",), ppi, source="CPIC 2020"),
    Drug("Pantoprazole", G, ("CYP2C19",), ppi, source="CPIC 2020"),
    Drug("Dexlansoprazole", G, ("CYP2C19",), ppi, source="CPIC 2020"),
    Drug("Esomeprazole", G, ("CYP2C19",), ppi_no_rec),
    Drug("Rabeprazole", G, ("CYP2C19",), ppi_no_rec),
    Drug("Sulfasalazine", G, ("NAT2",), _nat2_literature(
        YELLOW, "Higher adverse-effect risk in slow acetylators.", "Higher adverse-effect risk."),
         source="Literature"),
    # Psychiatry
    Drug("Citalopram", Y, ("CYP2C19",), citalopram, source="CPIC 2023"),
    Drug("Escitalopram", Y, ("CYP2C19",), citalopram, source="CPIC 2023"),
    Drug("Sertraline", Y, ("CYP2C19", "CYP2B6"), sertraline, source="CPIC 2023"),
    Drug("Amitriptyline", Y, ("CYP2C19", "CYP2D6"), tertiary_tca, source="CPIC 2016"),
    Drug("Clomipramine", Y, ("CYP2C19", "CYP2D6"), tertiary_tca, source="CPIC 2016"),
    Drug("Doxepin", Y, ("CYP2C19", "CYP2D6"), tertiary_tca, source="CPIC 2016"),
    Drug("Imipramine", Y, ("CYP2C19", "CYP2D6"), tertiary_tca, source="CPIC 2016"),
    Drug("Trimipramine", Y, ("CYP2C19", "CYP2D6"), tertiary_tca, source="CPIC 2016"),
    Drug("Nortriptyline", Y, ("CYP2D6",), nortriptyline, source="CPIC 2016"),
    Drug("Desipramine", Y, ("CYP2D6",), nortriptyline, source="CPIC 2016"),
    Drug("Paroxetine", Y, ("CYP2D6",), paroxetine, source="CPIC 2023"),
    Drug("Fluvoxamine", Y, ("CYP2D6",), fluvoxamine, source="CPIC 2023"),
    Drug("Vortioxetine", Y, ("CYP2D6",), vortioxetine, source="CPIC 2023"),
    Drug("Venlafaxine", Y, ("CYP2D6",), venlafaxine, source="CPIC 2023"),
    Drug("Fluoxetine", Y, ("CYP2D6",), fluoxetine, source="CPIC 2023"),
    Drug("Atomoxetine", Y, ("CYP2D6",), atomoxetine, source="CPIC 2019"),
    # Neurology
    Drug("Phenytoin", N, ("CYP2C9", "HLA-B*15:02"), phenytoin, source="CPIC 2020"),
    Drug("Fosphenytoin", N, ("CYP2C9", "HLA-B*15:02"), phenytoin, source="CPIC 2020"),
    Drug("Carbamazepine", N, ("HLA-B*15:02", "HLA-A*31:01"), carbamazepine, source="CPIC 2017"),
    Drug("Oxcarbazepine", N, ("HLA-B*15:02",), oxcarbazepine, source="CPIC 2017"),
    Drug("Amifampridine", N, ("NAT2",), amifampridine, source="FDA label"),
    # Infectious Disease
    Drug("Voriconazole", I, ("CYP2C19",), voriconazole, source="CPIC 2016"),
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
    Drug("Peginterferon alfa", I, ("IFNL3",), ifnl3, source="CPIC 2014"),
    Drug("Ribavirin", I, ("IFNL3",), ifnl3, source="CPIC 2014"),
    # Oncology, Immunology & Transplant
    Drug("Tamoxifen", O, ("CYP2D6",), tamoxifen, source="CPIC 2018"),
    Drug("Tacrolimus", O, ("CYP3A5", "CYP3A4"), tacrolimus, source="CPIC 2015"),
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
