"""Patient medication list: match what the operator types to the CPIC drug catalog.

The catalog has three kinds of entries:

* "rule"     - a drug with a rule in rules.py (evaluated against this patient's genotype)
* "untested" - CPIC has a guideline, but its gene is not on the Quest panel (e.g. G6PD, RYR1)
* "norec"    - CPIC reviewed the drug and made no gene-based recommendation

Anything else the operator enters is reported as "unknown" (no CPIC gene-drug guideline found).
Entries are matched by generic or brand name, ignoring doses ("Lipitor 40 mg daily" -> atorvastatin),
and combination products match every CPIC drug they contain ("Tylenol #3" -> codeine).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Optional

from .rules import DRUGS_BY_NAME, DrugResult

UNTESTED, NOREC, UNKNOWN, RULE, NONE = "untested", "norec", "unknown", "rule", "none"
GREY = "grey"


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    genes: tuple[str, ...]
    text: str
    short: str
    source: str


def _untested(gene: str, guideline: str, items: dict[str, tuple[str, str]]) -> list[CatalogEntry]:
    return [CatalogEntry(name, (gene,), f"{gene} is not tested on the Quest panel. {text}", short, guideline)
            for name, (text, short) in items.items()]


def _norec(names: list[str], genes: tuple[str, ...], why: str, source: str) -> list[CatalogEntry]:
    return [CatalogEntry(n, genes, why, "No CPIC gene-based recommendation.", source) for n in names]


_G6PD = "CPIC 2023"
_G6PD_HIGH = ("CPIC rates this drug HIGH risk for acute hemolytic anemia in G6PD deficiency (generally avoid). "
              "Confirm G6PD status before use.")
_G6PD_MED = ("CPIC rates this drug MEDIUM risk in G6PD deficiency (use with caution). Confirm G6PD status before "
             "use.")
_G6PD_LOW = "CPIC rates this drug low-to-no risk in G6PD deficiency (no added hemolysis risk expected)."
_G6PD_NONE = "CPIC (G6PD, 2023) reviewed this drug and assigned no risk level (no recommendation)."
_MH = ("CPIC (2019): halogenated volatile anesthetics and succinylcholine are relatively contraindicated in "
       "malignant hyperthermia susceptibility. Ask about personal/family history of malignant hyperthermia.")
_AMINO = ("CPIC (MT-RNR1): avoid aminoglycosides in carriers of an MT-RNR1 variant linked to hearing loss unless "
          "the infection risk outweighs permanent hearing loss.")

EXTRA_ENTRIES: list[CatalogEntry] = [
    # G6PD (CPIC 2023, Table 2) -- G6PD is not on the Quest panel. Dapsone and sulfasalazine have rules.
    *_untested("G6PD", _G6PD, {
        n: (_G6PD_HIGH, "G6PD not tested; HIGH hemolysis risk if deficient.")
        for n in ["Methylene blue", "Pegloticase", "Primaquine", "Rasburicase", "Tafenoquine", "Toluidine blue"]}),
    *_untested("G6PD", _G6PD, {"Nitrofurantoin": (_G6PD_MED, "G6PD not tested; medium hemolysis risk if deficient.")}),
    *_untested("G6PD", _G6PD, {
        n: (_G6PD_LOW, "G6PD not tested; low-to-no risk.")
        for n in ["Aminosalicylic acid", "Chloramphenicol", "Chloroquine", "Ciprofloxacin", "Dimercaprol",
                  "Doxorubicin", "Furazolidone", "Glyburide", "Hydroxychloroquine", "Mafenide", "Nalidixic acid",
                  "Norfloxacin", "Ofloxacin", "Phenazopyridine", "Quinine", "Sulfadiazine", "Sulfadimidine",
                  "Sulfamethoxazole", "Sulfanilamide", "Sulfisoxazole", "Tolbutamide", "Vitamin C", "Vitamin K"]}),
    *_norec(["Chlorpropamide", "Dabrafenib", "Gliclazide", "Glimepiride", "Glipizide", "Mepacrine", "Mesalamine",
             "Moxifloxacin", "Nicorandil", "Nitrofural", "Probenecid", "Sodium nitrite", "Sulfacetamide",
             "Tolazamide", "Trametinib"], ("G6PD",), _G6PD_NONE, _G6PD),
    # RYR1 / CACNA1S (CPIC 2019) -- not on the Quest panel.
    *[CatalogEntry(n, ("RYR1", "CACNA1S"), "RYR1 and CACNA1S are not tested on the Quest panel. " + _MH,
                   "RYR1/CACNA1S not tested; MH-triggering agent.", "CPIC 2019")
      for n in ["Desflurane", "Enflurane", "Halothane", "Isoflurane", "Methoxyflurane", "Sevoflurane",
                "Succinylcholine"]],
    # MT-RNR1 (CPIC 2021) -- not on the Quest panel.
    *[CatalogEntry(n, ("MT-RNR1",), "MT-RNR1 is not tested on the Quest panel. " + _AMINO,
                   "MT-RNR1 not tested; hearing-loss risk if variant carrier.", "CPIC 2021")
      for n in ["Amikacin", "Gentamicin", "Kanamycin", "Streptomycin", "Tobramycin"]],
    # CFTR (CPIC 2014) -- not on the Quest panel.
    CatalogEntry("Ivacaftor", ("CFTR",), "CFTR is not tested on the Quest panel. CPIC recommends ivacaftor only for "
                 "patients with specific CFTR variants; use CFTR genotyping.", "CFTR not tested.", "CPIC 2014"),
    # Panel genes, CPIC reviewed and made no recommendation.
    *_norec(["Aceclofenac", "Aspirin", "Diclofenac", "Indomethacin", "Lumiracoxib", "Metamizole", "Nabumetone",
             "Naproxen"], ("CYP2C9",),
            "CPIC (NSAIDs, 2020): not significantly affected by CYP2C9 variants, or insufficient evidence; no "
            "recommendation.", "CPIC 2020"),
    *_norec(["Carvedilol"], ("CYP2D6",),
            "CPIC (beta-blockers, 2024): insufficient evidence for CYP2D6-based carvedilol dosing; no "
            "recommendation.", "CPIC 2024"),
    *_norec(["Alfentanil", "Buprenorphine", "Levomethadone", "Naltrexone", "Remifentanil", "Sufentanil"],
            ("OPRM1", "COMT"), "CPIC (opioids, 2021) reviewed this drug and made no gene-based recommendation.",
            "CPIC 2021"),
    *_norec(["Duloxetine"], ("CYP2D6",),
            "CPIC (2023): existing data do not support a meaningful CYP2D6 effect on duloxetine; no "
            "recommendation.", "CPIC 2023"),
    *_norec(["Desvenlafaxine", "Levomilnacipran", "Milnacipran", "Vilazodone"], ("CYP2D6", "CYP2C19"),
            "CPIC (2023): not significantly affected by CYP2D6/CYP2C19; no recommendation.", "CPIC 2023"),
    *_norec(["Dolasetron", "Palonosetron", "Ramosetron"], ("CYP2D6",),
            "CPIC (5-HT3 antagonists, 2026): limited evidence for CYP2D6-guided use; no recommendation.",
            "CPIC 2026"),
]
EXTRA_BY_NAME = {e.name: e for e in EXTRA_ENTRIES}

# Brand names and other aliases -> catalog name(s). Lower case; punctuation is ignored when matching.
ALIASES: dict[str, list[str]] = {
    # cardiology
    "plavix": ["Clopidogrel"], "lopressor": ["Metoprolol"], "toprol": ["Metoprolol"], "toprol xl": ["Metoprolol"],
    "kapspargo": ["Metoprolol"], "zocor": ["Simvastatin"], "vytorin": ["Simvastatin"], "mevacor": ["Lovastatin"],
    "altoprev": ["Lovastatin"], "lipitor": ["Atorvastatin"], "caduet": ["Atorvastatin"], "crestor": ["Rosuvastatin"],
    "ezallor": ["Rosuvastatin"], "livalo": ["Pitavastatin"], "zypitamag": ["Pitavastatin"],
    "pravachol": ["Pravastatin"], "lescol": ["Fluvastatin"], "coumadin": ["Warfarin"], "jantoven": ["Warfarin"],
    "apresoline": ["Hydralazine"], "bidil": ["Hydralazine"], "coreg": ["Carvedilol"],
    # pain / anesthesia
    "tylenol with codeine": ["Codeine"], "tylenol 3": ["Codeine"], "tylenol 4": ["Codeine"],
    "ultram": ["Tramadol"], "ultracet": ["Tramadol"], "conzip": ["Tramadol"], "norco": ["Hydrocodone"],
    "vicodin": ["Hydrocodone"], "lortab": ["Hydrocodone"], "hysingla": ["Hydrocodone"], "zohydro": ["Hydrocodone"],
    "oxycontin": ["Oxycodone"], "roxicodone": ["Oxycodone"], "percocet": ["Oxycodone"], "endocet": ["Oxycodone"],
    "ms contin": ["Morphine"], "kadian": ["Morphine"], "dilaudid": ["Hydromorphone"], "exalgo": ["Hydromorphone"],
    "duragesic": ["Fentanyl"], "sublimaze": ["Fentanyl"], "actiq": ["Fentanyl"], "dolophine": ["Methadone"],
    "methadose": ["Methadone"], "versed": ["Midazolam"], "zofran": ["Ondansetron"], "zuplenz": ["Ondansetron"],
    "celebrex": ["Celecoxib"], "elyxyb": ["Celecoxib"], "advil": ["Ibuprofen"], "motrin": ["Ibuprofen"],
    "ansaid": ["Flurbiprofen"], "mobic": ["Meloxicam"], "vivlodex": ["Meloxicam"], "feldene": ["Piroxicam"],
    "aleve": ["Naproxen"], "naprosyn": ["Naproxen"], "anaprox": ["Naproxen"], "voltaren": ["Diclofenac"],
    "cambia": ["Diclofenac"], "indocin": ["Indomethacin"], "relafen": ["Nabumetone"], "suboxone": ["Buprenorphine"],
    "subutex": ["Buprenorphine"], "butrans": ["Buprenorphine"], "vivitrol": ["Naltrexone"],
    "anectine": ["Succinylcholine"], "quelicin": ["Succinylcholine"], "suxamethonium": ["Succinylcholine"],
    "suprane": ["Desflurane"], "ultane": ["Sevoflurane"], "forane": ["Isoflurane"],
    # gastrointestinal
    "prilosec": ["Omeprazole"], "zegerid": ["Omeprazole"], "prevacid": ["Lansoprazole"],
    "protonix": ["Pantoprazole"], "dexilant": ["Dexlansoprazole"], "nexium": ["Esomeprazole"],
    "aciphex": ["Rabeprazole"], "azulfidine": ["Sulfasalazine"],
    # psychiatry
    "celexa": ["Citalopram"], "lexapro": ["Escitalopram"], "zoloft": ["Sertraline"], "elavil": ["Amitriptyline"],
    "anafranil": ["Clomipramine"], "silenor": ["Doxepin"], "sinequan": ["Doxepin"], "tofranil": ["Imipramine"],
    "surmontil": ["Trimipramine"], "pamelor": ["Nortriptyline"], "aventyl": ["Nortriptyline"],
    "norpramin": ["Desipramine"], "paxil": ["Paroxetine"], "pexeva": ["Paroxetine"], "brisdelle": ["Paroxetine"],
    "luvox": ["Fluvoxamine"], "trintellix": ["Vortioxetine"], "effexor": ["Venlafaxine"], "prozac": ["Fluoxetine"],
    "sarafem": ["Fluoxetine"], "symbyax": ["Fluoxetine"], "strattera": ["Atomoxetine"], "cymbalta": ["Duloxetine"],
    "drizalma": ["Duloxetine"], "pristiq": ["Desvenlafaxine"], "fetzima": ["Levomilnacipran"],
    "savella": ["Milnacipran"], "viibryd": ["Vilazodone"],
    # neurology
    "dilantin": ["Phenytoin"], "phenytek": ["Phenytoin"], "cerebyx": ["Fosphenytoin"], "tegretol": ["Carbamazepine"],
    "carbatrol": ["Carbamazepine"], "equetro": ["Carbamazepine"], "epitol": ["Carbamazepine"],
    "trileptal": ["Oxcarbazepine"], "oxtellar": ["Oxcarbazepine"], "firdapse": ["Amifampridine"],
    "ruzurgi": ["Amifampridine"],
    # infectious disease
    "vfend": ["Voriconazole"], "sustiva": ["Efavirenz"], "atripla": ["Efavirenz"], "symfi": ["Efavirenz"],
    "nydrazid": ["Isoniazid"], "inh": ["Isoniazid"], "rifamate": ["Isoniazid"], "rifater": ["Isoniazid"],
    "aczone": ["Dapsone"], "reyataz": ["Atazanavir"], "evotaz": ["Atazanavir"], "ziagen": ["Abacavir"],
    "epzicom": ["Abacavir"], "triumeq": ["Abacavir"], "trizivir": ["Abacavir"], "pegasys": ["Peginterferon alfa"],
    "pegintron": ["Peginterferon alfa"], "peginterferon": ["Peginterferon alfa"], "copegus": ["Ribavirin"],
    "rebetol": ["Ribavirin"], "macrobid": ["Nitrofurantoin"], "macrodantin": ["Nitrofurantoin"],
    "bactrim": ["Sulfamethoxazole"], "septra": ["Sulfamethoxazole"], "smx tmp": ["Sulfamethoxazole"],
    "plaquenil": ["Hydroxychloroquine"], "cipro": ["Ciprofloxacin"], "avelox": ["Moxifloxacin"],
    "krintafel": ["Tafenoquine"], "arakoda": ["Tafenoquine"], "provayblue": ["Methylene blue"],
    "elitek": ["Rasburicase"], "krystexxa": ["Pegloticase"], "kalydeco": ["Ivacaftor"],
    "garamycin": ["Gentamicin"], "tobi": ["Tobramycin"], "pyridium": ["Phenazopyridine"],
    # oncology / transplant
    "nolvadex": ["Tamoxifen"], "soltamox": ["Tamoxifen"], "prograf": ["Tacrolimus"], "envarsus": ["Tacrolimus"],
    "astagraf": ["Tacrolimus"], "5 fu": ["Fluorouracil"], "5fu": ["Fluorouracil"], "adrucil": ["Fluorouracil"],
    "xeloda": ["Capecitabine"], "imuran": ["Azathioprine"], "azasan": ["Azathioprine"],
    "purinethol": ["Mercaptopurine"], "purixan": ["Mercaptopurine"], "6 mp": ["Mercaptopurine"],
    "tabloid": ["Thioguanine"], "6 tg": ["Thioguanine"], "camptosar": ["Irinotecan"], "onivyde": ["Irinotecan"],
    "adriamycin": ["Doxorubicin"],
    # other
    "zyloprim": ["Allopurinol"], "aloprim": ["Allopurinol"], "estrogen": ["Estrogen-containing therapy"],
    "estrogens": ["Estrogen-containing therapy"], "estradiol": ["Estrogen-containing therapy"],
    "ethinyl estradiol": ["Estrogen-containing therapy"], "conjugated estrogens": ["Estrogen-containing therapy"],
    "premarin": ["Estrogen-containing therapy"], "prempro": ["Estrogen-containing therapy"],
    "estrace": ["Estrogen-containing therapy"], "oral contraceptive": ["Estrogen-containing therapy"],
    "birth control pill": ["Estrogen-containing therapy"], "hormone replacement": ["Estrogen-containing therapy"],
    "glucotrol": ["Glipizide"], "amaryl": ["Glimepiride"], "glynase": ["Glyburide"], "diabeta": ["Glyburide"],
    "glibenclamide": ["Glyburide"], "acetylsalicylic acid": ["Aspirin"], "asa": ["Aspirin"],
    "ascorbic acid": ["Vitamin C"], "phytonadione": ["Vitamin K"], "mesalazine": ["Mesalamine"],
    "lialda": ["Mesalamine"], "asacol": ["Mesalamine"], "pentasa": ["Mesalamine"], "quinacrine": ["Mepacrine"],
}


# Common medications with no CPIC gene-drug guideline, so they are recognized (and typos corrected) rather than
# reported as "not recognized". Generic -> brand names.
NON_CPIC: dict[str, list[str]] = {
    # cardiovascular
    "Lisinopril": ["Zestril", "Prinivil"], "Enalapril": ["Vasotec"], "Ramipril": ["Altace"],
    "Benazepril": ["Lotensin"], "Losartan": ["Cozaar", "Hyzaar"], "Olmesartan": ["Benicar", "Azor", "Tribenzor"],
    "Valsartan": ["Diovan"], "Irbesartan": ["Avapro"], "Telmisartan": ["Micardis"], "Candesartan": ["Atacand"],
    "Sacubitril/valsartan": ["Entresto"], "Amlodipine": ["Norvasc"], "Nifedipine": ["Procardia", "Adalat"],
    "Diltiazem": ["Cardizem"], "Verapamil": ["Calan"], "Hydrochlorothiazide": ["Microzide", "HCTZ"],
    "Chlorthalidone": [], "Furosemide": ["Lasix"], "Torsemide": ["Demadex"], "Bumetanide": ["Bumex"],
    "Spironolactone": ["Aldactone"], "Eplerenone": ["Inspra"], "Atenolol": ["Tenormin"], "Propranolol": ["Inderal"],
    "Bisoprolol": ["Zebeta"], "Nebivolol": ["Bystolic"], "Labetalol": [], "Clonidine": ["Catapres"],
    "Apixaban": ["Eliquis"], "Rivaroxaban": ["Xarelto"], "Dabigatran": ["Pradaxa"], "Edoxaban": ["Savaysa"],
    "Ticagrelor": ["Brilinta"], "Prasugrel": ["Effient"], "Ezetimibe": ["Zetia"], "Fenofibrate": ["Tricor"],
    "Gemfibrozil": ["Lopid"], "Icosapent ethyl": ["Vascepa"], "Evolocumab": ["Repatha"], "Alirocumab": ["Praluent"],
    "Digoxin": ["Lanoxin"], "Amiodarone": ["Pacerone"], "Isosorbide mononitrate": ["Imdur"],
    "Nitroglycerin": ["Nitrostat"], "Ranolazine": ["Ranexa"],
    # endocrine
    "Metformin": ["Glucophage"], "Sitagliptin": ["Januvia", "Janumet"], "Empagliflozin": ["Jardiance"],
    "Dapagliflozin": ["Farxiga"], "Canagliflozin": ["Invokana"], "Semaglutide": ["Ozempic", "Wegovy", "Rybelsus"],
    "Tirzepatide": ["Mounjaro", "Zepbound"], "Liraglutide": ["Victoza", "Saxenda"], "Dulaglutide": ["Trulicity"],
    "Pioglitazone": ["Actos"], "Insulin": ["Lantus", "Humalog", "Novolog", "Levemir", "Tresiba", "Basaglar"],
    "Levothyroxine": ["Synthroid", "Levoxyl", "Unithroid"], "Liothyronine": ["Cytomel"],
    "Testosterone": ["AndroGel"], "Progesterone": ["Prometrium"], "Alendronate": ["Fosamax"],
    # gastrointestinal
    "Famotidine": ["Pepcid"], "Ranitidine": ["Zantac"], "Cimetidine": ["Tagamet"], "Sucralfate": ["Carafate"],
    "Metoclopramide": ["Reglan"], "Docusate": ["Colace"], "Polyethylene glycol": ["Miralax"],
    "Loperamide": ["Imodium"], "Dicyclomine": ["Bentyl"],
    # pain / musculoskeletal
    "Acetaminophen": ["Tylenol", "Paracetamol"], "Ketorolac": ["Toradol"], "Gabapentin": ["Neurontin"],
    "Pregabalin": ["Lyrica"], "Cyclobenzaprine": ["Flexeril"], "Tizanidine": ["Zanaflex"], "Baclofen": [],
    "Methocarbamol": ["Robaxin"], "Tapentadol": ["Nucynta"], "Oxymorphone": ["Opana"], "Colchicine": ["Colcrys"],
    "Febuxostat": ["Uloric"], "Methotrexate": ["Trexall"], "Adalimumab": ["Humira"],
    "Prednisone": [], "Prednisolone": [], "Methylprednisolone": ["Medrol"], "Dexamethasone": ["Decadron"],
    # psychiatry / neurology
    "Trazodone": ["Desyrel"], "Bupropion": ["Wellbutrin", "Zyban"], "Mirtazapine": ["Remeron"],
    "Buspirone": ["Buspar"], "Quetiapine": ["Seroquel"], "Aripiprazole": ["Abilify"], "Risperidone": ["Risperdal"],
    "Olanzapine": ["Zyprexa"], "Lithium": [], "Lamotrigine": ["Lamictal"], "Levetiracetam": ["Keppra"],
    "Topiramate": ["Topamax"], "Divalproex": ["Depakote", "Valproate", "Valproic acid"],
    "Clonazepam": ["Klonopin"], "Alprazolam": ["Xanax"], "Lorazepam": ["Ativan"], "Diazepam": ["Valium"],
    "Zolpidem": ["Ambien"], "Eszopiclone": ["Lunesta"], "Methylphenidate": ["Ritalin", "Concerta"],
    "Amphetamine": ["Adderall"], "Lisdexamfetamine": ["Vyvanse"], "Donepezil": ["Aricept"],
    "Memantine": ["Namenda"], "Sumatriptan": ["Imitrex"],
    # respiratory / allergy
    "Montelukast": ["Singulair"], "Albuterol": ["ProAir", "Ventolin", "Proventil"],
    "Fluticasone": ["Flonase", "Flovent"], "Budesonide": ["Pulmicort", "Symbicort"], "Cetirizine": ["Zyrtec"],
    "Loratadine": ["Claritin"], "Fexofenadine": ["Allegra"], "Diphenhydramine": ["Benadryl"],
    "Hydroxyzine": ["Vistaril", "Atarax"],
    # infection
    "Amoxicillin": ["Amoxil"], "Amoxicillin/clavulanate": ["Augmentin"], "Azithromycin": ["Zithromax", "Z-Pak"],
    "Doxycycline": [], "Cephalexin": ["Keflex"], "Clindamycin": ["Cleocin"], "Levofloxacin": ["Levaquin"],
    "Metronidazole": ["Flagyl"], "Valacyclovir": ["Valtrex"], "Acyclovir": ["Zovirax"], "Fluconazole": ["Diflucan"],
    # urology / other
    "Tamsulosin": ["Flomax"], "Finasteride": ["Proscar", "Propecia"], "Sildenafil": ["Viagra"],
    "Tadalafil": ["Cialis"], "Oxybutynin": ["Ditropan"], "Cyclosporine": ["Neoral", "Sandimmune"],
    "Mycophenolate": ["CellCept"], "Vitamin D": ["Cholecalciferol", "Ergocalciferol", "Vitamin D3", "Vitamin D2"], "Calcium": [],
    "Magnesium": [], "Potassium chloride": ["K-Dur", "Klor-Con"], "Folic acid": [], "Iron": ["Ferrous sulfate"],
    "Multivitamin": [], "Fish oil": ["Omega-3"],
}


def _norm(s: str) -> str:
    s = s.lower().replace("#", " ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def catalog_names() -> list[str]:
    """Every searchable generic name (for autocomplete)."""
    return sorted(set(DRUGS_BY_NAME) | set(EXTRA_BY_NAME) | set(NON_CPIC))


def _build_index() -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for name in catalog_names():
        idx.setdefault(_norm(name), []).append(name)
    idx[_norm("Estrogen-containing therapy")] = ["Estrogen-containing therapy"]
    for alias, targets in ALIASES.items():
        idx.setdefault(_norm(alias), [])
        idx[_norm(alias)] += [t for t in targets if t not in idx[_norm(alias)]]
    for generic, brands in NON_CPIC.items():
        for b in brands:
            idx.setdefault(_norm(b), [generic])
    return idx


_INDEX = _build_index()
for _targets in _INDEX.values():  # every alias must point at a real catalog entry
    for _t in _targets:
        assert _t in DRUGS_BY_NAME or _t in EXTRA_BY_NAME or _t in NON_CPIC, _t
_KEYS_LONGEST_FIRST = sorted(_INDEX, key=len, reverse=True)


def search_terms() -> list[str]:
    """Generic names plus brand names, for the web page's type-ahead list."""
    brands = [a.title() if len(a) > 3 else a.upper() for a in ALIASES]
    brands += [b for bs in NON_CPIC.values() for b in bs]
    return sorted(set(catalog_names()) | set(brands), key=str.lower)


@dataclass
class Match:
    entered: str
    names: list[str]  # catalog names found ([] if none)
    fuzzy: bool = False


def match_entry(entered: str) -> Match:
    text = _norm(entered)
    if not text:
        return Match(entered, [])
    padded = f" {text} "
    found: list[str] = []
    for key in _KEYS_LONGEST_FIRST:
        if f" {key} " in padded:
            for name in _INDEX[key]:
                if name not in found:
                    found.append(name)
            padded = padded.replace(f" {key} ", " " + "_" * len(key) + " ")  # don't re-match inside it
    if found:
        return Match(entered, found)
    # Typos: compare each word (and word pair) to the catalog; strict cutoff to avoid false matches.
    words = [w for w in text.split() if len(w) >= 5 and not w.isdigit()]
    candidates = words + [f"{a} {b}" for a, b in zip(text.split(), text.split()[1:])]
    best = (0.0, "")
    for c in candidates:
        for key in difflib.get_close_matches(c, _INDEX.keys(), n=3, cutoff=0.86):
            score = difflib.SequenceMatcher(None, c, key).ratio()
            if score > best[0]:
                best = (score, key)
    if best[1]:
        return Match(entered, list(_INDEX[best[1]]), fuzzy=True)
    return Match(entered, [])


def split_entries(raw: str) -> list[str]:
    """Operator input: one medication per line, or separated by commas/semicolons."""
    return [p.strip() for p in re.split(r"[\n;,]+", raw or "") if p.strip()]


@dataclass
class PatientMed:
    entered: str
    name: Optional[str]
    kind: str  # RULE / UNTESTED / NOREC / UNKNOWN
    result: Optional[DrugResult] = None
    entry: Optional[CatalogEntry] = None
    fuzzy: bool = False

    @property
    def tier(self) -> str:
        return self.result.tier if self.result else GREY

    @property
    def display_name(self) -> str:
        return self.name or self.entered

    @property
    def entered_differs(self) -> bool:
        return bool(self.name) and _norm(self.entered) != _norm(self.name)

    @property
    def genes(self) -> tuple[str, ...]:
        if self.result:
            return self.result.drug.genes
        return self.entry.genes if self.entry else ()

    @property
    def text(self) -> str:
        if self.result:
            return self.result.rec.text
        if self.entry:
            return self.entry.text
        if self.kind == NONE:
            return "No CPIC gene–drug guideline exists for this medication; dose per usual practice."
        return ("Medication not recognized, so no CPIC recommendation can be shown. Check the spelling, or use "
                "the generic name.")

    @property
    def short(self) -> str:
        if self.result:
            return self.result.rec.short
        if self.entry:
            return self.entry.short
        if self.kind == NONE:
            return "No CPIC gene–drug guideline."
        return "Not recognized; check spelling or use generic name."

    @property
    def source(self) -> str:
        if self.result:
            return self.result.source
        return self.entry.source if self.entry else "—"

    @property
    def status(self) -> str:
        if self.result:
            return {"red": "AVOID OR CHANGE", "yellow": "ADJUST OR MONITOR", "green": "STANDARD DOSING"}[self.tier]
        if self.kind == UNTESTED:
            return "GENE NOT TESTED"
        if self.kind == NOREC:
            return "NO CPIC RECOMMENDATION"
        if self.kind == NONE:
            return "NO CPIC GUIDELINE"
        return "NOT RECOGNIZED"


def resolve(entries: list[str], results: list[DrugResult]) -> list[PatientMed]:
    """Match operator entries and attach this patient's recommendation for each drug found."""
    by_name = {r.drug.name: r for r in results}
    out: list[PatientMed] = []
    seen: set[str] = set()
    for e in entries:
        m = match_entry(e)
        if not m.names:
            out.append(PatientMed(e, None, UNKNOWN))
            continue
        for name in m.names:
            if name in seen:
                continue
            seen.add(name)
            if name in by_name:
                out.append(PatientMed(e, name, RULE, result=by_name[name], fuzzy=m.fuzzy))
            elif name in DRUGS_BY_NAME:
                # A rule exists but a needed gene was not on this patient's report.
                missing = [g for g in DRUGS_BY_NAME[name].genes]
                out.append(PatientMed(e, name, UNTESTED, entry=CatalogEntry(
                    name, tuple(missing), "A gene needed for this drug was not on this lab report.",
                    "Gene not on this report.", DRUGS_BY_NAME[name].source), fuzzy=m.fuzzy))
            elif name in NON_CPIC:
                out.append(PatientMed(e, name, NONE, fuzzy=m.fuzzy))
            else:
                entry = EXTRA_BY_NAME[name]
                kind = NOREC if entry.short.startswith("No CPIC") else UNTESTED
                out.append(PatientMed(e, name, kind, entry=entry, fuzzy=m.fuzzy))
    order = {"red": 0, "yellow": 1, "green": 2, GREY: 3}
    return sorted(out, key=lambda pm: (order[pm.tier], {RULE: 0, UNTESTED: 1, NOREC: 2, NONE: 3, UNKNOWN: 4}[pm.kind]))


def drug_list_markdown() -> str:
    """Every medication the program recognizes, grouped by how it is handled (for CPIC_DRUG_LIST.md)."""
    from .rules import CATEGORIES, DRUGS

    brands: dict[str, list[str]] = {}
    for alias, targets in ALIASES.items():
        for t in targets:
            brands.setdefault(t, []).append(alias.title() if len(alias) > 3 else alias.upper())
    lines = ["# Medications recognized by PGx Translator", "",
             "Generated by `python -m pgx_translator --list-drugs`. Names in the last column also match.", ""]
    lines += ["## Evaluated against the patient's Quest results", "",
              "| Drug | Gene(s) | Source | Also matches |", "|---|---|---|---|"]
    for cat in CATEGORIES:
        for d in [d for d in DRUGS if d.category == cat]:
            lines.append(f"| {d.name} | {', '.join(d.genes)} | {d.source} | {', '.join(sorted(brands.get(d.name, [])))} |")
    for title, kind in (("CPIC guideline exists, but the gene is not on the Quest panel", UNTESTED),
                        ("CPIC reviewed: no gene-based recommendation", NOREC)):
        lines += ["", f"## {title}", "", "| Drug | Gene(s) | Source | Also matches |", "|---|---|---|---|"]
        for e in EXTRA_ENTRIES:
            if (NOREC if e.short.startswith("No CPIC") else UNTESTED) == kind:
                lines.append(f"| {e.name} | {', '.join(e.genes)} | {e.source} | {', '.join(sorted(brands.get(e.name, [])))} |")
    lines += ["", "## Common medications with no CPIC gene–drug guideline", "",
              "Recognized so typos are corrected and the report can say \"No CPIC guideline\" with confidence.", "",
              ", ".join(sorted(NON_CPIC)), "",
              "Anything else is reported as \"Not recognized\" with a prompt to check the spelling."]
    return "\n".join(lines)
