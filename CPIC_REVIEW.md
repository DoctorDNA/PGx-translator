# CPIC review log

Each rule in `pgx_translator/rules.py` is checked against the published CPIC guideline PDF.
A checked drug shows the guideline year in its source (e.g. "CPIC 2019") on every report;
"CPIC" alone means the rule is based on CPIC guidance but has not been checked yet.

## Checked

| Guideline (file reviewed) | Drugs | Result | Checked |
|---|---|---|---|
| CYP2D6/CYP2C19 & tricyclic antidepressants, 2016 update (CPT 2017;102:37), Tables 2–4 | amitriptyline, clomipramine, doxepin, imipramine, trimipramine, nortriptyline, desipramine | Tiers matched. Added: 50% start reduction if a TCA is warranted in CYP2D6 PM (and CYP2C19 PM tertiary amines); higher target dose with TDM in CYP2D6 UM; TDM for tertiary amines in CYP2C19 UM/RM; note that recommendations apply to depression-range doses (no change for IM/PM at low neuropathic-pain doses). | 2026-10-14 |
| CYP2D6 & atomoxetine, 2019, Table 3 (adults) | atomoxetine | **Changed.** Activity score 1.0 without CYP2D6\*10 (e.g. \*1/\*5) is dosed like normal metabolizers → green. AS 0.25–0.5, or 1.0 with \*10, and PM → slow schedule (40 mg/day, 80 mg/day only after 2 weeks) → yellow; previously these got the 3-day titration. Pediatric weight-based dosing (Table 2) referenced, not implemented. | 2026-10-14 |
| UGT1A1 & atazanavir, 2015, Table 2 | atazanavir | Tiers matched. Added CPIC discontinuation figures and counseling wording. | 2026-10-14 |
| HLA-B & abacavir, 2014 update | abacavir | Update states the 2012 original remains current; rule matches the 2012 recommendation. Original 2012 table not yet reviewed directly. | 2026-10-14 |
| HLA-B & allopurinol, 2015 update | allopurinol | Update states the 2013 original remains current; rule matches the 2013 recommendation. Original 2013 table not yet reviewed directly. | 2026-10-14 |

## Not yet checked

PPIs, clopidogrel, voriconazole (CYP2C19); SSRIs/SNRIs (CYP2D6, CYP2C19, CYP2B6); opioids;
ondansetron/tropisetron; tamoxifen; beta-blockers (metoprolol); statins (SLCO1B1, ABCG2, CYP2C9);
warfarin; NSAIDs; phenytoin; carbamazepine/oxcarbazepine; efavirenz; tacrolimus; fluoropyrimidines
(DPYD); thiopurines (TPMT, NUDT15); hydralazine (NAT2).

Non-CPIC rules (Literature / FDA label / DPWG): procainamide, isoniazid, dapsone, sulfasalazine,
amifampridine, methadone, midazolam, irinotecan, estrogen-containing therapy.
